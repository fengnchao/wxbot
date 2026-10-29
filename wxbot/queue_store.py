"""SQLite 收件箱、合并批次和发件箱。所有事务短小，模型/UI 操作不持有数据库锁。"""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from .config import validate_failure_timeout
from .delivery_policy import DeliveryPolicy

FAILURE_TIMEOUT_SECONDS = 180
RETRY_DELAY_SECONDS = 20
MAX_DELIVERY_RETRIES = 2
_UNSET = object()
FAILURE_DETAIL_FIELDS = {'phase','expected_contact','actual_contact','expected_group','actual_group',
    'expected_hwnd','foreground_hwnd','input_focused','target_matches','characters_entered',
    'enter_attempted','clipboard_write','clipboard_committed','clipboard_checked',
    'clipboard_operation','clipboard_format','clipboard_error','os_error_code','exception_type',
    'manual_required','retry_safe','attempt','max_attempts','retry_at','error_code',
    'mention_verified','mention_fallback','bubble_verified'}


def queue_database(cfg):
    from .config import ROOT
    value = str(cfg.get("queue", {}).get("database", "cache/wxbot_queue.sqlite3"))
    if value == ":memory:":
        return value
    path = Path(value)
    base = Path(cfg["_config_path"]).parent if cfg.get("_config_path") else ROOT
    return path if path.is_absolute() else base / path


@dataclass(frozen=True)
class Incoming:
    text: str
    member_key: str = ""
    context: str = ""
    member_name: str = ""
    reply_mode: str = "text"   # text=文字回复 / emoji=表情图 / none=静默（已进上下文不回复）
    avatar: str = ""
    reply_reason: str = ""


@dataclass(frozen=True)
class Batch:
    id: str
    contact: str
    text: str
    context: str
    member_key: str = ""
    member_name: str = ""
    reply_mode: str = "text"
    avatar: str = ""
    reply_reason: str = ""


REPLY_MODE_PRIORITY = ("text", "emoji", "none")


def merge_reply_mode(rows):
    """合并批次时取优先级最高的回复方式：文字 > 表情 > 静默。"""
    modes = {row["reply_mode"] for row in rows}
    for mode in REPLY_MODE_PRIORITY:
        if mode in modes:
            return mode
    return "text"


@dataclass(frozen=True)
class Delivery:
    id: str
    contact: str
    text: str
    batch_id: str | None = None
    group_mode: bool | None = None
    part_seq: int = 1
    part_count: int = 1
    kind: str = "text"
    mention_name: str = ""
    package_id: str | None = None
    media_id: str = ''
    media_path: str = ''


