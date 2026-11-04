import sqlite3, time, datetime
p=r'D:\work\code\wxbot-dev\cache\wxbot_queue.sqlite3'
con=sqlite3.connect(p); con.row_factory=sqlite3.Row; c=con.cursor()
c.execute("SELECT * FROM delivery_events WHERE record_id LIKE ? ORDER BY seq", ('eaea5a89%',))
for r in c.fetchall():
 print(dict(r))
c.execute("SELECT * FROM delivery_events ORDER BY seq DESC LIMIT 15")
print('--- last 15 events ---')
for r in c.fetchall():
 print(dict(r))
# convert created_at
c.execute("SELECT id,state,kind,created_at,submitted_at,media_path,error FROM outbox WHERE id=?", ('eaea5a891bfd4847986cb52331cdf2db:1',))
row=dict(c.fetchone())
print('outbox', row)
print('created_local', datetime.datetime.fromtimestamp(row['created_at']).isoformat())
print('now', datetime.datetime.now().isoformat(), 'age_s', time.time()-row['created_at'])
con.close()
