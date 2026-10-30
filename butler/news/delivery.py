"""Daily digest persistence and per-recipient/part delivery receipts."""
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3

import requests

from common.news_config import atomic_json, read_settings, runtime_path
from .collector import CST, collect


@contextmanager
def run_lock(folder):
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'run.lock').open('a+b') as file:
        if file.tell() == 0:
            file.write(b'0')
            file.flush()
        file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('另一个新闻任务正在执行，本次跳过') from None
        try:
            yield
        finally:
            file.seek(0)
            if os.name == 'nt':
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file, fcntl.LOCK_UN)


def subscribers(path, *, database=None):
    from butler.contact_store import ContactStore,is_unified
    if database and is_unified(database):
        return ContactStore(database).groups().get('1',[])
    raw = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(raw, dict):
        raise ValueError('分组文件格式无效')
    groups = raw.get('groups', raw)
    if not isinstance(groups, dict):
        raise ValueError('分组文件格式无效')
    users = groups.get('1', [])
    if not isinstance(users, list) or any(not isinstance(u, str) or len(u) > 64 for u in users):
        raise ValueError('新闻订阅者须为微信会话名称列表')
    return list(dict.fromkeys(u.strip() for u in users if u.strip()))


def message_parts(text):
    blocks = text.split('\n\n')
    header, body = blocks[0], blocks[1:]
    parts, current = [], header
    for block in body:
        if len(current) + len(block) + 2 > 500 and current != header:
            parts.append(current)
            current = header
        current += '\n\n' + block
    if current != header:
        parts.append(current)
    if len(parts) > 1:
        parts = [part.replace('\n', f'（{index}/{len(parts)}）\n', 1)
                 for index, part in enumerate(parts, 1)]
    return parts


def push(cfg, contact, text):
    """A failed HTTP result can still mean queued: never blindly resend it."""
    if not cfg.token:
        return {'state': 'not_submitted', 'reason': 'Butler Token 未配置'}
    host = cfg.host
    if host in ('0.0.0.0', '::'):
        host = '127.0.0.1'
    if ':' in host and not host.startswith('['):
        host = '[' + host + ']'
    url = f'http://{host}:{cfg.port}/v1/push'
    try:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(url, json={'type': 1, 'messageType': 1, 'contact': contact, 'text': text},
                                    headers={'Authorization': 'Bearer ' + cfg.token},
                                    timeout=(5, max(150, float(cfg.wxbot_timeout or 120) + 30)),
                                    allow_redirects=False)
        if response.status_code in (400, 401, 403, 404):
            return {'state': 'not_submitted', 'reason': f'Butler 拒绝请求：HTTP {response.status_code}'}
        response.raise_for_status()
        result = response.json()
        meta = result.get('meta') if isinstance(result, dict) else None
        if isinstance(meta, dict) and meta.get('ok') is True and meta.get('contact') == contact:
            return {'state': 'sent', 'reason': 'Butler 确认微信发送成功'}
        return {'state': 'uncertain', 'reason': 'Butler 未确认发送成功，请在收发队列核对'}
    except (requests.RequestException, ValueError) as exc:
        return {'state': 'uncertain', 'reason': type(exc).__name__ + '：结果未知，不自动重发'}


def run(cfg):
    groups = cfg.group_file_path()
    if not groups:
        raise ValueError('未配置新闻订阅分组文件')
    folder = runtime_path(groups)
    now = datetime.now(CST)
    day = now.strftime('%Y-%m-%d')
    report = {'date': day, 'status': 'started', 'article_count': 0, 'sent': 0, 'uncertain': 0}
    with run_lock(folder):
        try:
            settings, _ = read_settings(groups)
            users = subscribers(groups,database=getattr(cfg,'contact_database',None))
            if not users:
                report['status'] = 'no_subscribers'
                return report
            # Today's earlier mock delivery also counts, avoiding an upgrade duplicate.
            legacy = Path(groups).parent / 'mock_news_daily' / (day + '.json')
            if legacy.exists():
                report['status'] = 'legacy_run_exists'
                return report
            with sqlite3.connect(folder / 'delivery.sqlite3', timeout=5) as db:
                db.execute('PRAGMA synchronous=FULL')
                db.execute('CREATE TABLE IF NOT EXISTS deliveries (day TEXT, contact TEXT, part INTEGER, state TEXT, detail TEXT, PRIMARY KEY(day,contact,part))')
                # Holding the process lock proves no earlier owner is still sending.
                db.execute("UPDATE deliveries SET state='uncertain',detail='上次任务在发送期间退出，结果待核对' WHERE state='sending'")
                db.commit()
                digest_file = folder / (day + '.json')
                if digest_file.exists():
                    digest = json.loads(digest_file.read_text(encoding='utf-8'))
                else:
                    digest = collect(settings, now)
                    if not digest['articles']:
                        report.update(status='no_news', sources=digest['sources'])
                        return report
                    atomic_json(digest_file, digest)
                report['article_count'] = len(digest['articles'])
                report['targets'] = users
                parts = message_parts(digest['text'])
                if not parts:
                    raise ValueError('简报内容为空')
                results = []
                for user in users:
                    completed = True
                    detail = '全部分段已确认发送'
                    for number, text in enumerate(parts, 1):
                        row = db.execute('SELECT state,detail FROM deliveries WHERE day=? AND contact=? AND part=?',
                                         (day, user, number)).fetchone()
                        if row and row[0] == 'sent':
                            continue
                        if row and row[0] == 'uncertain':
                            completed = False
                            detail = row[1]
                            break
                        with db:
                            db.execute('INSERT OR REPLACE INTO deliveries VALUES(?,?,?,?,?)',
                                       (day, user, number, 'sending', '请求已准备，等待确认'))
                        result = push(cfg, user, text)
                        with db:
                            db.execute('UPDATE deliveries SET state=?,detail=? WHERE day=? AND contact=? AND part=?',
                                       (result['state'], result['reason'], day, user, number))
                        if result['state'] != 'sent':
                            completed = False
                            detail = result['reason']
                            break
                    results.append({'contact': user, 'complete': completed, 'detail': detail})
                report['sent'] = sum(r['complete'] for r in results)
                report['uncertain'] = db.execute("SELECT COUNT(DISTINCT contact) FROM deliveries WHERE day=? AND state='uncertain'", (day,)).fetchone()[0]
                report['status'] = 'sent' if report['sent'] == len(users) else 'incomplete'
                report['results'] = results
                return report
        except Exception as exc:
            report.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            report['updated_at'] = datetime.now(CST).isoformat()
            atomic_json(folder / 'latest.json', report)
