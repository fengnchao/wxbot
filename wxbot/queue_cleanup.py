"""Explicit, backed-up deletion of unsuccessful queue records. No UI access."""
import json
from pathlib import Path
import sqlite3
import uuid
from contextlib import closing


def delete_unsent(store, *, now, source):
    backup_path = ''
    # Includes unmerged incoming messages and unfinished model batches, as
    # explicitly authorized by the user. Keep a restorable database snapshot.
    with store._transaction() as db:
        if store.path != ':memory:':
            path = Path(store.path).resolve()
            directory = path.parent / 'backups'
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / ('delete-unsent-' + uuid.uuid4().hex + '.sqlite3')
            # The write reservation prevents new records arriving between the
            # backup snapshot and deletion. Read through a separate connection;
            # backing up this connection's write transaction would deadlock.
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as reader:
                with closing(sqlite3.connect(target)) as backup:
                    reader.backup(backup)
            backup_path = str(target)
        rows = db.execute("SELECT * FROM outbox WHERE state NOT IN ('sent','sending','confirming')").fetchall()
        active = db.execute("SELECT COUNT(*) FROM outbox WHERE state IN ('sending','confirming')").fetchone()[0]
        affected_batches = {row['batch_id'] for row in rows if row['batch_id']}
        packages = {row['package_id'] for row in rows if row['package_id']}
        drafts = {row['contact'] for row in rows if row['manual_required'] or row['draft_text']}
        db.executemany('DELETE FROM delivery_events WHERE record_id=? AND record_kind=?',
                       ((row['id'], 'outbox') for row in rows))
        db.executemany('DELETE FROM outbox WHERE id=?', ((row['id'],) for row in rows))
        # Request IDs remain cancellation receipts, preventing package replay.
        db.executemany("UPDATE delivery_packages SET state='cancelled' WHERE id=?", ((item,) for item in packages))
        deleted_messages = db.execute('SELECT COUNT(*) FROM inbox WHERE batch_id IS NULL').fetchone()[0]
        db.execute('DELETE FROM inbox WHERE batch_id IS NULL')
        deleted_batches = 0
        for batch in db.execute('SELECT * FROM batches').fetchall():
            if batch['id'] not in affected_batches and batch['state'] == 'done':
                continue
            children = db.execute('SELECT state,text FROM outbox WHERE batch_id=? ORDER BY part_seq',
                                  (batch['id'],)).fetchall()
            if children:
                if batch['id'] in affected_batches:
                    db.execute("UPDATE batches SET delivery_resolution='deleted',error=?,reply_text=? WHERE id=?",
                               ('未发送部分已由用户删除', ''.join(row['text'] for row in children), batch['id']))
                    store._recompute_batch(db, batch['id'], now)
            else:
                deleted_messages += db.execute('SELECT COUNT(*) FROM inbox WHERE batch_id=?', (batch['id'],)).fetchone()[0]
                db.execute('DELETE FROM inbox WHERE batch_id=?', (batch['id'],))
                db.execute("DELETE FROM delivery_events WHERE record_id=? AND record_kind='batches'", (batch['id'],))
                db.execute('DELETE FROM batches WHERE id=?', (batch['id'],))
                deleted_batches += 1
        # These are unread UI discovery markers, not collected message rows.
        # Keep them in sync with MainInbox's live memory instead of silently
        # discarding unread/new messages or letting deleted markers reappear.
        protected_reads = db.execute('SELECT COUNT(*) FROM pending_sessions').fetchone()[0]
        result = dict(deleted_messages=deleted_messages, deleted_deliveries=len(rows),
                      deleted_batches=deleted_batches, protected_active=active+protected_reads,
                      protected_reads=protected_reads,
                      drafts_to_clear=len(drafts), backup_path=backup_path)
        # Also cancel old HTTP work that has not yet left the in-memory queue.
        db.execute('''INSERT INTO delivery_events(record_id,record_kind,contact,action,at,state,reason,details,source)
            VALUES(?, 'queue', '', 'delete_unsent', ?, 'deleted', ?, ?, ?)''',
                   (uuid.uuid4().hex, now, '用户删除所有未发送成功消息',
                    json.dumps({k: v for k, v in result.items() if isinstance(v, int)}), source))
        return result
