"""Transaction-local unified person matching; membership evidence stays on bindings."""
import json
import unicodedata


def normalize_name(value):
    if not isinstance(value, str):
        return ''
    name = unicodedata.normalize('NFC', value).strip()
    return '' if name.startswith(('成员-', '待命名-', 'unknown-')) else name


def is_active(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='unified_contacts'").fetchone():
        return False
    return bool(db.execute('SELECT 1 FROM unified_contacts WHERE id=1 AND active=1').fetchone())


def touch_version(db):
    if is_active(db):
        db.execute('UPDATE unified_contacts SET version=version+1 WHERE id=1')


def ensure_schema(db):
    # Never executescript: it can commit the caller's migration transaction.
    for sql in (
        'CREATE TABLE IF NOT EXISTS user_redirects(old_user_id TEXT PRIMARY KEY,user_id TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS user_name_history(user_id TEXT NOT NULL,name TEXT NOT NULL,'
        'normalized_name TEXT NOT NULL,PRIMARY KEY(user_id,name))',
        'CREATE TABLE IF NOT EXISTS user_binding_names(binding_id TEXT PRIMARY KEY,nickname TEXT NOT NULL)',
    ):
        db.execute(sql)


def canonical_user(db, user_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='user_redirects'").fetchone():
        return user_id
    seen = set()
    while user_id not in seen:
        seen.add(user_id)
        row = db.execute('SELECT user_id FROM user_redirects WHERE old_user_id=?', (user_id,)).fetchone()
        if row is None:
            return user_id
        user_id = row[0]
    raise ValueError('联系人 ID 跳转循环')


def binding_name(db, row):
    if is_active(db):
        ensure_schema(db)
        item = db.execute('SELECT nickname FROM user_binding_names WHERE binding_id=?', (row['binding_id'],)).fetchone()
        if item:
            return item[0]
    return row['nickname']


def remember_name(db, user_id, name):
    ensure_schema(db)
    normalized = normalize_name(name)
    if normalized:
        db.execute('INSERT OR IGNORE INTO user_name_history VALUES(?,?,?)', (canonical_user(db, user_id), name, normalized))


def _people(db):
    ensure_schema(db)
    profiles = {row['user_id']: dict(row) for row in db.execute('SELECT * FROM user_profiles p WHERE NOT EXISTS '
        '(SELECT 1 FROM user_redirects r WHERE r.old_user_id=p.user_id)')}
    for profile in profiles.values():
        profile['names'] = {normalize_name(profile['display_name'])} - {''}
        profile['private'] = False
    for row in db.execute('SELECT b.*,COALESCE(n.nickname,b.nickname) AS actual_name FROM user_bindings b '
                          'LEFT JOIN user_binding_names n ON n.binding_id=b.binding_id'):
        if row['user_id'] in profiles:
            item = profiles[row['user_id']]
            if row['nickname_confirmed']:
                item['names'].update({normalize_name(row['actual_name'])} - {''})
            item['private'] |= row['channel_type'] == 'dm'
    return profiles


def _priority(person):
    return (not person['private'], person['created_at'], person['user_id'])


def reuse_person(db, nickname):
    if not is_active(db) or not normalize_name(nickname):
        return None
    matches = [person for person in _people(db).values() if normalize_name(nickname) in person['names']]
    return min(matches, key=_priority)['user_id'] if matches else None


def _redirect_conversations(db, source_id, target_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='unified_contacts'").fetchone():
        return
    row = db.execute('SELECT payload FROM unified_contacts WHERE id=1').fetchone()
    if row is None:
        return
    state = json.loads(row[0])
    policies = state.get('person_policies', {})
    source_policy, target_policy = policies.get(source_id), policies.get(target_id)
    changed = False
    for conversation in state.get('conversations', []):
        if conversation.get('person_id') == source_id:
            # Preserve each route's behavior before retiring the source default.
            if conversation.get('policy') is None and conversation.get('inherit_person_policy', True) and source_policy != target_policy:
                if source_policy is None:
                    conversation['inherit_person_policy'] = False
                else:
                    conversation['policy'] = source_policy
            conversation['person_id'] = target_id
            changed = True
    if source_id in policies:
        del policies[source_id]
        changed = True
    if changed:
        db.execute('UPDATE unified_contacts SET payload=?,version=version+1 WHERE id=1',
                   (json.dumps(state, ensure_ascii=False, separators=(',', ':')),))


def merge_users(db, source_id, target_id):
    ensure_schema(db)
    source_id, target_id = canonical_user(db, source_id), canonical_user(db, target_id)
    if source_id == target_id:
        return {'merged': [], 'target_id': target_id}
    people = _people(db)
    if source_id not in people or target_id not in people:
        raise ValueError('联系人不存在')
    for person in (people[source_id], people[target_id]):
        for name in person['names']:
            remember_name(db, target_id, name)
    for row in db.execute('SELECT name,normalized_name FROM user_name_history WHERE user_id=?', (source_id,)).fetchall():
        db.execute('INSERT OR IGNORE INTO user_name_history VALUES(?,?,?)', (target_id, row[0], row[1]))
    bindings = [row[0] for row in db.execute('SELECT binding_id FROM user_bindings WHERE user_id=?', (source_id,))]
    # Leave source profiles intact for historic references, redirect all live identity use.
    db.execute('UPDATE user_bindings SET user_id=?,version=version+1 WHERE user_id=?', (target_id, source_id))
    db.execute('UPDATE user_redirects SET user_id=? WHERE user_id=?', (target_id, source_id))
    db.execute('INSERT INTO user_redirects VALUES(?,?)', (source_id, target_id))
    _redirect_conversations(db, source_id, target_id)
    return {'merged': [{'source_id': source_id, 'target_id': target_id, 'binding_ids': bindings}],
            'target_id': target_id}


def merge_same_named(db):
    ensure_schema(db)
    people = _people(db)
    parent = {user_id: user_id for user_id in people}
    def find(user_id):
        while parent[user_id] != user_id:
            user_id = parent[user_id]
        return user_id
    names = {}
    for user_id, person in people.items():
        for name in person['names']:
            if name in names:
                parent[find(user_id)] = find(names[name])
            else:
                names[name] = user_id
    groups = {}
    for user_id in people:
        groups.setdefault(find(user_id), []).append(people[user_id])
    report = {'merged': []}
    for group in groups.values():
        ordered = sorted(group, key=_priority)
        for source in ordered[1:]:
            result = merge_users(db, source['user_id'], ordered[0]['user_id'])
            report['merged'].extend(result['merged'])
    return report
