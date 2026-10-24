"""Transactional reply lifecycle; no UI, network, or startup side effects."""


class DeliveryPolicy:
    def _end_reply(self, db, batch_id, now, reason, resolution):
        """End unsent blocks, retaining uncertain outcomes for explicit review."""
        rows = db.execute("SELECT * FROM outbox WHERE batch_id=? AND state NOT IN ('sent','skipped')",
                          (batch_id,)).fetchall()
        for row in rows:
            uncertain = row['state'] in ('uncertain', 'confirming')
            state = 'uncertain' if uncertain else 'skipped'
            db.execute('UPDATE outbox SET state=?,detached=?,resolution=?,finished_at=?,error=? WHERE id=?',
                       (state, int(uncertain), 'review' if uncertain else resolution, now,
                        reason + ('；原原因：' + row['error'] if row['error'] else ''), row['id']))
            self._event(db, row, resolution, now, state, reason)
        db.execute('UPDATE batches SET delivery_resolution=?,error=? WHERE id=?',
                   (resolution, reason, batch_id))
        self._recompute_batch(db, batch_id, now)
        if rows:
            self._advance_turn(db, rows[0]['contact'])
        return rows

    def _expire_replies(self, db, now):
        batches = db.execute('''SELECT * FROM batches WHERE first_delivery_failure IS NOT NULL
            AND first_delivery_failure<=? AND EXISTS(SELECT 1 FROM outbox
                WHERE batch_id=batches.id AND detached=0 AND state IN ('pending','blocked'))
            AND NOT EXISTS(SELECT 1 FROM outbox WHERE batch_id=batches.id AND state IN ('sending','confirming'))''',
            (now - self.failure_timeout_seconds,)).fetchall()
        expired = []
        for batch in batches:
            reason = f'整轮回复首次失败满{self.failure_timeout_seconds:g}秒，结束剩余分块'
            rows = self._end_reply(db, batch['id'], now, reason, 'timeout')
            expired.extend({**dict(row), 'state': 'skipped', 'error': reason,
                            'failed_at': batch['first_delivery_failure']} for row in rows)
        return expired

    def save_draft(self, delivery_id, text):
        """Only called after the UI readback exactly matches the entered prefix."""
        with self._transaction() as db:
            row = db.execute('SELECT contact FROM outbox WHERE id=?', (delivery_id,)).fetchone()
            db.execute('UPDATE outbox SET draft_text=NULL WHERE contact=?', (row['contact'],))
            db.execute('UPDATE outbox SET draft_text=? WHERE id=?', (text, delivery_id))

    def owned_draft(self, contact):
        with self._lock:
            row = self._db.execute('SELECT draft_text FROM outbox WHERE contact=? AND draft_text IS NOT NULL ORDER BY seq DESC LIMIT 1',
                                   (contact,)).fetchone()
            return row[0] if row else None

    def forget_draft(self, contact):
        with self._transaction() as db:
            db.execute('UPDATE outbox SET draft_text=NULL WHERE contact=?', (contact,))