class QueueStore(DeliveryPolicy):
    def __init__(self, path, *, access="runtime", failure_timeout_seconds=FAILURE_TIMEOUT_SECONDS,
                 retry_delay_seconds=RETRY_DELAY_SECONDS, max_delivery_retries=MAX_DELIVERY_RETRIES, restart_chat_policy='discard', directory_path=None):
        from . import queue_schema
        if access not in {"runtime", "readonly", "admin"}:
            raise ValueError("无效队列访问模式")
        if restart_chat_policy not in {'discard', 'resume'}:
            raise ValueError('无效的聊天重启恢复策略')
        from butler.directory import DirectoryStore
        self.directory = DirectoryStore(directory_path) if directory_path else None
        self.restart_chat_policy = restart_chat_policy
        self.failure_timeout_seconds = validate_failure_timeout(failure_timeout_seconds)
        self.retry_delay_seconds = float(retry_delay_seconds)
        self.max_delivery_retries = int(max_delivery_retries)
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
            if access != 'readonly':
                self._db.execute('PRAGMA foreign_keys=ON')
            if access == "runtime":
                queue_schema.backup_before_migration(self._db, self.path)
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

    def group_member_name(self, contact, member_key):
        if self.directory is not None:
            return self.directory.member_name(contact, member_key)
        with self._lock:
            row = self._db.execute(
                "SELECT name FROM group_member_names WHERE contact=? AND member_key=?",
                (contact, member_key)).fetchone()
            return row[0] if row else ""

    def group_observations(self, batch_id):
        """Original public observations, in capture order, before batch merging."""
        with self._lock:
            return [dict(row) for row in self._db.execute(
                'SELECT text,member_key,member_name,avatar FROM inbox '
                'WHERE batch_id=? AND group_mode=1 ORDER BY id', (batch_id,))]

    def identity_observations(self):
        """Bounded latest captured avatar evidence; no historical message bodies."""
        with self._lock:
            return [dict(row) for row in self._db.execute('''
                SELECT contact,group_mode,member_key,member_name,avatar FROM inbox
                WHERE id IN (SELECT MAX(id) FROM inbox WHERE avatar!=''
                    GROUP BY contact,group_mode,member_key)
                ORDER BY id DESC LIMIT 500''')]

    def remember_group_member(self, contact, member_key, name, *, now):
        if self.directory is not None:
            self.directory.observe_member(contact, member_key, name)
            return
        with self._transaction() as db:
            db.execute("""INSERT INTO group_member_names VALUES(?,?,?,?)
                ON CONFLICT(contact,member_key) DO UPDATE SET name=excluded.name,updated_at=excluded.updated_at""",
                (contact, member_key, name, now))

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
                    (contact,text,member_key,member_name,reply_mode,context,group_mode,received_at,avatar,reply_reason) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (contact, message.text, message.member_key, message.member_name,
                     message.reply_mode, message.context, int(group_mode), received_at, message.avatar, message.reply_reason))
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
                    AND detached=0 AND state NOT IN ('sent','skipped') LIMIT 1""", (contact,)).fetchone()
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
                reply_mode = merge_reply_mode(selected)
                reason = next((row['reply_reason'] for row in selected if row['reply_mode'] == reply_mode), '')
                db.execute("""INSERT INTO batches(id,contact,text,context,member_key,member_name,reply_mode,state,created_at,avatar,reply_reason)
                    VALUES(?,?,?,?,?,?,?,'ready',?,?,?)""",
                    (batch_id, first["contact"], "\n".join(row["text"] for row in selected),
                     first["context"], first["member_key"] or "", first["member_name"] or "",
                     reply_mode, now, first['avatar'], reason))
                db.executemany("UPDATE inbox SET batch_id=? WHERE id=?",
                               [(batch_id, row["id"]) for row in selected])
        return len(candidates)

    def claim_batch(self, *, now):
        with self._transaction() as db:
            self._recover_model_failures(db,now)
            row = db.execute("SELECT * FROM batches WHERE state='ready' ORDER BY seq LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("""UPDATE batches SET state='processing',started_at=?,finished_at=NULL,attempts=attempts+1
                WHERE id=?""", (now, row["id"]))
            return Batch(row["id"], row["contact"], row["text"], row["context"],
                         row["member_key"] or "", row["member_name"] or "", row["reply_mode"] or "text", row['avatar'], row['reply_reason'])

    @staticmethod
    def _insert_delivery(db, contact, text, now, not_before, batch_id=None, part_seq=1, kind="text", mention_name=""):
        delivery_id = f"{batch_id}:{part_seq}" if batch_id else uuid.uuid4().hex
        db.execute("""INSERT INTO outbox(id,contact,text,batch_id,state,created_at,not_before,part_seq,kind,mention_name)
            VALUES(?,?,?,?,'pending',?,?,?,?,?)""",
                   (delivery_id, contact, text, batch_id, now, not_before, part_seq, kind, mention_name))
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

    def finish_batch_parts(self, batch_id, parts, *, now, delay=0, reply_text=None, mention_name=''):
        if not isinstance(parts, tuple) or any(not isinstance(p, str) or not p.strip() for p in parts):
            raise ValueError("分句必须是完整的非空字符串元组")
        with self._transaction() as db:
            row = db.execute("SELECT * FROM batches WHERE id=? AND state='processing'",
                             (batch_id,)).fetchone()
            if row is None:
                raise ValueError("批次不处于处理中，不能重复保存模型结果")
            # Only the service-resolved target is authority; observed names/hash
            # mappings and text supplied by the model never choose a recipient.
            group = db.execute('SELECT group_mode FROM inbox WHERE batch_id=? LIMIT 1', (batch_id,)).fetchone()
            member_name = str(mention_name or '').strip() if group and group[0] else ''
            for n, part in enumerate(parts, 1):
                self._insert_delivery(db, row["contact"], part, now, now + delay, batch_id, n,
                                      mention_name=member_name if n == 1 else '')
            db.execute("""UPDATE batches SET reply_text=?,reply_complete=1,part_count=?,error='',finished_at=NULL WHERE id=?""",
                       (reply_text if reply_text is not None else ''.join(parts), len(parts), batch_id))
            self._recompute_batch(db, batch_id, now)

    @staticmethod
    def _recompute_batch(db, batch_id, now=None):
        if batch_id is None:
            return
        batch = db.execute('SELECT reply_complete FROM batches WHERE id=?', (batch_id,)).fetchone()
        if batch is None or not batch[0]:
            return  # Unknown model result must remain uncertain/processing.
        states = {r[0] for r in db.execute('SELECT state FROM outbox WHERE batch_id=? AND detached=0', (batch_id,))}
        state = ('done' if states <= {'sent','skipped'} else 'uncertain' if 'uncertain' in states
                 else 'blocked' if 'blocked' in states else 'waiting_delivery')
        db.execute("""UPDATE batches SET state=?,finished_at=CASE WHEN ?='done'
            THEN COALESCE(finished_at,?) ELSE NULL END WHERE id=?""", (state,state,now,batch_id))

    def finish_batch_sticker(self, batch_id, *, now):
        """Keep emoji delivery in its parent's turn until it is confirmed."""
        with self._transaction() as db:
            row = db.execute("SELECT * FROM batches WHERE id=? AND state='processing'",
                             (batch_id,)).fetchone()
            if row is None:
                raise ValueError('批次不处于处理中，不能重复保存回复')
            self._insert_delivery(db, row['contact'], '', now, now, batch_id, 1, kind='emoji')
            db.execute("""UPDATE batches SET reply_text='',reply_complete=1,part_count=1,
                error='',finished_at=NULL WHERE id=?""", (batch_id,))
            self._recompute_batch(db, batch_id, now)

    @staticmethod
    def _advance_turn(db, contact):
        next_turn = db.execute('SELECT COALESCE(MAX(last_turn),0)+1 FROM delivery_turns').fetchone()[0]
        db.execute("""INSERT INTO delivery_turns VALUES(?,?) ON CONFLICT(contact)
            DO UPDATE SET last_turn=excluded.last_turn""", (contact,next_turn))

    def fail_batch(self, batch_id, error, *, now=None, retry_safe=False):
        now=time.time() if now is None else now
        with self._transaction() as db:
            row=db.execute("SELECT * FROM batches WHERE id=? AND state='processing'",(batch_id,)).fetchone()
            if row is None:return
            db.execute("UPDATE batches SET state='uncertain',error=?,finished_at=? WHERE id=?",(error,now,batch_id))
            self._event(db,row,'model_retryable' if retry_safe else 'model_uncertain',now,'uncertain',error,
                        {'retry_safe':retry_safe,'attempt':row['attempts']},kind='batches')

    def recover_model_failures(self, *, now):
        with self._transaction() as db:
            return self._recover_model_failures(db,now)

    def _recover_model_failures(self,db,now):
        from .model_recovery import model_failure_info,MODEL_MAX_ATTEMPTS
        recovered=[]
        rows=db.execute("SELECT * FROM batches WHERE (state IN ('blocked','uncertain') OR (state='ready' AND error!='')) AND reply_complete=0 "
                        "AND NOT EXISTS(SELECT 1 FROM outbox WHERE batch_id=batches.id) ORDER BY seq").fetchall()
        for row in rows:
            info=model_failure_info(db,row,now,self.failure_timeout_seconds)
            if info['auto_action']=='retry' and row['state']!='ready':
                db.execute("UPDATE batches SET state='ready',started_at=NULL WHERE id=?",(row['id'],))
                action='model_retry';reason=f"尚未提交模型，自动重试；已尝试 {row['attempts']}/{MODEL_MAX_ATTEMPTS} 次；原失败原因："+row['error']
            elif info['auto_action']=='abandon':
                cause=f'模型失败满{self.failure_timeout_seconds:g}秒' if now>=info['discard_at'] else f'模型请求已失败{MODEL_MAX_ATTEMPTS}次'
                reason=cause+'，结束失败批次并放行后续消息；原失败原因：'+row['error']
                db.execute("UPDATE batches SET state='done',finished_at=?,error=? WHERE id=?",(now,reason,row['id']))
                action='model_abandoned'
            else:continue
            self._event(db,row,action,now,'ready' if action=='model_retry' else 'done',reason,
                        {'retry_safe':info['retry_safe'],'attempt':row['attempts'],'max_attempts':MODEL_MAX_ATTEMPTS},kind='batches')
            recovered.append({'id':row['id'],'contact':row['contact'],'action':action,'reason':reason})
        return recovered

    @staticmethod
    def _check_outbound_cutoff(db, received_at):
        if received_at is None:
            return
        cutoff = db.execute("SELECT MAX(at) FROM delivery_events WHERE action='delete_unsent'").fetchone()[0]
        if cutoff is not None and received_at <= cutoff:
            raise ValueError('此推送已由用户删除，停止投递')

    def delete_unsent(self, *, now=None, source='log'):
        from .queue_cleanup import delete_unsent
        return delete_unsent(self, now=time.time() if now is None else now, source=source)

    def delete_workflow_history(self,payload,*,now=None):
        from .queue_history import delete
        return delete(self,payload,now=now)

    def enqueue_delivery(self, contact, text, *, now, received_at=None):
        with self._transaction() as db:
            self._check_outbound_cutoff(db, received_at)
            return self._insert_delivery(db, contact, text, now, now)

    def enqueue_package(self, contact, items, request_id, *, media_paths, now, received_at=None):
        """Insert an ordered package in one transaction. Paths are trusted cache outputs only."""
        from common.media_bundle import validate_items, validate_request_id
        items = validate_items(items)
        if not isinstance(contact, str) or not contact.strip() or len(contact) > 256:
            raise ValueError('无效联系人')
        validate_request_id(request_id)
        for item in items:
            if item['kind'] == 'image' and item['media_id'] not in media_paths:
                raise ValueError('图片尚未准备完成')
        payload = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self._transaction() as db:
            self._check_outbound_cutoff(db, received_at)
            prior = db.execute('SELECT id,payload_hash FROM delivery_packages WHERE contact=? AND request_id=?',
                               (contact, request_id)).fetchone()
            if prior:
                if prior['payload_hash'] != digest:
                    raise ValueError('同一包标识不能更改内容')
                return prior['id']
            package_id = uuid.uuid4().hex
            db.execute('INSERT INTO delivery_packages(id,contact,request_id,payload_hash,created_at) VALUES(?,?,?,?,?)',
                       (package_id,contact,request_id,digest,now))
            for seq,item in enumerate(items,1):
                delivery_id = self._insert_delivery(db,contact,item.get('text',''),now,now,
                                                    part_seq=seq,kind=item['kind'])
                media_id = item.get('media_id','')
                db.execute('UPDATE outbox SET package_id=?,media_id=?,media_path=? WHERE id=?',
                           (package_id,media_id,str(media_paths[media_id]) if media_id else '',delivery_id))
            return package_id

    def package_receipt(self, package_id):
        with self._lock:
            package = self._db.execute('SELECT state FROM delivery_packages WHERE id=?',(package_id,)).fetchone()
            if package is None:
                raise ValueError('未知发件包')
            state = package['state']
            return {'done':state != 'pending','ok':state == 'sent','state':state}

    @staticmethod
    def _recompute_package(db,package_id):
        if not package_id:
            return
        current = db.execute('SELECT state FROM delivery_packages WHERE id=?', (package_id,)).fetchone()
        if current is not None and current[0] == 'cancelled':
            return
        states={row[0] for row in db.execute('SELECT state FROM outbox WHERE package_id=?',(package_id,))}
        if states=={'sent'}:
            state='sent'
        elif 'uncertain' in states:
            state='uncertain'
        elif 'blocked' in states:
            state='blocked'
        elif states & {'pending','sending','confirming'}:
            state='pending'
        else:
            state='skipped'
        db.execute('UPDATE delivery_packages SET state=? WHERE id=?',(state,package_id))

    def requires_image_ui_review(self):
        with self._lock:
            return self._db.execute("SELECT 1 FROM outbox WHERE (kind='image' OR package_id IS NOT NULL) AND manual_required=1 LIMIT 1").fetchone() is not None

    def defer_delivery(self,delivery_id,*,now):
        """No UI work has started: yield the claim while background authorization runs."""
        with self._transaction() as db:
            db.execute("""UPDATE outbox SET state='pending',not_before=? WHERE id=? AND state='sending'
                AND baseline IS NULL AND submitted_at IS NULL""",(now+.1,delivery_id))

    @staticmethod
    def _stop_package(db, package_id, state, now):
        db.execute("UPDATE delivery_packages SET state=? WHERE id=? AND state!='cancelled'",(state,package_id))
        db.execute("""UPDATE outbox SET state='skipped',detached=1,finished_at=?,resolution='package_stopped',
            error='图文包未完整确认，停止剩余内容，需人工核对' WHERE package_id=? AND state='pending'""",(now,package_id))

    def enqueue_sticker(self, contact, *, now):
        with self._transaction() as db:
            return self._insert_delivery(db, contact, "", now, now, kind="emoji")

    _DELIVERY_CANDIDATE = """SELECT o.*,
        COALESCE(b.part_count,NULLIF((SELECT COUNT(*) FROM outbox p WHERE p.package_id=o.package_id),0),1) AS part_count FROM outbox o
        LEFT JOIN batches b ON b.id=o.batch_id
        LEFT JOIN delivery_turns t ON t.contact=o.contact
        WHERE o.state='pending' AND o.detached=0 AND o.not_before<=?
        AND NOT EXISTS(SELECT 1 FROM outbox hold WHERE hold.contact=o.contact AND hold.manual_required=1)
        AND NOT EXISTS(SELECT 1 FROM outbox older WHERE older.contact=o.contact
            AND older.seq<o.seq AND older.detached=0 AND older.state NOT IN ('sent','skipped'))
        ORDER BY COALESCE(t.last_turn,0),o.seq LIMIT 1"""

    def has_ready_delivery(self, *, now):
        with self._lock:
            return self._db.execute(self._DELIVERY_CANDIDATE, (now,)).fetchone() is not None

    def claim_delivery(self, *, now):
        with self._transaction() as db:
            self._expire_replies(db, now)
            row = db.execute(self._DELIVERY_CANDIDATE, (now,)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE outbox SET state='sending' WHERE id=?", (row["id"],))
            group_kind = (db.execute("SELECT group_mode FROM inbox WHERE batch_id=? LIMIT 1", (row["batch_id"],)).fetchone()
                        if row["batch_id"] else None)
            if group_kind is None:
                group_kind = db.execute("SELECT group_mode FROM observations WHERE contact=?", (row["contact"],)).fetchone()
            return Delivery(row["id"], row["contact"], row["text"], row["batch_id"],
                            bool(group_kind[0]) if group_kind is not None else None, row['part_seq'], row['part_count'],
                            row["kind"] or "text", row['mention_name'], row['package_id'], row['media_id'], row['media_path'])

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
                if row['package_id']:
                    self._stop_package(db,row['package_id'],state,now)
                    db.execute("UPDATE outbox SET detached=1 WHERE id=?",(delivery_id,))
                if row['batch_id']:
                    db.execute('UPDATE batches SET first_delivery_failure=COALESCE(first_delivery_failure,?) WHERE id=?',
                               (now,row['batch_id']))
                    db.execute('''UPDATE outbox SET failed_at=(SELECT first_delivery_failure FROM batches WHERE id=?)
                        WHERE batch_id=? AND state NOT IN ('sent','skipped')''', (row['batch_id'],row['batch_id']))
                if (details or {}).get('manual_required'):
                    db.execute('UPDATE outbox SET manual_required=1 WHERE id=?',(delivery_id,))
                self._event(db,row,'failed',now,state,error,details)
                if state == 'uncertain':
                    db.execute("UPDATE outbox SET detached=1,resolution='review' WHERE id=?", (delivery_id,))
                    if row['batch_id']:
                        self._end_reply(db,row['batch_id'],now,'发送结果待核对，停止本轮续发并放行后续消息','review')
                    self._advance_turn(db,row['contact'])
            if state == 'sent':
                db.execute('UPDATE outbox SET draft_text=NULL,manual_required=0 WHERE id=?',(delivery_id,))
                if details and ('mention_verified' in details or 'bubble_verified' in details):
                    self._event(db, row, 'confirmed', now, state, '已确认自己的新消息气泡', details)
            if state in {'sent','skipped'}:
                self._advance_turn(db, row['contact'])
            self._recompute_batch(db, row['batch_id'], now)
            if row['package_id'] and state in {'sent','skipped'}:
                if state == 'skipped':
                    self._stop_package(db,row['package_id'],'skipped',now)
                self._recompute_package(db,row['package_id'])

    def retry_failed_deliveries(self, *, now):
        """blocked 发件过了重试延迟且未超重试上限 → 自动重新入队（救回瞬态失败）。

        uncertain 不自动重试：它已回车但未确认气泡，可能已经发出，重试会重复发送。
        """
        with self._transaction() as db:
            rows = db.execute("""SELECT * FROM outbox WHERE state='blocked'
                AND detached=0 AND manual_required=0 AND package_id IS NULL
                AND failed_at IS NOT NULL AND failed_at<=? AND failed_at>? AND retries<?
                ORDER BY seq""",
                (now - self.retry_delay_seconds, now - self.failure_timeout_seconds, self.max_delivery_retries)).fetchall()
            retried = []
            for row in rows:
                db.execute("""UPDATE outbox SET state='pending',error='',resolution='',baseline=NULL,
                    submitted_at=NULL,submitted_text=NULL,finished_at=NULL,retries=retries+1
                    WHERE id=?""", (row["id"],))
                reason = f'自动重试（第 {row["retries"] + 1}/{self.max_delivery_retries} 次）；原失败原因：' + (row['error'] or '未记录')
                self._event(db, row, 'auto_retry', now, 'pending', reason)
                retried.append({**dict(row), 'state': 'pending', 'retries': row['retries'] + 1})
            return retried

    def expire_failed_deliveries(self, *, now):
        with self._transaction() as db:
            expired=self._expire_replies(db,now)
            rows=db.execute("""SELECT * FROM outbox WHERE batch_id IS NULL AND detached=0 AND state IN ('blocked','uncertain')
                AND failed_at IS NOT NULL AND failed_at<=? ORDER BY seq""",
                (now-self.failure_timeout_seconds,)).fetchall()
            for row in rows:
                reason=f'发送失败满{self.failure_timeout_seconds:g}秒，自动丢弃；原失败原因：'+(row['error'] or '未记录')
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
            interrupted_models=db.execute("SELECT * FROM batches WHERE state='processing'").fetchall()
            models = db.execute("""UPDATE batches SET state='uncertain',error='进程中断，模型结果未知',finished_at=?
                WHERE state='processing'""",(now,)).rowcount
            for row in interrupted_models:
                self._event(db,row,'model_uncertain',now,'uncertain','进程中断，模型结果未知',
                            {'retry_safe':False,'attempt':row['attempts']},kind='batches')
            interrupted=db.execute("SELECT * FROM outbox WHERE state IN ('sending','confirming')").fetchall()
            deliveries = db.execute("""UPDATE outbox SET state='uncertain',error='进程中断，发送结果需核对',
                failed_at=COALESCE(failed_at,?),finished_at=?
                WHERE state IN ('sending','confirming')""",(now,now)).rowcount
            for row in interrupted:
                if row['kind']=='image' or row['package_id']:
                    db.execute('UPDATE outbox SET manual_required=1 WHERE id=?',(row['id'],))
                if row['package_id']:
                    self._stop_package(db,row['package_id'],'uncertain',now)
                self._event(db,row,'failed',now,'uncertain','进程中断，发送结果需核对',{'phase':'recovery'})
            if self.restart_chat_policy == 'discard':
                for batch in db.execute("SELECT id FROM batches WHERE reply_complete=1 AND EXISTS(SELECT 1 FROM outbox WHERE batch_id=batches.id AND detached=0 AND state NOT IN ('sent','skipped'))").fetchall():
                    self._end_reply(db,batch['id'],now,'重启停止续发旧聊天回复','restart_discard')
            for row in db.execute("SELECT * FROM outbox WHERE state='uncertain' AND detached=0").fetchall():
                db.execute("UPDATE outbox SET detached=1,resolution='review' WHERE id=?",(row['id'],))
                if row['batch_id']:
                    self._end_reply(db,row['batch_id'],now,'发送结果待核对，停止本轮续发','review')
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
            if result.get('batch_id'):
                count = self._db.execute('SELECT COUNT(*) FROM outbox WHERE batch_id=?', (result['batch_id'],)).fetchone()[0]
                parent = self._db.execute('SELECT * FROM batches WHERE id=?', (result['batch_id'],)).fetchone()
                original = parent['part_count'] if parent is not None and 'part_count' in parent.keys() else 0
                result['part_count'] = max(count, original)
            else:
                result['part_count'] = 1
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
            if row is None or (row["state"] not in {"blocked", "uncertain"} and not (delivery and row["state"]=="skipped" and row["manual_required"])):
                raise ValueError("只允许显式重试 blocked/uncertain 任务")
            self._check_action(row,contact,expected_state,expected_finished_at,expected_attempts)
            if not delivery and db.execute("SELECT 1 FROM outbox WHERE batch_id=?", (record_id,)).fetchone():
                raise ValueError("模型已有回复，请处理对应发件任务，不能重跑模型")
            if delivery:
                if db.execute("SELECT 1 FROM outbox WHERE contact=? AND state IN ('sending','confirming')",(row['contact'],)).fetchone():
                    raise ValueError('该会话正在发送，请等待发送结束后重试')
                db.execute('UPDATE outbox SET manual_required=0 WHERE contact=?',(row['contact'],))
                if row['detached'] or row['state']=='skipped':
                    db.execute('UPDATE outbox SET failed_at=NULL,retries=0 WHERE id=?',(record_id,))
                    if row['batch_id']:
                        db.execute("UPDATE batches SET first_delivery_failure=NULL,delivery_resolution='',error='' WHERE id=?",(row['batch_id'],))
                db.execute("""UPDATE outbox SET detached=0,state='pending',error='',resolution='',baseline=NULL,
                    submitted_at=NULL,submitted_text=NULL,finished_at=NULL WHERE id=?""", (record_id,))
                self._recompute_batch(db, row["batch_id"])
                self._recompute_package(db,row['package_id'])
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
            if row is None or (row["state"] not in {"blocked", "uncertain"} and not (delivery and row["state"]=="skipped" and row["manual_required"])):
                raise ValueError("只允许人工处理 blocked/uncertain 任务")
            self._check_action(row,contact,expected_state,expected_finished_at,expected_attempts)
            if delivery:
                db.execute('UPDATE outbox SET manual_required=0 WHERE contact=?',(row['contact'],))
                db.execute("UPDATE outbox SET detached=0,state=?,finished_at=?,error=?,resolution=? WHERE id=?",
                           ("sent" if sent else "skipped", now, "人工核对结束",
                            'manual_sent' if sent else 'manual_skip',record_id))
                self._advance_turn(db, row["contact"])
                self._recompute_batch(db, row["batch_id"], now)
                self._recompute_package(db,row['package_id'])
            else:
                if db.execute("SELECT 1 FROM outbox WHERE batch_id=?", (record_id,)).fetchone():
                    raise ValueError("模型已有回复，请处理对应发件任务")
                db.execute("UPDATE batches SET state='done',finished_at=?,error=? WHERE id=?",
                           (now, "人工跳过", record_id))
            reason='人工核对结束；原状态：'+row['state']+'；原失败原因：'+(row['error'] or '未记录')
            self._event(db,row,'confirm_sent' if sent else 'manual_discard',now,
                        'sent' if sent else 'skipped' if delivery else 'done',reason,
                        kind=table,source=source)
