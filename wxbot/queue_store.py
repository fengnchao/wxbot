"""SQLite 收件箱、合并批次和发件箱。所有事务短小，模型/UI 操作不持有数据库锁。"""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

FAILURE_TIMEOUT_SECONDS = 180
_UNSET = object()
FAILURE_DETAIL_FIELDS = {'phase','expected_contact','actual_contact','expected_group','actual_group',
    'expected_hwnd','foreground_hwnd','input_focused','target_matches','characters_entered',
    'enter_attempted','clipboard_write','clipboard_committed','clipboard_checked'}


def queue_database(cfg):
    from .config import ROOT
    value = str(cfg.get("queue", {}).get("database", "cache/wxbot_queue.sqlite3"))
    if value == ":memory:":
        return value
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


@dataclass(frozen=True)
class Incoming:
    text: str
    member_key: str = ""
    context: str = ""


@dataclass(frozen=True)
class Batch:
    id: str
    contact: str
    text: str
    context: str


@dataclass(frozen=True)
class Delivery:
    id: str
    contact: str
    text: str
    batch_id: str | None = None
    group_mode: bool | None = None
    part_seq: int = 1
    part_count: int = 1


class QueueStore:
    def __init__(self, path, *, access="runtime"):
        from . import queue_schema
        if access not in {"runtime", "readonly", "admin"}:
            raise ValueError("无效队列访问模式")
        self.path, self.access = str(path), access
        self._lock = threading.RLock()
        self._owner_file = self._db = None
        try:
            if access == "runtime":
                if self.path != ":memory:":
                    Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                self.acquire_runtime()  # Must precede connection, PRAGMA and every DDL.
                self._db = sqlite3.connect(self.path, timeout=5, check_same_thread=False)
            else:
                if self.path == ":memory:":
                    raise ValueError("管理访问需要现有数据库文件")
                uri = Path(self.path).resolve().as_uri() + ("?mode=ro" if access == "readonly" else "?mode=rw")
                self._db = sqlite3.connect(uri, uri=True, timeout=5, check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            if access == "runtime":
                self._db.execute("PRAGMA journal_mode=WAL")
                self._db.execute("PRAGMA synchronous=FULL")
                self._db.execute("PRAGMA foreign_keys=ON")
                queue_schema.initialize(self._db)
            elif access == "admin" and not queue_schema.is_latest(self._db):
                raise ValueError("旧队列需要升级：先停止旧 wxbot，再启动新版；管理命令不会迁移")
        except BaseException:
            self.close()
            raise

    @contextmanager
    def _transaction(self):
        if self.access == "readonly":
            raise ValueError("只读队列不能修改任务")
        with self._lock:
            with self._db:
                self._db.execute("BEGIN IMMEDIATE")
                yield self._db

    def acquire_runtime(self):
        """UI 收发仅允许一个运行实例；管理命令只读数据库，不占此运行锁。"""
        if self.access != "runtime":
            raise RuntimeError("管理访问不能占用运行锁")
        if self.path == ":memory:" or self._owner_file is not None:
            return
        fh = open(self.path + ".lock", "a+b")
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
        fh.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise RuntimeError("另一个 wxbot 正在使用此队列，不能重复启动") from exc
        self._owner_file = fh

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
            if self._owner_file is not None:
                self._owner_file.close()
                self._owner_file = None

    def remember_session(self, contact, unread_count, mentioned, *, now):
        with self._transaction() as db:
            db.execute("""INSERT INTO pending_sessions VALUES(?,?,?,?)
                ON CONFLICT(contact) DO UPDATE SET
                unread_count=MAX(unread_count,excluded.unread_count),
                mentioned=MAX(mentioned,excluded.mentioned),
                updated_at=CASE WHEN excluded.unread_count>unread_count OR excluded.mentioned>mentioned
                    THEN excluded.updated_at ELSE updated_at END""",
                       (contact, unread_count, int(mentioned), now))

    def pending_sessions(self):
        with self._lock:
            return [dict(row) for row in self._db.execute(
                "SELECT * FROM pending_sessions ORDER BY updated_at,contact")]

    def snapshots(self):
        with self._lock:
            return {row["contact"]: (json.loads(row["snapshot"]), bool(row["group_mode"]))
                    for row in self._db.execute("SELECT * FROM observations")}

    def capture(self, contact, snapshot, messages, *, group_mode=False, now):
        ids = []
        with self._transaction() as db:
            pending = db.execute("SELECT updated_at FROM pending_sessions WHERE contact=?", (contact,)).fetchone()
            received_at = min(now, pending[0]) if pending else now
            for message in messages:
                cursor = db.execute("""INSERT INTO inbox
                    (contact,text,member_key,context,group_mode,received_at) VALUES(?,?,?,?,?,?)""",
                    (contact, message.text, message.member_key, message.context, int(group_mode), received_at))
                ids.append(cursor.lastrowid)
            db.execute("""INSERT INTO observations VALUES(?,?,?,?)
                ON CONFLICT(contact) DO UPDATE SET snapshot=excluded.snapshot,
                group_mode=excluded.group_mode,updated_at=excluded.updated_at""",
                       (contact, json.dumps(snapshot, ensure_ascii=False), int(group_mode), now))
            db.execute("DELETE FROM pending_sessions WHERE contact=?", (contact,))
        return ids

    @staticmethod
    def _candidate(rows, quiet, max_wait, prefix):
        first = rows[0]
        deadline = first["received_at"] + max_wait
        selected = []
        due = first["received_at"]
        for row in rows:
            command = bool(prefix) and row["text"].lstrip().startswith(prefix)
            if selected and (command or row["member_key"] != first["member_key"]):
                due = min(due, row["received_at"])
                break
            if selected and row["received_at"] > due:
                break
            selected.append(row)
            due = min(row["received_at"] + quiet, deadline)
            if command:
                due = row["received_at"]
                break
        return due, selected

    def prepare(self, *, quiet, max_wait, prefix, now):
        with self._transaction() as db:
            contacts = db.execute("""SELECT contact FROM inbox WHERE batch_id IS NULL
                GROUP BY contact ORDER BY MIN(id)""").fetchall()
            candidates = []
            for (contact,) in contacts:
                busy = db.execute("SELECT 1 FROM batches WHERE contact=? AND state!='done' LIMIT 1",
                                  (contact,)).fetchone()
                outgoing = db.execute("""SELECT 1 FROM outbox WHERE contact=?
                    AND state NOT IN ('sent','skipped') LIMIT 1""", (contact,)).fetchone()
                unread = db.execute("SELECT 1 FROM pending_sessions WHERE contact=?", (contact,)).fetchone()
                if busy or outgoing or unread:
                    continue
                rows = db.execute("""SELECT * FROM inbox WHERE contact=? AND batch_id IS NULL
                    ORDER BY id""", (contact,)).fetchall()
                due, selected = self._candidate(rows, quiet, max_wait, prefix)
                if due <= now:
                    candidates.append((due, selected[0]["id"], selected))
            for _, _, selected in sorted(candidates, key=lambda item: item[:2]):
                batch_id = uuid.uuid4().hex
                first = selected[0]
                db.execute("""INSERT INTO batches(id,contact,text,context,state,created_at)
                    VALUES(?,?,?,?,'ready',?)""",
                    (batch_id, first["contact"], "\n".join(row["text"] for row in selected),
                     first["context"], now))
                db.executemany("UPDATE inbox SET batch_id=? WHERE id=?",
                               [(batch_id, row["id"]) for row in selected])
        return len(candidates)

    def claim_batch(self, *, now):
        with self._transaction() as db:
            row = db.execute("SELECT * FROM batches WHERE state='ready' ORDER BY seq LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("""UPDATE batches SET state='processing',started_at=?,attempts=attempts+1
                WHERE id=?""", (now, row["id"]))
            return Batch(row["id"], row["contact"], row["text"], row["context"])

    @staticmethod
    def _insert_delivery(db, contact, text, now, not_before, batch_id=None, part_seq=1):
        delivery_id = f"{batch_id}:{part_seq}" if batch_id else uuid.uuid4().hex
        db.execute("""INSERT INTO outbox(id,contact,text,batch_id,state,created_at,not_before,part_seq)
            VALUES(?,?,?,?,'pending',?,?,?)""",
                   (delivery_id, contact, text, batch_id, now, not_before, part_seq))
        return delivery_id

    def release_unsubmitted_batch(self, batch_id):
        """Shutdown raced with claim, but no backend call began: safe to leave ready."""
        with self._transaction() as db:
            db.execute("""UPDATE batches SET state='ready',started_at=NULL,attempts=MAX(0,attempts-1)
                WHERE id=? AND state='processing' AND reply_complete=0 AND NOT EXISTS
                (SELECT 1 FROM outbox WHERE batch_id=batches.id)""", (batch_id,))

    def finish_batch(self, batch_id, reply, *, now, delay=0):
        parts = (reply,) if isinstance(reply, str) and reply.strip() else ()
        return self.finish_batch_parts(batch_id, parts, now=now, delay=delay, reply_text=reply)

    def finish_batch_parts(self, batch_id, parts, *, now, delay=0, reply_text=None):
        if not isinstance(parts, tuple) or any(not isinstance(p, str) or not p.strip() for p in parts):
            raise ValueError("分句必须是完整的非空字符串元组")
        with self._transaction() as db:
            row = db.execute("SELECT * FROM batches WHERE id=? AND state='processing'",
                             (batch_id,)).fetchone()
            if row is None:
                raise ValueError("批次不处于处理中，不能重复保存模型结果")
            for n, part in enumerate(parts, 1):
                self._insert_delivery(db, row["contact"], part, now, now + delay, batch_id, n)
            db.execute("""UPDATE batches SET reply_text=?,reply_complete=1,part_count=? WHERE id=?""",
                       (reply_text if reply_text is not None else ''.join(parts), len(parts), batch_id))
            self._recompute_batch(db, batch_id, now)

    @staticmethod
    def _recompute_batch(db, batch_id, now=None):
        if batch_id is None:
            return
        batch = db.execute('SELECT reply_complete FROM batches WHERE id=?', (batch_id,)).fetchone()
        if batch is None or not batch[0]:
            return  # Unknown model result must remain uncertain/processing.
        states = {r[0] for r in db.execute('SELECT state FROM outbox WHERE batch_id=?', (batch_id,))}
        state = ('done' if states <= {'sent','skipped'} else 'uncertain' if 'uncertain' in states
                 else 'blocked' if 'blocked' in states else 'waiting_delivery')
        db.execute("""UPDATE batches SET state=?,finished_at=CASE WHEN ?='done'
            THEN COALESCE(finished_at,?) ELSE NULL END WHERE id=?""", (state,state,now,batch_id))

    @staticmethod
    def _advance_turn(db, contact):
        next_turn = db.execute('SELECT COALESCE(MAX(last_turn),0)+1 FROM delivery_turns').fetchone()[0]
        db.execute("""INSERT INTO delivery_turns VALUES(?,?) ON CONFLICT(contact)
            DO UPDATE SET last_turn=excluded.last_turn""", (contact,next_turn))

    def fail_batch(self, batch_id, error):
        with self._transaction() as db:
            db.execute("UPDATE batches SET state='uncertain',error=?,finished_at=? WHERE id=?",
                       (error,time.time(),batch_id))

    def enqueue_delivery(self, contact, text, *, now):
        with self._transaction() as db:
            return self._insert_delivery(db, contact, text, now, now)

    _DELIVERY_CANDIDATE = """SELECT o.*,
        COALESCE(b.part_count,1) AS part_count FROM outbox o
        LEFT JOIN batches b ON b.id=o.batch_id
        LEFT JOIN delivery_turns t ON t.contact=o.contact
        WHERE o.state='pending' AND o.not_before<=?
        AND NOT EXISTS(SELECT 1 FROM outbox older WHERE older.contact=o.contact
            AND older.seq<o.seq AND older.state NOT IN ('sent','skipped'))
        ORDER BY COALESCE(t.last_turn,0),o.seq LIMIT 1"""

    def has_ready_delivery(self, *, now):
        with self._lock:
            return self._db.execute(self._DELIVERY_CANDIDATE, (now,)).fetchone() is not None

    def claim_delivery(self, *, now):
        with self._transaction() as db:
            row = db.execute(self._DELIVERY_CANDIDATE, (now,)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE outbox SET state='sending' WHERE id=?", (row["id"],))
            kind = (db.execute("SELECT group_mode FROM inbox WHERE batch_id=? LIMIT 1", (row["batch_id"],)).fetchone()
                    if row["batch_id"] else None)
            if kind is None:
                kind = db.execute("SELECT group_mode FROM observations WHERE contact=?", (row["contact"],)).fetchone()
            return Delivery(row["id"], row["contact"], row["text"], row["batch_id"],
                            bool(kind[0]) if kind is not None else None, row['part_seq'], row['part_count'])

    def save_baseline(self, delivery_id, snapshot, *, submitted_text=None):
        with self._transaction() as db:
            db.execute("UPDATE outbox SET baseline=?,submitted_text=? WHERE id=?",
                       (json.dumps(snapshot, ensure_ascii=False), submitted_text, delivery_id))

    def record_submitted_text(self, delivery_id, text, *, user_confirmed=False):
        """记录已核对的实际输入；旧异常任务仅在用户确认已发送后登记，暂不释放队列。"""
        if not isinstance(text, str) or not text:
            raise ValueError("实际输入正文不能为空")
        with self._transaction() as db:
            row = db.execute("SELECT state FROM outbox WHERE id=?", (delivery_id,)).fetchone()
            allowed = {"uncertain"} if user_confirmed else {"sending", "confirming"}
            if row is None or row[0] not in allowed:
                raise ValueError("当前发件状态不允许登记实际输入")
            db.execute("UPDATE outbox SET submitted_text=? WHERE id=?", (text, delivery_id))
            if user_confirmed:
                db.execute("UPDATE outbox SET error=? WHERE id=?",
                           ("用户已确认实际发出；重启后只读核对，不重发", delivery_id))

    def confirming(self, delivery_id, *, now):
        with self._transaction() as db:
            db.execute("UPDATE outbox SET state='confirming',submitted_at=? WHERE id=?", (now, delivery_id))

    @staticmethod
    def _event(db,row,action,now,state,reason,details=None,*,kind='outbox',source='wxbot'):
        safe={k:(v[:256] if isinstance(v,str) else v) for k,v in (details or {}).items()
              if k in FAILURE_DETAIL_FIELDS and (v is None or isinstance(v,(str,int,float,bool)))}
        db.execute('''INSERT INTO delivery_events(record_id,record_kind,contact,action,at,state,reason,details,source)
            VALUES(?,?,?,?,?,?,?,?,?)''',(row['id'],kind,row['contact'],action,now,state,reason,
                                         json.dumps(safe,ensure_ascii=False),source))

    def delivery_events(self, *, contact='', limit=100):
        with self._lock:
            where=' WHERE contact=?' if contact else ''
            args=[contact] if contact else []
            rows=self._db.execute('SELECT * FROM delivery_events'+where+' ORDER BY seq DESC LIMIT ?',
                                  [*args,max(1,min(200,int(limit)))]).fetchall()
            return [{**dict(row),'details':json.loads(row['details'])} for row in reversed(rows)]

    def finish_delivery(self, delivery_id, state, *, now, error="", details=None):
        if state not in {"sent", "skipped", "blocked", "uncertain"}:
            raise ValueError("无效的发送状态")
        with self._transaction() as db:
            row = db.execute('SELECT * FROM outbox WHERE id=?', (delivery_id,)).fetchone()
            if row is None or row['state'] in {'sent','skipped'}:
                return
            failure=state in {'blocked','uncertain'}
            db.execute("""UPDATE outbox SET state=?,finished_at=?,error=?,
                failed_at=CASE WHEN ? THEN COALESCE(failed_at,?) ELSE failed_at END,
                resolution=? WHERE id=?""",
                (state,now,error,failure,now,'sent' if state=='sent' else '',delivery_id))
            if failure:
                self._event(db,row,'failed',now,state,error,details)
            if state in {'sent','skipped'}:
                self._advance_turn(db, row['contact'])
            self._recompute_batch(db, row['batch_id'], now)

    def expire_failed_deliveries(self, *, now):
        with self._transaction() as db:
            rows=db.execute("""SELECT * FROM outbox WHERE state IN ('blocked','uncertain')
                AND failed_at IS NOT NULL AND failed_at<=? ORDER BY seq""",
                (now-FAILURE_TIMEOUT_SECONDS,)).fetchall()
            expired=[]
            for row in rows:
                reason='发送失败满180秒，自动丢弃；原失败原因：'+(row['error'] or '未记录')
                db.execute("UPDATE outbox SET state='skipped',resolution='timeout',finished_at=?,error=? WHERE id=?",
                           (now,reason,row['id']))
                self._event(db,row,'timeout_discard',now,'skipped',reason)
                self._advance_turn(db,row['contact'])
                self._recompute_batch(db,row['batch_id'],now)
                expired.append({**dict(row),'state':'skipped','error':reason,'resolution':'timeout'})
            return expired

    def recover(self, *, now=None):
        now=time.time() if now is None else now
        with self._transaction() as db:
            models = db.execute("""UPDATE batches SET state='uncertain',error='进程中断，模型结果未知',finished_at=?
                WHERE state='processing'""",(now,)).rowcount
            interrupted=db.execute("SELECT * FROM outbox WHERE state IN ('sending','confirming')").fetchall()
            deliveries = db.execute("""UPDATE outbox SET state='uncertain',error='进程中断，发送结果需核对',
                failed_at=COALESCE(failed_at,?),finished_at=?
                WHERE state IN ('sending','confirming')""",(now,now)).rowcount
            for row in interrupted:
                self._event(db,row,'failed',now,'uncertain','进程中断，发送结果需核对',{'phase':'recovery'})
            for row in db.execute("SELECT id FROM batches WHERE reply_complete=1").fetchall():
                self._recompute_batch(db, row[0])
            return {"models_uncertain": models, "deliveries_uncertain": deliveries}

    def records(self, table, *, limit=None):
        order = {"inbox": "id", "batches": "seq", "outbox": "seq"}.get(table)
        if order is None:
            raise ValueError("未知队列表")
        with self._lock:
            sql = f"SELECT * FROM {table} ORDER BY {order}"
            if limit is not None:
                return [self._record(table, row) for row in self._db.execute(sql + " LIMIT ?", (int(limit),))]
            return [self._record(table, row) for row in self._db.execute(sql)]

    def _record(self, table, row):
        result = dict(row)
        if table == 'outbox':
            result.setdefault('part_seq', 1)
            result['part_count'] = (self._db.execute('SELECT COUNT(*) FROM outbox WHERE batch_id=?',
                                                  (result['batch_id'],)).fetchone()[0]
                                    if result.get('batch_id') else 1)
            result.setdefault('submitted_text', None)
        elif table == 'batches':
            count = self._db.execute('SELECT COUNT(*) FROM outbox WHERE batch_id=?', (result['id'],)).fetchone()[0]
            result.setdefault('part_count', count)
            result.setdefault('reply_complete', int(result['state']=='done' or count>0))
            result['completed_parts'] = self._db.execute("""SELECT COUNT(*) FROM outbox
                WHERE batch_id=? AND state IN ('sent','skipped')""", (result['id'],)).fetchone()[0]
        return result

    def _get(self, table, record_id):
        with self._lock:
            row = self._db.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
            return self._record(table, row) if row else None

    def get_batch(self, batch_id):
        return self._get("batches", batch_id)

    def get_delivery(self, delivery_id):
        return self._get("outbox", delivery_id)

    def counts(self):
        with self._lock:
            result = {"unbatched": self._db.execute(
                "SELECT COUNT(*) FROM inbox WHERE batch_id IS NULL").fetchone()[0],
                "pending_sessions": self._db.execute("SELECT COUNT(*) FROM pending_sessions").fetchone()[0]}
            for table in ("batches", "outbox"):
                result[table] = dict(self._db.execute(f"SELECT state,COUNT(*) FROM {table} GROUP BY state"))
            return result

    @staticmethod
    def _check_action(row,contact,expected_state,expected_finished_at,expected_attempts):
        if contact is not None and row['contact']!=contact:
            raise ValueError('任务联系人不匹配，请刷新队列')
        if expected_state is not None and row['state']!=expected_state:
            raise ValueError('任务状态已变化，请刷新队列')
        if expected_finished_at is not _UNSET and row['finished_at']!=expected_finished_at:
            raise ValueError('任务已更新，请刷新队列后核对')
        if expected_attempts is not _UNSET and row['attempts']!=expected_attempts:
            raise ValueError('任务执行次数已变化，请刷新队列后核对')

    def retry(self, record_id, *, delivery=False, contact=None, expected_state=None,
              expected_finished_at=_UNSET,expected_attempts=_UNSET,source='cli',now=None):
        now=time.time() if now is None else now
        with self._transaction() as db:
            table = "outbox" if delivery else "batches"
            row = db.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
            if row is None or row["state"] not in {"blocked", "uncertain"}:
                raise ValueError("只允许显式重试 blocked/uncertain 任务")
            self._check_action(row,contact,expected_state,expected_finished_at,expected_attempts)
            if not delivery and db.execute("SELECT 1 FROM outbox WHERE batch_id=?", (record_id,)).fetchone():
                raise ValueError("模型已有回复，请处理对应发件任务，不能重跑模型")
            if delivery:
                db.execute("""UPDATE outbox SET state='pending',error='',resolution='',baseline=NULL,
                    submitted_at=NULL,submitted_text=NULL,finished_at=NULL WHERE id=?""", (record_id,))
                self._recompute_batch(db, row["batch_id"])
            else:
                db.execute("""UPDATE batches SET state='ready',error='',started_at=NULL,
                    finished_at=NULL WHERE id=?""", (record_id,))
            reason='人工核对后重试；原状态：'+row['state']+'；原失败原因：'+(row['error'] or '未记录')
            self._event(db,row,'retry',now,'pending' if delivery else 'ready',reason,
                        kind=table,source=source)

    def resolve(self, record_id, *, delivery=False, sent=False, now,contact=None,expected_state=None,
                expected_finished_at=_UNSET,expected_attempts=_UNSET,source='cli'):
        """人工核对后结束异常任务；不允许更改正在执行的任务。"""
        if sent and not delivery:
            raise ValueError("只有发件任务能标记已发送")
        with self._transaction() as db:
            table = "outbox" if delivery else "batches"
            row = db.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)).fetchone()
            if row is None or row["state"] not in {"blocked", "uncertain"}:
                raise ValueError("只允许人工处理 blocked/uncertain 任务")
            self._check_action(row,contact,expected_state,expected_finished_at,expected_attempts)
            if delivery:
                db.execute("UPDATE outbox SET state=?,finished_at=?,error=?,resolution=? WHERE id=?",
                           ("sent" if sent else "skipped", now, "人工核对结束",
                            'manual_sent' if sent else 'manual_skip',record_id))
                self._advance_turn(db, row["contact"])
                self._recompute_batch(db, row["batch_id"], now)
            else:
                if db.execute("SELECT 1 FROM outbox WHERE batch_id=?", (record_id,)).fetchone():
                    raise ValueError("模型已有回复，请处理对应发件任务")
                db.execute("UPDATE batches SET state='done',finished_at=?,error=? WHERE id=?",
                           (now, "人工跳过", record_id))
            reason='人工核对结束；原状态：'+row['state']+'；原失败原因：'+(row['error'] or '未记录')
            self._event(db,row,'confirm_sent' if sent else 'manual_discard',now,
                        'sent' if sent else 'skipped' if delivery else 'done',reason,
                        kind=table,source=source)
