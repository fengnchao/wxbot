"""Independent reception and forwarding loops; wxbot remains the UI owner."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import threading

from butler.push_client import push_news
from .client import fatal_error
from .formatting import parts


@contextmanager
def instance_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('另一个 Telegram 接收或登录进程正在使用此状态/会话') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def read_subscribers(path, *, database=None):
    from butler.contact_store import ContactStore,is_unified
    if database and is_unified(database):
        return ContactStore(database).groups().get('1',[])
    try:
        raw = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        raise ValueError('新闻分组文件不可读或格式损坏') from None
    if not isinstance(raw, dict) or not isinstance(raw.get('groups', raw), dict):
        raise ValueError('新闻分组格式无效')
    groups = raw.get('groups', raw)
    if '1' not in groups:
        raise ValueError('新闻分组缺失，暂停投递')
    users = groups['1']
    if not isinstance(users, list) or any(not isinstance(u, str) or len(u) > 64 for u in users):
        raise ValueError('新闻订阅者须为微信会话名称列表')
    return list(dict.fromkeys(u.strip() for u in users if u.strip()))


async def wait_signal(stop, seconds, wake=None):
    tasks = [asyncio.create_task(stop.wait())]
    if wake is not None:
        tasks.append(asyncio.create_task(wake.wait()))
    try:
        await asyncio.wait(tasks, timeout=seconds, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class Relay:
    def __init__(self, cfg, butler_cfg, store, source, *, push=push_news):
        self.cfg, self.butler_cfg, self.store, self.source = cfg, butler_cfg, store, source
        self.push = push
        self.ready = False
        self.active_sources = set()
        self.stopping = threading.Event()

    async def scan_once(self):
        self.ready = False
        await self.source.connect()
        account = await self.source.account_id()
        resolved = []
        for username in self.cfg.sources:
            source = await self.source.resolve(username)
            cursor = self.store.cursor(source.id)
            baseline = await self.source.latest(source) if cursor is None else cursor
            self.store.bind(account, source.id, username, baseline)
            resolved.append(source)
        self.active_sources = {s.id for s in resolved}
        for source in resolved:
            async for messages, cursor in self.source.after(source, self.store.cursor(source.id)):
                if self.stopping.is_set():
                    return
                self.store.ingest(source.id, messages, cursor)
        self.store.runtime('connection', 'connected')
        self.store.runtime('scan_error', '')
        self.ready = True

    def deliver_once(self):
        if not self.ready or self.stopping.is_set():
            return False
        group_path = self.butler_cfg.group_file_path()
        for message in self.store.unexpanded(source_ids=self.active_sources):
            users = read_subscribers(group_path,database=getattr(self.butler_cfg,'contact_database',None))
            self.store.expand(message, users, parts(message))
        if self.stopping.is_set():
            return False
        users = read_subscribers(group_path,database=getattr(self.butler_cfg,'contact_database',None))
        item = self.store.claim(users, source_ids=self.active_sources)
        if item is None:
            return False
        if self.stopping.is_set():
            # No HTTP request has started. This pending task is safe to resume.
            self.store.defer(item.id)
            return False
        try:
            result = self.push(self.butler_cfg, item.contact, item.text)
            if not isinstance(result, dict) or result.get('state') not in ('sent', 'not_submitted', 'uncertain'):
                result = {'state': 'uncertain', 'reason': '无效投递回执，须人工核对'}
        except Exception as exc:
            result = {'state': 'uncertain', 'reason': type(exc).__name__ + '：结果待核对'}
        self.store.finish(item.id, result['state'], result.get('reason', ''))
        self.store.runtime('delivery_error', '')
        return True

    async def _scan_loop(self, stop):
        backoff = 1
        while not stop.is_set():
            self.source.wake.clear()
            delay = self.cfg.scan_interval
            try:
                await self.scan_once()
                backoff = 1
            except Exception as exc:
                self.ready = False
                self.store.runtime('connection', 'error')
                self.store.runtime('scan_error', type(exc).__name__)
                if fatal_error(exc) or isinstance(exc, ValueError):
                    raise
                # Database errors must not become an endless reconnect loop.
                import sqlite3
                if isinstance(exc, sqlite3.Error):
                    raise
                delay = max(1, getattr(exc, 'seconds', backoff))
                backoff = min(60, backoff * 2)
                await self.source.close()
            await wait_signal(stop, delay, self.source.wake if self.ready else None)

    async def _delivery_loop(self, stop):
        while not stop.is_set():
            try:
                worked = await asyncio.to_thread(self.deliver_once)
            except ValueError as exc:
                self.store.runtime('delivery_error', type(exc).__name__)
                worked = False
            if not worked:
                await wait_signal(stop, 1)

    async def run(self, stop):
        self.store.recover()
        self.store.runtime('service', 'running')
        scan = asyncio.create_task(self._scan_loop(stop))
        delivery = asyncio.create_task(self._delivery_loop(stop))
        stopping = asyncio.create_task(stop.wait())
        error = None
        try:
            done, _ = await asyncio.wait([scan, delivery, stopping], return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not stopping and not task.cancelled():
                    error = task.exception() or error
        finally:
            self.ready = False
            self.stopping.set()
            stop.set()
            scan.cancel()
            stopping.cancel()
            # Let the current bounded HTTP request record its result before closing SQLite.
            await asyncio.gather(scan, stopping, delivery, return_exceptions=True)
            try:
                await self.source.close()
            finally:
                self.store.runtime('service', 'failed' if error else 'stopped')
                self.store.runtime('connection', 'disconnected')
        if error:
            raise error
