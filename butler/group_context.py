"""Public group observations, bounded request snapshots and per-thread cursors."""
import json
import time


def initialize(db):
    """Add tables within the caller's business-store migration transaction."""
    for sql in (
        '''CREATE TABLE IF NOT EXISTS group_context (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, contact TEXT NOT NULL,
            source_id TEXT NOT NULL, source_index INTEGER NOT NULL,
            member_key TEXT NOT NULL, member_name TEXT NOT NULL,
            text TEXT NOT NULL, sender TEXT NOT NULL, created_at REAL NOT NULL,
            UNIQUE(contact,source_id,source_index))''',
        'CREATE INDEX IF NOT EXISTS group_context_contact_seq ON group_context(contact,seq)',
        '''CREATE TABLE IF NOT EXISTS group_context_cursors (
            contact TEXT NOT NULL, scope TEXT NOT NULL, seq INTEGER NOT NULL,
            PRIMARY KEY(contact,scope))''',
        '''CREATE TABLE IF NOT EXISTS group_context_snapshots (
            contact TEXT NOT NULL, request_id TEXT NOT NULL, before_seq INTEGER NOT NULL,
            snapshot TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(contact,request_id))''',
    ):
        db.execute(sql)


def _text(value, name, limit, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError('Invalid ' + name)
    return value


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid ' + name)
    return value


class GroupContext:
    def __init__(self, store):
        self.store = store
        with store.transaction() as db:
            initialize(db)

    def archive(self, contact, source_id, messages):
        _text(contact, 'contact', 300)
        _text(source_id, 'source_id', 300)
        if not isinstance(messages, list) or not 1 <= len(messages) <= 200:
            raise ValueError('messages must contain 1-200 observations')
        normalized = []
        for item in messages:
            if not isinstance(item, dict):
                raise ValueError('Invalid observation')
            text = _text(item.get('text'), 'text', 10000, empty=True)
            key = _text(item.get('member_key', ''), 'member_key', 300, empty=True)
            name = _text(item.get('member_name', ''), 'member_name', 300, empty=True)
            sender = item.get('sender', 'other')
            if sender not in {'other', 'self'}:
                raise ValueError('Invalid sender')
            normalized.append((key, name, text, sender))
        if sum(len(row[2]) for row in normalized) > 100000:
            raise ValueError('Archive payload too large')
        with self.store.transaction() as db:
            existing = db.execute('SELECT * FROM group_context WHERE contact=? AND source_id=? '
                                  'ORDER BY source_index', (contact, source_id)).fetchall()
            if existing:
                if [tuple(r[k] for k in ('member_key', 'member_name', 'text', 'sender')) for r in existing] != normalized:
                    raise ValueError('Archive source already has different observations')
                return {'seq': existing[-1]['seq'], 'inserted': 0}
            last = 0
            for index, row in enumerate(normalized):
                last = db.execute('INSERT INTO group_context(contact,source_id,source_index,member_key,'
                    'member_name,text,sender,created_at) VALUES(?,?,?,?,?,?,?,?)',
                    (contact, source_id, index, *row, time.time())).lastrowid
            return {'seq': last, 'inserted': len(normalized)}

    def snapshot(self, contact, before_seq, after_seq=0, limit=30, max_chars=6000):
        with self.store.transaction() as db:
            return self._snapshot(db, contact, before_seq, after_seq, limit, max_chars)

    @staticmethod
    def _snapshot(db, contact, before_seq, after_seq, limit, max_chars):
        _text(contact, 'contact', 300)
        _integer(before_seq, 'before_seq', 1, 2**63 - 1)
        _integer(after_seq, 'after_seq', 0, 2**63 - 1)
        _integer(limit, 'limit', 1, 200)
        _integer(max_chars, 'max_chars', 1, 30000)
        recent = db.execute('SELECT * FROM group_context WHERE contact=? AND seq<? AND seq>? '
                            'ORDER BY seq DESC LIMIT ?', (contact, before_seq, after_seq, limit))
        rows, characters = [], 0
        for row in recent:
            size = len(row['text'])
            if characters + size > max_chars:
                break
            rows.append(dict(row))
            characters += size
        rows.reverse()
        return {'messages': rows, 'from_seq': rows[0]['seq'] if rows else 0,
                'to_seq': rows[-1]['seq'] if rows else 0, 'characters': characters}

    def snapshot_for_request(self, contact, request_id, before_seq, after_seq=0, limit=30, max_chars=6000):
        _text(request_id, 'request_id', 300)
        with self.store.transaction() as db:
            row = db.execute('SELECT before_seq,snapshot FROM group_context_snapshots '
                             'WHERE contact=? AND request_id=?', (contact, request_id)).fetchone()
            if row:
                if row['before_seq'] != before_seq:
                    raise ValueError('Request context boundary changed')
                return json.loads(row['snapshot'])
            current = db.execute('SELECT MIN(seq) FROM group_context WHERE contact=? AND source_id=?',
                                 (contact, request_id)).fetchone()[0]
            # The model receives the whole merged batch as its current input.
            # Exclude every observation in that batch from the public preamble.
            cutoff = min(before_seq, current) if current is not None else before_seq
            snapshot = self._snapshot(db, contact, cutoff, after_seq, limit, max_chars)
            db.execute('INSERT INTO group_context_snapshots VALUES(?,?,?,?,?)',
                (contact, request_id, before_seq, json.dumps(snapshot, ensure_ascii=False), time.time()))
            return snapshot

    def cursor(self, contact, scope):
        with self.store.transaction() as db:
            row = db.execute('SELECT seq FROM group_context_cursors WHERE contact=? AND scope=?',
                             (contact, scope)).fetchone()
            return row['seq'] if row else 0

    def advance(self, contact, scope, seq):
        _text(contact, 'contact', 300)
        _text(scope, 'scope', 2000)
        _integer(seq, 'seq', 0, 2**63 - 1)
        with self.store.transaction() as db:
            db.execute('INSERT INTO group_context_cursors VALUES(?,?,?) ON CONFLICT(contact,scope) '
                       'DO UPDATE SET seq=MAX(seq,excluded.seq)', (contact, scope, seq))
