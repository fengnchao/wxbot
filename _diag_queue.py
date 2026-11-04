import sqlite3, os, json
paths = [
 r'D:\work\code\wxbot-dev\cache\wxbot_queue.sqlite3',
 r'D:\work\code\wxbot\cache\wxbot_queue.sqlite3',
]
oid = 'eaea5a891bfd4847986cb52331cdf2db:1'
prefix = 'eaea5a891bfd4847986cb52331cdf2db'
for p in paths:
 print('===', p, 'exists=', os.path.exists(p))
 if not os.path.exists(p):
  continue
 con = sqlite3.connect(p)
 con.row_factory = sqlite3.Row
 cur = con.cursor()
 cur.execute('SELECT name FROM sqlite_master WHERE type=?', ('table',))
 tables = [r[0] for r in cur.fetchall()]
 print('tables:', tables)
 for t in tables:
  cur.execute(f'PRAGMA table_info({t})')
  cols = [r[1] for r in cur.fetchall()]
  print('TABLE', t, 'cols:', cols)
  # try find by id
  if 'id' in cols:
   cur.execute(f'SELECT * FROM {t} WHERE CAST(id AS TEXT) LIKE ?', (prefix+'%',))
   rows = cur.fetchall()
   for row in rows:
    print('HIT', t, dict(row))
  # recent sending/voice
  q = None
  if 'state' in cols and 'kind' in cols:
   q = f"SELECT * FROM {t} WHERE state='sending' OR kind='voice' ORDER BY rowid DESC LIMIT 8"
  elif 'state' in cols:
   q = f"SELECT * FROM {t} WHERE state='sending' ORDER BY rowid DESC LIMIT 8"
  if q:
   try:
    cur.execute(q)
    for row in cur.fetchall():
     print('RECENT', t, dict(row))
   except Exception as e:
    print('recent err', t, e)
 con.close()
