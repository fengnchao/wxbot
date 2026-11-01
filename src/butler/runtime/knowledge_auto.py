"""定时把 L1 原文提炼成 L2 事实：进程内单线程，一轮只喂模型一批。

为什么挂在 Butler 进程里：写路径统一收在这一侧，管理台只读；提炼和落原文共用
同一个 KnowledgeStore，跨进程各写一份只会多出争用。
为什么不用系统计划任务：退避、单飞锁与状态要和 CLI 共用一套，两套进程更难查。

一轮的判定顺序见 `_round`：有开关 → 到点 → 没人在说话 → 有积压 → 抢得到锁。
任何一条不满足都只推迟，不算失败；真正失败的只有模型调用与写库。
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from butler.identity.contacts import Contact
from butler.runtime.knowledge_extract import MAX_BATCH, extract

LOCK_STALE_SECONDS = 1800        # 锁文件超过半小时视为上次进程崩了
DEFER_SECONDS = 300              # 有消息往来时顺延多久再看
MAX_BACKOFF_SECONDS = 6 * 3600
MAX_IDLE_SECONDS = 3600
SCAN_LIMIT = 50                  # 一轮最多看多少人的目录
EXTRACT_WORKER = ('知识库提炼', 'knowledge-extract')


def acquire(path):
    """跨进程单飞：O_EXCL 建锁文件，崩掉留下的旧锁按 mtime 过期。

    CLI 和调度器都拿这一把：同一批原文被送两次模型只是白花钱，事实本身有去重。
    """
    lock = Path(path)
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    for attempt in (1, 2):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if attempt == 2:
                return None
            try:
                if time.time() - lock.stat().st_mtime < LOCK_STALE_SECONDS:
                    return None
                lock.unlink()
            except OSError:
                return None
            continue
        except OSError:
            return None
        try:
            os.write(fd, ('%d %f' % (os.getpid(), time.time())).encode('ascii'))
        finally:
            os.close(fd)
        return str(lock)
    return None


def release(handle):
    if not handle:
        return
    try:
        os.unlink(handle)
    except OSError:
        pass


class ExtractScheduler:
    """定时提炼 + 手动触发 + 每日清理。审计只记条数与错误类型，不写模型原文。"""

    def __init__(self, butler, cfg, log=None):
        self.butler = butler
        self.cfg = cfg
        self.log = log or (lambda *a, **k: None)
        self.state_path = cfg.knowledge_extract_state_path()
        self.audit_path = cfg.knowledge_extract_audit_path()
        self.lock_path = cfg.knowledge_extract_lock_path()
        self._stop = threading.Event()
        self._thread = None
        self._running = threading.Lock()      # 定时轮与手动触发互斥
        self._audit_lock = threading.Lock()

    # ---------- 状态与审计 ----------
    def _audit(self, event, **fields):
        row = {'at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'event': event, **fields}
        try:
            path = Path(self.audit_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n'
            with self._audit_lock, open(path, 'a', encoding='utf-8') as fh:
                fh.write(line)
        except OSError as exc:
            self.log('写入提炼审计日志失败: %s', type(exc).__name__)

    def _state(self):
        try:
            with open(self.state_path, 'r', encoding='utf-8') as fh:
                raw = json.load(fh)
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, **fields):
        state = self._state()
        state.update(fields)
        state['version'] = 1
        try:
            path = Path(self.state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(path) + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as fh:
                json.dump(state, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError as exc:
            self.log('保存提炼状态失败: %s', type(exc).__name__)

    @property
    def enabled(self):
        return bool(self.cfg.knowledge_enabled and self.cfg.knowledge_auto_extract)

    def status(self):
        state = self._state()
        return {
            'enabled': self.enabled,
            'knowledge_enabled': bool(self.cfg.knowledge_enabled),
            'auto_extract': bool(self.cfg.knowledge_auto_extract),
            'auto_prune': bool(self.cfg.knowledge_auto_prune),
            'interval_minutes': self.cfg.knowledge_extract_interval_minutes,
            'batch': self.cfg.knowledge_extract_batch,
            'max_owners': self.cfg.knowledge_extract_max_owners,
            'min_backlog': self.cfg.knowledge_extract_min_backlog,
            'idle_seconds': self.cfg.knowledge_extract_idle_seconds,
            'next_run_at': state.get('next_run_at'),
            'last_run_at': state.get('last_run_at'),
            'last_report': state.get('last_report') or {},
            'failures': int(state.get('failures') or 0),
            'last_error': state.get('last_error') or '',
            'next_prune_at': state.get('next_prune_at'),
        }

    # ---------- 选人 ----------
    def _pending(self, store, owner=''):
        """有积压的人：游标之后还有至少 min_backlog 条原文。目录已按最近说话排序。"""
        entries = store.owners()[:SCAN_LIMIT]
        if owner:
            entries = [item for item in entries if item['owner'] == owner]
        picked = []
        floor = self.cfg.knowledge_extract_min_backlog
        for entry in entries:
            rows = store.episodes_of(entry['owner'],
                                     after_at=store.extracted_at(entry['owner']),
                                     limit=floor)
            if len(rows) >= floor:
                picked.append(entry)
                if not owner and len(picked) >= self.cfg.knowledge_extract_max_owners:
                    break
        return entries, picked

    # ---------- 提炼 ----------
    def run_once(self, owner='', batch=None, dry_run=False):
        """跑一轮提炼并返回报告。抢不到跨进程锁时返回 locked，不记失败。"""
        store = self.butler.knowledge
        amount = max(1, min(MAX_BATCH, int(batch or self.cfg.knowledge_extract_batch)))
        entries, targets = self._pending(store, owner=owner)
        if not targets:
            return {'ok': True, 'reason': 'no_backlog', 'owners': [], 'batch': amount}
        handle = acquire(self.lock_path)
        if handle is None:
            return {'ok': False, 'reason': 'locked', 'owners': [], 'batch': amount}
        try:
            worker = Contact(name=EXTRACT_WORKER[0],
                             profile=(sorted(self.cfg.contacts.profiles()) or ['default'])[0],
                             uid=EXTRACT_WORKER[1])
            # 每轮清空：提炼用的提示词自带全部上下文，不靠会话历史。
            self.butler.hermes.reset(worker, session_kind='extract')
            report = []
            for entry in targets:
                try:
                    read, written, parsed = extract(
                        store, entry['owner'], entry['contact'],
                        lambda prompt: self.butler.hermes.chat(worker, prompt, session_kind='extract'),
                        batch=amount, log=self.log, dry_run=dry_run)
                except Exception as exc:            # 一个人出错不中断整轮
                    self.log('[%s] 提炼失败：%s', entry['owner'], type(exc).__name__)
                    report.append({'owner': entry['owner'], 'contact': entry['contact'],
                                   'read': 0, 'written': 0, 'parsed': 0,
                                   'error': type(exc).__name__})
                    continue
                report.append({'owner': entry['owner'], 'contact': entry['contact'],
                               'read': read, 'written': written, 'parsed': parsed})
            return {'ok': True, 'owners': report, 'batch': amount,
                    'dry_run': bool(dry_run), 'scanned': len(entries)}
        finally:
            release(handle)

    def _record(self, report, source):
        """把一轮结果写进状态与审计：成功清零失败计数，失败按指数退避。"""
        now = time.time()
        interval = self.cfg.knowledge_extract_interval_minutes * 60
        rows = report.get('owners') or []
        failed = [row for row in rows if row.get('error')]
        if report.get('reason') == 'locked':
            self._audit('skipped', source=source, reason='locked')
            self._save(next_run_at=now + interval)
            return
        if report.get('reason') == 'no_backlog':
            self._audit('skipped', source=source, reason='no_backlog')
            self._save(next_run_at=now + interval, last_run_at=now)
            return
        if failed:
            failures = int(self._state().get('failures') or 0) + 1
            delay = min(MAX_BACKOFF_SECONDS,
                        self.cfg.knowledge_extract_retry_minutes * 60 * (2 ** (failures - 1)))
            self._audit('error', source=source, failures=failures,
                        error=','.join(str(row.get('error')) for row in failed))
            self._save(last_run_at=now, next_run_at=now + delay, failures=failures,
                       last_error=str(failed[0].get('error') or ''), last_report=report)
            self.log('知识提炼失败：%s（%d 次，%.0f 分钟后重试）',
                     failed[0].get('error'), failures, delay / 60)
            return
        total = sum(int(row.get('written') or 0) for row in rows)
        self._audit('extracted', source=source, owners=len(rows), written=total,
                    read=sum(int(row.get('read') or 0) for row in rows))
        self._save(last_run_at=now, next_run_at=now + interval, failures=0,
                   last_error='', last_report=report)
        if rows:
            self.log('知识提炼完成：%d 人，写入 %d 条事实', len(rows), total)

    # ---------- 清理 ----------
    def _prune_due(self):
        if not self.cfg.knowledge_auto_prune:
            return False
        return time.time() >= float(self._state().get('next_prune_at') or 0)

    def _prune(self):
        """过期原文按天清一次；节点是事实，不参与过期（见 KnowledgeStore.prune）。"""
        handle = acquire(self.lock_path)
        if handle is None:
            return
        try:
            deleted = self.butler.knowledge.prune()
        except Exception as exc:
            self._audit('error', source='scheduled', phase='prune', error=type(exc).__name__)
            self.log('知识库清理失败：%s', type(exc).__name__)
            return
        finally:
            release(handle)
        self._audit('pruned', deleted=deleted,
                    retention_days=self.cfg.knowledge_retention_days)
        self._save(next_prune_at=time.time() + self.cfg.knowledge_prune_interval_hours * 3600)
        if deleted:
            self.log('知识库清理：删除 %d 条过期原文', deleted)

    # ---------- 调度 ----------
    def _round(self):
        if not self._running.acquire(blocking=False):
            return
        try:
            owners = self.butler.knowledge.owners()
            newest = max([float(item.get('last_at') or 0) for item in owners] or [0])
            idle = min(MAX_IDLE_SECONDS, int(self.cfg.knowledge_extract_idle_seconds))
            if idle and owners and time.time() - newest < idle:
                # 正在聊天就让路：模型调用几十秒，不该和回复抢上游配额。
                self._audit('deferred', reason='recent_activity', idle_seconds=idle)
                self._save(next_run_at=time.time() + DEFER_SECONDS)
                return
            self._record(self.run_once(), source='scheduled')
            if self._prune_due():
                self._prune()
        finally:
            self._running.release()

    def _loop(self):
        interval = self.cfg.knowledge_extract_interval_minutes * 60
        due = float(self._state().get('next_run_at') or 0)
        if due <= time.time():
            due = time.time() + interval
            self._save(next_run_at=due)
        self._audit('scheduler_started', next_run_at=due)
        self.log('知识提炼已启用：每 %d 分钟扫一次，一批 %d 条，最多 %d 人',
                 self.cfg.knowledge_extract_interval_minutes,
                 self.cfg.knowledge_extract_batch,
                 self.cfg.knowledge_extract_max_owners)
        while not self._stop.is_set():
            if self._stop.wait(max(0.0, due - time.time())):
                break
            try:
                self._round()
            except Exception as exc:                # 调度轮次异常不能带走线程
                self._audit('error', source='scheduled', phase='round',
                            error=type(exc).__name__)
                self.log('知识提炼调度轮次异常: %s', type(exc).__name__)
                self._save(next_run_at=time.time() + interval)
            due = float(self._state().get('next_run_at') or 0) or (time.time() + interval)
        self._audit('scheduler_stopped')

    def start(self):
        if not self.cfg.knowledge_enabled:
            self.log('知识提炼未启动：knowledge.enabled=false')
            return
        if not self.cfg.knowledge_auto_extract:
            self.log('知识提炼未启动：knowledge.auto_extract=false（可手动 python -m butler knowledge-extract）')
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='butler-knowledge-extract',
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    # ---------- 手动触发 ----------
    def trigger(self, owner='', batch=None, dry_run=False):
        """立即跑一轮，后台线程执行，不阻塞 HTTP 请求。"""
        if not self._running.acquire(blocking=False):
            return False, 'busy'
        ready = threading.Event()

        def job():
            try:
                ready.wait()
                report = self.run_once(owner=owner, batch=batch, dry_run=dry_run)
                if dry_run:
                    return                      # 空跑不留状态，避免污染下次计划时间
                self._record(report, source='manual')
            except Exception as exc:
                self._audit('error', source='manual', error=type(exc).__name__)
                self.log('手动提炼失败: %s', type(exc).__name__)
            finally:
                self._running.release()

        try:
            threading.Thread(target=job, name='butler-knowledge-extract-manual',
                             daemon=True).start()
        except Exception:
            self._running.release()
            return False, 'start_failed'
        self._audit('manual_trigger_requested', owner=owner, dry_run=bool(dry_run))
        ready.set()
        return True, 'started'
