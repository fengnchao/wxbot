"""Explicit, restartable import of local legacy directory fields."""
import os
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import tomlkit
from .directory import DirectoryStore, directory_path, migration_source_name


def _replace(path, text):
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def migrate_installation(root):
    from contextlib import ExitStack
    from common.config_lock import config_lock
    root = Path(root).resolve()
    with ExitStack() as locks:
        for name in ('config.butler.toml', 'config.wxbot.toml'):
            locks.enter_context(config_lock(root/name))
        return _migrate_locked(root)


def _migrate_locked(root):
    root = Path(root).resolve()
    butler = root/'config.butler.toml'
    wxbot = root/'config.wxbot.toml'
    shared_path = directory_path(butler)
    if wxbot.exists() and directory_path(wxbot) != shared_path:
        raise ValueError("Butler and wxbot directory database paths must match")
    store = DirectoryStore(shared_path)
    files = []
    for path in (butler,wxbot):
        if path.exists():
            original = path.read_bytes()
            files.append((path,original,tomlkit.parse(original.decode('utf-8-sig'))))
    with store.transaction() as db:
        # Upgrade old absolute ledger keys in-place. Never visit those paths.
        for row in list(db.execute('SELECT * FROM directory_migrations')):
            key = migration_source_name(row['source'])
            if key is None or key == row['source']:
                continue
            existing = db.execute('SELECT * FROM directory_migrations WHERE source=?',(key,)).fetchone()
            if existing and (existing['digest'],existing['fields']) != (row['digest'],row['fields']):
                raise ValueError('conflicting directory migration ledger entries')
            if not existing:
                db.execute('INSERT INTO directory_migrations VALUES(?,?,?)',(key,row['digest'],row['fields']))
            db.execute('DELETE FROM directory_migrations WHERE source=?',(row['source'],))
        state = store._snapshot(db)
        changed = False
        for path, original, doc in files:
            if db.execute('SELECT 1 FROM directory_migrations WHERE source=?',(path.name,)).fetchone():
                continue
            fields = []
            if path == butler:
                state['contacts'].extend([dict(row) for row in doc.get('contacts',[])])
                if 'contacts' in doc:
                    fields.append(['contacts'])
                    del doc['contacts']
            else:
                channel = state['channel']
                bot = doc.get('bot',{})
                target = channel.setdefault('bot',{})
                for key,default in [('bound_users',[]),('bound_groups',[]),('mention_names',[])]:
                    value = bot.get(key,default)
                    if not isinstance(value, list) or any(not isinstance(item,str) for item in value):
                        raise ValueError(f'bot.{key} must be a list of names')
                    target[key] = list(value)
                    if key in bot:
                        fields.append(['bot',key])
                        del bot[key]
                main = doc.get('wechat',{}).get('main_window',{})
                listen_all = main.get('listen_all', True)
                if type(listen_all) is not bool:
                    raise ValueError('wechat.main_window.listen_all must be boolean')
                channel.setdefault('wechat',{}).setdefault('main_window',{})['listen_all'] = listen_all
                if 'listen_all' in main:
                    fields.append(['wechat','main_window','listen_all'])
                    del main['listen_all']
                sender = doc.get('wechat',{}).get('group_sender',{})
                for key,name in sender.get('member_names',{}).items():
                    state['aliases'].append(dict(group='',member_key=key,name=name,source='legacy',pending=True))
                if 'member_names' in sender:
                    fields.append(['wechat','group_sender','member_names'])
                    del sender['member_names']
                queue = Path(doc.get('queue',{}).get('database') or 'cache/wxbot_queue.sqlite3')
                queue = queue if queue.is_absolute() else root/queue
                if queue.exists():
                    with sqlite3.connect(f'{queue.resolve().as_uri()}?mode=ro',uri=True) as old:
                        if old.execute("SELECT 1 FROM sqlite_master WHERE name='group_member_names'").fetchone():
                            for group,key,name in old.execute('SELECT contact,member_key,name FROM group_member_names'):
                                state['aliases'].append(dict(group=group,member_key=key,name=name,source='learned',pending=False))
            db.execute('INSERT INTO directory_migrations VALUES(?,?,?)',(path.name,hashlib.sha256(original).hexdigest(),json.dumps(fields)))
            changed = True
        if changed:
            store._save(db,state,state['version'])
    # Ledger survives interruption between commit and file replacement. Never replay imports.
    cleaned = []
    with store.transaction() as db:
        entries = list(db.execute('SELECT * FROM directory_migrations'))
    for row in entries:
        key = migration_source_name(row['source'])
        if key is None:
            continue
        path = root/key
        if not path.exists():
            continue
        current = path.read_bytes()
        if hashlib.sha256(current).hexdigest() == row['digest']:
            doc = tomlkit.parse(current.decode('utf-8-sig'))
            for keys in json.loads(row['fields']):
                target = doc
                for key in keys[:-1]:
                    target = target[key]
                del target[keys[-1]]
            text = tomlkit.dumps(doc)
            if current.startswith(b'\xef\xbb\xbf'):
                text = '\ufeff'+text
            _replace(path,text)
            cleaned.append(str(path))
    return dict(database=str(store.path),version=store.snapshot()['version'],cleaned=cleaned)
