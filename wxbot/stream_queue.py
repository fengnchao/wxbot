"""Runtime-only auxiliary stream storage, independent of legacy queue migrations."""
from contextlib import contextmanager
import json
import sqlite3
import time

from .streaming import SentenceBuffer


class StreamQueue:
    def _initialize_streams(self):
        self._stream_buffers = {}
        self._db.executescript('''
            CREATE TABLE IF NOT EXISTS model_stream_events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT NOT NULL,
                event TEXT NOT NULL,created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS model_stream_batch ON model_stream_events(batch_id,seq);
            CREATE TABLE IF NOT EXISTS model_stream_batches(
                batch_id TEXT PRIMARY KEY,mode TEXT NOT NULL,status TEXT NOT NULL,
                answer TEXT NOT NULL DEFAULT '',part_seq INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS model_stream_parts(
                delivery_id TEXT PRIMARY KEY,batch_id TEXT NOT NULL,sealed INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,enter_attempted INTEGER NOT NULL DEFAULT 0);
        ''')

    def begin_stream(self, batch_id, mode, *, now):
        with self._transaction() as db:
            old=db.execute('SELECT answer FROM model_stream_batches WHERE batch_id=?',(batch_id,)).fetchone()
            if old:
                if old['answer'] or db.execute('SELECT 1 FROM outbox WHERE batch_id=?',(batch_id,)).fetchone():
                    raise ValueError('cannot replay a stream with answer or deliveries')
                db.execute("UPDATE model_stream_batches SET mode=?,status='active',part_seq=1 WHERE batch_id=?",
                           (mode,batch_id))
            else:
                db.execute('INSERT INTO model_stream_batches(batch_id,mode,status) VALUES(?,?,?)',
                           (batch_id,mode,'active'))
        self._stream_buffers[batch_id] = SentenceBuffer()

    def record_model_event(self, batch_id, event, *, now):
        # Only canonical public fields are retained, never tool arguments/auth.
        allowed = {'type','text','provider','model','streaming','status','tool','sendable','label','fallback','message','code'}
        clean = {k: (v[:8192 if k=='text' else 300] if isinstance(v,str) else v) for k,v in event.items()
                 if k in allowed and isinstance(v,(str,int,float,bool,type(None)))}
        if clean.get('type') not in {'backend','summary_delta','tool','answer_delta','complete','error'}:
            return
        with self._transaction() as db:
            db.execute('INSERT INTO model_stream_events(batch_id,event,created_at) VALUES(?,?,?)',
                       (batch_id,json.dumps(clean,ensure_ascii=False),now))
            db.execute('DELETE FROM model_stream_events WHERE batch_id=? AND seq NOT IN '
                       '(SELECT seq FROM model_stream_events WHERE batch_id=? ORDER BY seq DESC LIMIT 512)',
                       (batch_id,batch_id))

    def model_events(self, batch_id, after=0):
        with self._lock:
            try:
                rows = self._db.execute('SELECT seq,event,created_at FROM model_stream_events '
                    'WHERE batch_id=? AND seq>? ORDER BY seq LIMIT 512',(batch_id,int(after))).fetchall()
            except sqlite3.OperationalError:
                return []
            return [dict(json.loads(r['event']),seq=r['seq'],created_at=r['created_at']) for r in rows]

    def stream_snapshot(self, batch_id):
        with self._lock:
            try:
                row = self._db.execute('SELECT * FROM model_stream_batches WHERE batch_id=?',(batch_id,)).fetchone()
            except sqlite3.OperationalError:
                return None
            return dict(row) if row else None

    def stream_part(self, delivery_id):
        with self._lock:
            try:
                row = self._db.execute('SELECT p.*,o.text,b.mode,b.status FROM model_stream_parts p '
                    'JOIN outbox o ON o.id=p.delivery_id JOIN model_stream_batches b ON b.batch_id=p.batch_id '
                    'WHERE p.delivery_id=?',(delivery_id,)).fetchone()
            except sqlite3.OperationalError:
                return None
            return dict(row) if row else None

    def delivery_typing_mode(self, batch_id):
        row = self.stream_snapshot(batch_id) if batch_id else None
        return row['mode'] if row else 'chunked'

    def is_group_batch(self, batch_id):
        with self._lock:
            row=self._db.execute('SELECT group_mode FROM inbox WHERE batch_id=? LIMIT 1',(batch_id,)).fetchone()
            return bool(row and row[0])

    def stream_draft_cleaned(self, delivery_id):
        with self._transaction() as db:
            db.execute("UPDATE outbox SET draft_text=NULL,manual_required=0 WHERE id=? AND state='skipped'",
                       (delivery_id,))

    def stream_draft_review(self, delivery_id):
        with self._transaction() as db:
            db.execute("UPDATE outbox SET manual_required=1 WHERE id=? AND state IN ('skipped','uncertain')",
                       (delivery_id,))

    def cancel_active_streams(self, *, now):
        with self._transaction() as db:
            for row in db.execute("SELECT batch_id FROM model_stream_batches WHERE mode='streaming' AND status='active'").fetchall():
                self._cancel_stream(db,row['batch_id'],now,'模型线程停止，不重放流式回复')

    def finish_buffered_stream(self, batch_id, text):
        with self._transaction() as db:
            db.execute("UPDATE model_stream_batches SET status='complete',answer=? WHERE batch_id=?",(text,batch_id))

    def defer_stream_window(self, delivery_id, *, now):
        with self._transaction() as db:
            db.execute("UPDATE outbox SET state='pending',baseline=NULL,not_before=? WHERE id=? AND state='sending'",
                       (now+.1,delivery_id))

    def append_stream(self, batch_id, text, *, now, final=False):
        with self._transaction() as db:
            stream = db.execute('SELECT * FROM model_stream_batches WHERE batch_id=?',(batch_id,)).fetchone()
            if stream is None or stream['status'] != 'active':
                raise ValueError('stream stopped')
            answer = stream['answer'] + text
            if len(answer) > 1048576:
                raise ValueError('stream answer exceeds limit')
            parser = self._stream_buffers[batch_id]
            sealed = parser.feed(text)
            if final:
                sealed += parser.finish()
            seq = stream['part_seq']
            contact = db.execute('SELECT contact FROM batches WHERE id=?',(batch_id,)).fetchone()[0]
            pieces = [(part,True) for part in sealed]
            if parser.pending.strip():
                pieces.append((parser.pending,False))
            for part, is_sealed in pieces:
                ident = f'{batch_id}:{seq}'
                old = db.execute('SELECT text FROM outbox WHERE id=?',(ident,)).fetchone()
                if old is None:
                    self._insert_delivery(db,contact,part,now,now,batch_id,seq)
                    db.execute('INSERT INTO model_stream_parts(delivery_id,batch_id,sealed) VALUES(?,?,?)',
                               (ident,batch_id,int(is_sealed)))
                else:
                    if not part.startswith(old[0]):
                        raise ValueError('stream part is not append-only')
                    db.execute('UPDATE outbox SET text=? WHERE id=?',(part,ident))
                    db.execute('UPDATE model_stream_parts SET sealed=?,version=version+1 WHERE delivery_id=?',
                               (int(is_sealed),ident))
                if is_sealed:
                    seq += 1
            db.execute('UPDATE model_stream_batches SET answer=?,part_seq=?,status=? WHERE batch_id=?',
                       (answer,seq,'complete' if final else 'active',batch_id))
            db.execute('UPDATE batches SET part_count=? WHERE id=?',
                       (seq-1+bool(parser.pending.strip()),batch_id))
            if final:
                db.execute('UPDATE batches SET reply_text=?,reply_complete=1 WHERE id=?',(answer,batch_id))
                self._recompute_batch(db,batch_id,now)

    def cancel_stream(self, batch_id, *, now, reason='流式生成中断，停止续发'):
        with self._transaction() as db:
            self._cancel_stream(db,batch_id,now,reason)

    def _cancel_stream(self, db, batch_id, now, reason):
        db.execute("UPDATE model_stream_batches SET status='cancelled' WHERE batch_id=?",(batch_id,))
        for row in db.execute('SELECT o.*,p.enter_attempted FROM outbox o JOIN model_stream_parts p '
                "ON p.delivery_id=o.id WHERE o.batch_id=? AND o.state NOT IN ('sent','skipped')",(batch_id,)).fetchall():
            uncertain = row['enter_attempted'] or row['state'] in {'confirming','uncertain'}
            db.execute('UPDATE outbox SET state=?,detached=?,manual_required=?,finished_at=?,error=?,resolution=? WHERE id=?',
                ('uncertain' if uncertain else 'skipped',int(bool(uncertain)),int(bool(uncertain or row['draft_text'])),
                 now,reason,'review' if uncertain else 'stream_cancelled',row['id']))
        db.execute('UPDATE batches SET reply_complete=1,error=? WHERE id=?',(reason,batch_id))
        self._recompute_batch(db,batch_id,now)

    @contextmanager
    def stream_enter_gate(self, delivery_id, text, version):
        # The same write lock serializes cancellation and the native Enter call.
        # Persist attempted before native submission; a crash is always review.
        with self._lock:
            with self._transaction() as db:
                row = db.execute('SELECT p.*,o.state,o.text,b.status FROM model_stream_parts p '
                    'JOIN outbox o ON o.id=p.delivery_id JOIN model_stream_batches b ON b.batch_id=p.batch_id '
                    'WHERE delivery_id=?',(delivery_id,)).fetchone()
                allowed = bool(row and row['sealed'] and row['version']==version and row['text']==text
                    and row['state']=='sending' and row['status'] in {'active','complete'} and not row['enter_attempted'])
                if allowed:
                    db.execute('UPDATE model_stream_parts SET enter_attempted=1 WHERE delivery_id=?',(delivery_id,))
                    db.execute("UPDATE outbox SET state='confirming',submitted_at=? WHERE id=?",(time.time(),delivery_id))
            if not allowed:
                yield False
                return
            # Hold SQLite's writer reservation too: admin connections do not
            # share the Python lock. The durable attempted receipt above must
            # survive a crash inside this second transaction/native call.
            with self._transaction() as db:
                current=db.execute('SELECT o.state,b.status,p.version,p.sealed,o.text FROM outbox o '
                    'JOIN model_stream_parts p ON p.delivery_id=o.id '
                    'JOIN model_stream_batches b ON b.batch_id=p.batch_id WHERE o.id=?',(delivery_id,)).fetchone()
                yield bool(current and current['state']=='confirming' and current['status'] in {'active','complete'}
                           and current['sealed'] and current['version']==version and current['text']==text)
