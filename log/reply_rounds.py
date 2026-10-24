"""Paginate complete reply groups before fetching their constituent blocks."""


def read_rounds(db, row_reader, *, contact, state, scope, limit, offset, now, timeout):
    columns = {r[1] for r in db.execute('PRAGMA table_info(outbox)')}
    detached = 'detached=0 AND ' if 'detached' in columns else ''
    manual = ' OR manual_required=1' if 'manual_required' in columns else ''
    terms, args = [], []
    if contact:
        terms.append('contact=?'); args.append(contact)
    if state == 'active':
        terms.append(detached + "state NOT IN ('sent','skipped')")
    elif state != 'all':
        terms.append('state=?'); args.append(state)
    if scope == 'active': terms.append(detached + "state NOT IN ('sent','skipped')")
    if scope == 'issues': terms.append("(state IN ('blocked','uncertain')" + manual + ')')
    if scope == 'history': terms.append("state IN ('sent','skipped')")
    where = ' WHERE ' + ' AND '.join(terms) if terms else ''
    key = "CASE WHEN batch_id IS NULL THEN 'push:'||id ELSE 'reply:'||batch_id END"
    query = f'SELECT {key} round_id, MIN(seq) seq, MAX(seq) last_seq, MIN(failed_at) failed_at FROM outbox' + where + ' GROUP BY round_id'
    # Legacy databases without failed_at remain readable.
    if 'failed_at' not in columns: query = query.replace('MIN(failed_at)', 'MIN(created_at)')
    total = db.execute('SELECT COUNT(*) FROM (' + query + ')', args).fetchone()[0]
    offset = min(max(0, offset), ((max(total, 1)-1)//limit)*limit)
    order = 'last_seq DESC' if scope in ('all', 'history') else 'failed_at ASC,seq ASC' if scope == 'issues' else 'seq ASC'
    groups = db.execute(query + ' ORDER BY ' + order + ' LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
    result = []
    for group in groups:
        rows = db.execute(f'SELECT * FROM outbox WHERE {key}=? ORDER BY seq', (group['round_id'],)).fetchall()
        items = [row_reader(db, 'outbox', row, now=now, failure_timeout_seconds=timeout) for row in rows]
        active = next((r for r in items if not r.get('detached') and r['state'] not in ('sent','skipped')), None)
        review = next((r for r in items if r['state']=='uncertain' or r.get('manual_required')), None)
        chosen = active or review or items[-1]
        result.append({'id':group['round_id'], 'contact':chosen['contact'], 'state':chosen['state'],
                       'display_state':chosen.get('display_state',chosen['state']),
                       'preview': ''.join(r['preview'] for r in items)[:240],
                       'sent_parts':sum(r['state']=='sent' for r in items), 'part_count':len(items),
                       'error':chosen['error'], 'discard_at':chosen.get('discard_at'),
                       'created_at':items[0]['created_at'], 'parts':items})
    return result, {'total':total, 'offset':offset, 'limit':limit, 'has_more':offset+len(result)<total}
