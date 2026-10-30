"""Delete unsuccessful Telegram work without creating or migrating a queue."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from butler.channels.telegram.bot.news import NewsRelay


DELETED_REASON = '未成功投递已删除；部分成功记录保留，其他投递已停止'
ACTIVE_REASON = '未成功投递已删除；正在发送的任务保留，其他投递已停止'


def delete_unsent(path, *, now=None, backup_path=None):
    """Keep sent receipts and in-flight sends; preparing media is cancellable.

    The existing polling cursor is also the ingestion high-water mark. No new
    table, schema migration, configuration, subscription, or network call is needed.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Telegram 接收队列尚未创建')
    with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=5)) as db, db:
        db.row_factory = sqlite3.Row
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'cursor', 'pending', 'news_plan', 'news_delivery'}
        if not required <= tables or bool('news_package' in tables) != bool('news_bundle_delivery' in tables):
            raise ValueError('Telegram 队列不支持清理，未修改或迁移数据库')
        db.execute('BEGIN IMMEDIATE')
        if backup_path is not None:
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as reader:
                with closing(sqlite3.connect(backup_path)) as backup:
                    reader.backup(backup)
        messages = db.execute('SELECT bot,uid,payload FROM pending').fetchall()
        plans = {(row['bot'], row['uid']): row['reason'] or '' for row in
                 db.execute('SELECT bot,uid,reason FROM news_plan')}
        text = db.execute('SELECT id,bot,uid,state FROM news_delivery').fetchall()
        media = 'news_package' in tables
        packages = db.execute('SELECT bot,package_key,uid FROM news_package').fetchall() if media else []
        bundles = db.execute('SELECT id,bot,package_key,state FROM news_bundle_delivery').fetchall() if media else []
        aliases = {(row['bot'], row['alias']): row['package_key'] for row in
                   db.execute('SELECT bot,alias,package_key FROM news_package_alias')} if 'news_package_alias' in tables else {}
        package_keys = {(row['bot'], row['package_key']) for row in packages}
        members = {key: set() for key in package_keys}
        for row in packages:
            members[(row['bot'], row['package_key'])].add((row['bot'], row['uid']))
        for row in messages:
            if plans.get((row['bot'], row['uid']), '').startswith('图集迟到或重复成员，'):
                continue  # Late members have no receipt for their own media.
            try:
                message = json.loads(row['payload'])['message']
                identity = NewsRelay._package_key(message)
            except (ValueError, TypeError, KeyError):
                continue
            key = row['bot'], aliases.get((row['bot'], identity), identity)
            if key in members:
                members[key].add((row['bot'], row['uid']))
        protected = {'sent', 'sending'}
        sent_sources = {(row['bot'], row['uid']) for row in text if row['state'] == 'sent'}
        sent_packages = {(row['bot'], row['package_key']) for row in bundles if row['state'] == 'sent'}
        for key in sent_packages:
            sent_sources.update(members.get(key, ()))
        keep_sources = {(row['bot'], row['uid']) for row in text if row['state'] in protected}
        keep_packages = {(row['bot'], row['package_key']) for row in bundles if row['state'] in protected}
        for key in keep_packages:
            keep_sources.update(members.get(key, ()))
        removed_text = [row for row in text if row['state'] not in protected]
        removed_bundles = [row for row in bundles if row['state'] not in protected]
        changed_sources = {(row['bot'], row['uid']) for row in removed_text}
        changed_packages = {(row['bot'], row['package_key']) for row in removed_bundles}
        for key in changed_packages:
            changed_sources.update(members.get(key, ()))
        db.executemany('DELETE FROM news_delivery WHERE id=?', [(row['id'],) for row in removed_text])
        if media:
            db.executemany('DELETE FROM news_bundle_delivery WHERE id=?', [(row['id'],) for row in removed_bundles])
        # Retain the plan as a cancellation/receipt boundary for partial success.
        # The source row is needed to display the unchanged successful receipts.
        for bot, uid in keep_sources & changed_sources:
            reason = DELETED_REASON if (bot, uid) in sent_sources else ACTIVE_REASON
            db.execute('INSERT INTO news_plan(bot,uid,reason) VALUES(?,?,?) '
                       'ON CONFLICT(bot,uid) DO UPDATE SET reason=excluded.reason', (bot, uid, reason))
        if media:
            for bot, key in keep_packages & changed_packages:
                reason = DELETED_REASON if (bot, key) in sent_packages else ACTIVE_REASON
                db.execute("UPDATE news_package SET state='cancelled',reason=? WHERE bot=? AND package_key=?",
                           (reason, bot, key))
            for row in packages:
                key = row['bot'], row['package_key']
                if key not in keep_packages:
                    if 'news_package_alias' in tables:
                        db.execute('DELETE FROM news_package_alias WHERE bot=? AND package_key=?', key)
                    db.execute('DELETE FROM news_package WHERE bot=? AND package_key=?', key)
        removed_messages = [(row['bot'], row['uid']) for row in messages
                            if (row['bot'], row['uid']) not in keep_sources]
        db.executemany('DELETE FROM news_plan WHERE bot=? AND uid=?', removed_messages)
        db.executemany('DELETE FROM pending WHERE bot=? AND uid=?', removed_messages)
        return {'deleted_messages': len(removed_messages),
                'deleted_deliveries': len(removed_text) + len(removed_bundles),
                'protected_active': sum(row['state'] == 'sending' for row in [*text, *bundles])}
