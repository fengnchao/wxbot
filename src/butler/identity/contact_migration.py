"""Explicit, offline cutover from legacy contact sources to one business database.

Preview reads consistent private SQLite backup snapshots. Import, identity merges and activation happen in a
staging database; SQLite backup publishes the complete result atomically.
"""
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import tempfile
import time
import tomllib
import uuid

from butler.identity.contact_store import ContactStore
from butler.identity.directory import directory_path, migration_source_name


def _path(value, owner):
    target = Path(value).expanduser()
    return (target if target.is_absolute() else owner / target).resolve()


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _database_digest(path):
    return (_digest(path), _digest(Path(str(path) + '-wal')))


@contextmanager
def _read_database(path):
    """Take a consistent read-only snapshot, including committed WAL frames."""
    with closing(sqlite3.connect(':memory:')) as db:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
            source.backup(db)
        db.row_factory = sqlite3.Row
        yield db


def _table(db, name):
    return bool(db.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?', (name,)).fetchone())


def _record(path, kind, sources):
    if not any(s['path'] == str(path) for s in sources):
        sources.append(dict(path=str(path), kind=kind, sha256=_digest(path), present=path.is_file()))


def _toml(path, sources):
    _record(path, 'toml', sources)
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text('utf-8-sig'))
    except (ValueError, UnicodeError):
        raise ValueError(f'invalid TOML source: {path}') from None


def _layout(root, sources):
    btpath, wxpath = root / 'config.butler.toml', root / 'config.wxbot.toml'
    lgpath = _path(os.environ.get('LOG_CONFIG') or 'config.log.toml', root)
    bt, wx, lg = (_toml(p, sources) for p in (btpath, wxpath, lgpath))
    database = directory_path(btpath, bt)
    if wxpath.exists() and directory_path(wxpath, wx) != database:
        raise ValueError('conflicting Butler and wxbot directory database paths')
    for key, expected in [('butler_config', btpath), ('wxbot_config', wxpath)]:
        override = os.environ.get('BUTLER_CONFIG' if key == 'butler_config' else 'WXBOT_CONFIG') or (lg.get('sources') or {}).get(key)
        if override and _path(override, lgpath.parent) != expected:
            raise ValueError(f'conflicting effective {key} path; use the owning installation directory')
    return database, (btpath, bt), (wxpath, wx), (lgpath, lg)


def _names(values, label):
    if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError(f'{label} must be a list of nonempty names')
    return list(dict.fromkeys(values))


def _json(path, kind, sources):
    _record(path, kind, sources)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text('utf-8-sig'))
    except (ValueError, UnicodeError):
        raise ValueError(f'invalid {kind} JSON source: {path}') from None
    if not isinstance(raw, dict):
        raise ValueError(f'invalid {kind} object: {path}')
    return raw


def _policies(path, sources):
    raw = _json(path, 'policy', sources)
    if raw is None:
        return None
    users = raw.get('users')
    if not isinstance(users, dict):
        raise ValueError(f'invalid policy users: {path}')
    result = {}
    for name, policy in users.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(policy, dict):
            raise ValueError(f'invalid policy entry: {path}')
        # Reject malformed permissions rather than silently replacing them by {}.
        if not isinstance(policy.get('role_skill'), str) or not policy['role_skill'].strip():
            raise ValueError(f'invalid policy role: {path}')
        allowed = policy.get('allowed_skills')
        if not isinstance(allowed, list) or any(not isinstance(v, str) for v in allowed):
            raise ValueError(f'invalid policy skills: {path}')
        if 'heartbeat_enabled' in policy and type(policy['heartbeat_enabled']) is not bool:
            raise ValueError(f'invalid policy heartbeat: {path}')
        result[name] = dict(role_skill=policy['role_skill'].strip(),
                            allowed_skills=sorted({v.strip() for v in allowed if v.strip()} - {policy['role_skill'].strip()}),
                            heartbeat_enabled=policy.get('heartbeat_enabled', False))
    return result


def _groups(path, sources):
    raw = _json(path, 'subscriptions', sources)
    if raw is None:
        return None
    groups = raw.get('groups', raw)
    if not isinstance(groups, dict):
        raise ValueError(f'invalid subscription groups: {path}')
    result = {}
    for kind, names in groups.items():
        if not isinstance(kind, str) or not kind.isdigit() or int(kind) < 1:
            raise ValueError(f'invalid subscription type: {path}')
        result[str(int(kind))] = _names(names, 'subscription destinations')
    return result


def _merge_sources(paths, loader, sources, label):
    result = {}
    for path in dict.fromkeys(p for p in paths if p is not None):
        current = loader(path, sources)
        if current is None:
            continue
        for key, value in current.items():
            if key in result and result[key] != value:
                raise ValueError(f'conflicting effective {label} sources for {key!r}')
            result[key] = value
    return result


def _collect(root):
    sources = []
    database, (btpath, bt), (wxpath, wx), (lgpath, lg) = _layout(root, sources)
    secondary = _path(bt.get('agent', {}).get('data_dir') or 'data', btpath.parent) / 'business.sqlite3'
    if secondary != database and secondary.exists():
        with _read_database(secondary) as db:
            for table in ('identities', 'memory', 'sessions', 'reminders', 'operations', 'events',
                          'user_profiles', 'user_bindings', 'user_avatars', 'user_legacy_owners'):
                if _table(db, table) and db.execute('SELECT 1 FROM "' + table + '" LIMIT 1').fetchone():
                    raise ValueError('conflicting business database paths: configured directory database differs '
                                     'from agent.data_dir/business.sqlite3 containing identity or business data; '
                                     'resolve the sources before contact migration')
    directory = dict(contacts=[], channel={}, aliases=[])
    bindings, profiles, imported, memory_conflicts, memories, identities = [], [], set(), [], [], []
    if database.exists():
        with _read_database(database) as db:
            if _table(db, 'unified_contacts'):
                row = db.execute('SELECT active FROM unified_contacts WHERE id=1').fetchone()
                if row and row['active']:
                    return dict(ok=True, active=True, mode=wx.get('installation', {}).get('mode', 'local'),
                                database=str(database), state=ContactStore._snapshot(db),
                                sources=sources, errors=[], counts={}, same_name_merges=[], memory_conflicts=[])
            if _table(db, 'directory_state'):
                row = db.execute('SELECT payload FROM directory_state WHERE id=1').fetchone()
                if row:
                    directory = json.loads(row['payload'])
            if _table(db, 'directory_migrations'):
                imported = {migration_source_name(row[0]) for row in db.execute('SELECT source FROM directory_migrations')}
            if _table(db, 'user_bindings'):
                bindings = [dict(row) for row in db.execute('SELECT * FROM user_bindings')]
            if _table(db, 'user_profiles'):
                profiles = [dict(row) for row in db.execute('SELECT * FROM user_profiles')]
            if _table(db, 'memory'):
                memories = [dict(row) for row in db.execute('SELECT owner,key,value FROM memory WHERE owner LIKE "user:%"')]
            if _table(db, 'identities'):
                identities = [dict(row) for row in db.execute('SELECT * FROM identities ORDER BY rowid DESC')]
    conversations = {}
    explicit_fields = {}
    types = {}

    def add(name, channel_type=None, route=None):
        if not isinstance(name, str) or not name.strip():
            raise ValueError('contact name must be nonempty')
        if channel_type == 'private':
            channel_type = 'dm'
        if channel_type is not None:
            if channel_type not in {'dm', 'group'}:
                raise ValueError(f'invalid channel type for {name!r}')
            if name in types and types[name] != channel_type:
                raise ValueError(f'conflicting dm/group destination: {name!r}')
            types[name] = channel_type
        value = conversations.setdefault(name, dict(id=uuid.uuid5(uuid.NAMESPACE_URL, 'butler-conversation:' + name).hex,
            name=name, channel_type=channel_type or 'dm', uid=name, profile='default', label='', session_key='',
            listening=False, enabled=True, person_id='', policy=None, subscriptions=[]))
        if channel_type:
            value['channel_type'] = channel_type
        if route:
            seen = explicit_fields.setdefault(name, {})
            for key in ('uid', 'profile', 'label', 'session_key', 'enabled'):
                if key not in route:
                    continue
                if key in seen and seen[key] != route[key]:
                    raise ValueError(f'conflicting route {key} for {name!r}')
                seen[key] = route[key]
                value[key] = route[key]
        return value

    contacts = list(directory.get('contacts', []))
    known_routes = set()
    if btpath.name not in imported:
        legacy_contacts = bt.get('contacts', [])
        if not isinstance(legacy_contacts, list):
            raise ValueError('contacts must be a list')
        contacts.extend(legacy_contacts)
    for route in contacts:
        if not isinstance(route, dict):
            raise ValueError('invalid contact route')
        add(route.get('name'), route.get('channel_type'), route)
        known_routes.add(route['name'])

    settings = {}
    channels = [directory.get('channel', {})]
    if wxpath.name not in imported:
        bot = wx.get('bot', {})
        main = wx.get('wechat', {}).get('main_window', {})
        channels.append(dict(bot={k: bot[k] for k in ('bound_users', 'bound_groups', 'mention_names') if k in bot},
                             wechat=dict(main_window={k: main[k] for k in ('listen_all',) if k in main})))
    for channel in channels:
        bot = channel.get('bot', {})
        for key, kind in [('bound_users', 'dm'), ('bound_groups', 'group')]:
            for name in _names(bot.get(key, []), key):
                add(name, kind)['listening'] = True
        if 'mention_names' in bot:
            mentions = _names(bot['mention_names'], 'mention_names')
            if 'bot' in settings and settings['bot']['mention_names'] != mentions:
                raise ValueError('conflicting effective mention_names settings')
            settings['bot'] = dict(mention_names=mentions)
        main = channel.get('wechat', {}).get('main_window', {})
        if 'listen_all' in main:
            if type(main['listen_all']) is not bool:
                raise ValueError('listen_all must be boolean')
            value = dict(main_window=dict(listen_all=main['listen_all']))
            if 'wechat' in settings and settings['wechat'] != value:
                raise ValueError('conflicting effective listen_all settings')
            settings['wechat'] = value
    settings.setdefault('bot', dict(mention_names=[]))
    settings.setdefault('wechat', dict(main_window=dict(listen_all=True)))

    aliases = deepcopy(directory.get('aliases', []))
    alias_keys = {(a['group'], a['member_key'], a['source']) for a in aliases}

    def alias(group, key, name, source, pending):
        identity = (group, key, source)
        if identity not in alias_keys:
            aliases.append(dict(group=group, member_key=key, name=name, source=source, pending=pending))
            alias_keys.add(identity)
        if group:
            add(group, 'group')

    if wxpath.name not in imported:
        for key, name in wx.get('wechat', {}).get('group_sender', {}).get('member_names', {}).items():
            alias('', key, name, 'legacy', True)
    queue = _path(wx.get('queue', {}).get('database') or 'cache/wxbot_queue.sqlite3', wxpath.parent)
    if queue.exists():
        _record(queue, 'nickname observations', sources)
        with _read_database(queue) as db:
            if _table(db, 'group_member_names'):
                for group, key, name in db.execute('SELECT contact,member_key,name FROM group_member_names'):
                    alias(group, key, name, 'learned', False)
    for observation in list(aliases):
        if observation.get('group'):
            add(observation['group'], 'group')
    for binding in bindings:
        c = add(binding['contact'], binding['channel_type'])
        if binding['channel_type'] == 'dm':
            c['person_id'] = binding['user_id']
            if not binding['enabled']:
                c['enabled'] = False
    # Historic service-computed identities are route evidence, never a reason
    # to start listening. Current configured routes take precedence over history.
    for identity in identities:
        name = identity.get('contact')
        if not name or name in known_routes:
            continue
        route = {key: identity[key] for key in ('uid', 'profile') if isinstance(identity.get(key), str)}
        add(name, identity.get('channel_type') or None, route)
        known_routes.add(name)
    provider = bt.get('agent', {}).get('provider', 'hermes')
    home_value = bt.get('agent', {}).get('data_dir', 'data') if provider == 'codex' else bt.get('hermes', {}).get('root')
    home = _path(home_value, btpath.parent) if home_value else None
    log_home = _path(lg.get('sources', {}).get('home') or home or 'data', lgpath.parent)
    heartbeat = bt.get('heartbeat', {}).get('config_file')
    policy_paths = ([_path(heartbeat, btpath.parent)] if heartbeat else
                    [home / 'cache/butler_heartbeat.json' if home else None, log_home / 'cache/butler_heartbeat.json'])
    group_file = bt.get('groups', {}).get('file')
    group_paths = [_path(group_file, btpath.parent) if group_file else home / 'cache/butler_groups.json' if home else None]
    override = os.environ.get('BUTLER_GROUP_FILE') or lg.get('sources', {}).get('groups_file')
    group_paths.append(_path(override, lgpath.parent) if override else log_home / 'cache/butler_groups.json')
    for name, policy in _merge_sources(policy_paths, _policies, sources, 'policy').items():
        add(name)['policy'] = policy
    for kind, names in _merge_sources(group_paths, _groups, sources, 'subscription').items():
        for name in names:
            add(name)['subscriptions'].append(int(kind))
    for c in conversations.values():
        c['needs_route'] = c['name'] not in known_routes
    state = dict(version=0, conversations=list(conversations.values()), settings=settings, aliases=aliases, person_policies={})
    ContactStore._validated(state)
    from butler.identity.contact_identity import normalize_name
    named = {}
    for profile in profiles:
        name = normalize_name(profile['display_name'])
        if name:
            named.setdefault(name, set()).add(profile['user_id'])
    for binding in bindings:
        name = normalize_name(binding['nickname']) if binding.get('nickname_confirmed', True) else ''
        if name:
            named.setdefault(name, set()).add(binding['user_id'])
    merges = [dict(name=name, user_ids=sorted(ids)) for name, ids in sorted(named.items()) if len(ids) > 1]
    for merge in merges:
        by_key = {}
        owners = {'user:' + person for person in merge['user_ids']}
        for row in memories:
            if row['owner'] in owners:
                by_key.setdefault(row['key'], set()).add(row['value'])
        memory_conflicts.extend(dict(name=merge['name'], key=key, variants=len(values), user_ids=merge['user_ids'])
                                for key, values in sorted(by_key.items()) if len(values) > 1)
    return dict(ok=True, active=False, mode=wx.get('installation', {}).get('mode', 'local'),
                database=str(database), state=state, sources=sources, errors=[],
                counts=dict(conversations=len(conversations), bindings=len(bindings), aliases=len(aliases),
                            policies=sum(c['policy'] is not None for c in conversations.values()),
                            subscriptions=sum(len(c['subscriptions']) for c in conversations.values())),
                same_name_merges=merges, memory_conflicts=memory_conflicts)


def preview_contacts(root):
    """Return a credential-free, read-only contact migration report."""
    root = Path(root).resolve()
    try:
        return _collect(root)
    except (ValueError, TypeError, KeyError, AttributeError, OSError, sqlite3.Error) as exc:
        # Parser errors can include entire source lines containing secrets.
        message = str(exc) if isinstance(exc, ValueError) else f'invalid contact source ({type(exc).__name__})'
        return dict(ok=False, active=False, database='', sources=[], errors=[message])


def _ensure_stopped(root):
    sources = []
    _, (_, bt), (_, wx), (_, lg) = _layout(root, sources)
    mode = wx.get('installation', {}).get('mode', 'local')
    listeners = [('wxbot', wx.get('outbound', {}), 8765), ('log', lg.get('server', {}), 8788)]
    if mode == 'local':
        listeners.append(('butler', bt.get('server', {}), 8770))
    for name, config, default in listeners:
        host, port = config.get('host', '127.0.0.1'), config.get('port', default)
        if not isinstance(host, str) or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError(f'invalid {name} service port')
        family = socket.AF_INET6 if ':' in host else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as listener:
            if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind((host, port))
            except OSError:
                raise ValueError(f'{name} service port {port} is occupied; stop old writers before migration') from None


def _backup_database(source, target):
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as old:
        with closing(sqlite3.connect(target)) as new:
            old.backup(new)


def _stage_contacts(path, report):
    from butler.business import BusinessStore
    from butler.identity.user_registry import UserRegistry
    from butler.identity.directory import DirectoryStore
    from butler.identity.contact_identity import ensure_schema, merge_same_named, normalize_name, adopt_legacy_notes
    # These constructors can perform additive upgrades: only call them on staging.
    DirectoryStore(path)
    business = BusinessStore(path)
    registry = UserRegistry(business)
    store = ContactStore(path)
    state = deepcopy(report['state'])
    with business.transaction() as db:
        ensure_schema(db)
        for observation in sorted(state['aliases'], key=lambda a: (a['source'] != 'manual', a['group'], a['member_key'])):
            if not observation['group'] or observation['pending']:
                continue
            group, key, nickname = observation['group'], observation['member_key'], observation['name']
            keyed = list(db.execute('SELECT b.binding_id FROM user_bindings b WHERE b.channel_type="group" AND b.contact=? AND '
                '(EXISTS(SELECT 1 FROM user_member_aliases a WHERE a.binding_id=b.binding_id AND a.member_key=?) OR '
                'EXISTS(SELECT 1 FROM user_observation_keys o WHERE o.binding_id=b.binding_id AND o.member_key=?))', (group, key, key)))
            if keyed:
                # Existing exact observations, including ambiguous ones and
                # disabled identities, retain their original relationships.
                continue
            unkeyed = list(db.execute('SELECT b.binding_id FROM user_bindings b LEFT JOIN user_binding_names n '
                'ON n.binding_id=b.binding_id WHERE b.channel_type="group" AND b.contact=? '
                'AND COALESCE(n.nickname,b.nickname)=? AND NOT EXISTS(SELECT 1 FROM user_member_aliases a WHERE a.binding_id=b.binding_id) '
                'AND NOT EXISTS(SELECT 1 FROM user_observation_keys o WHERE o.binding_id=b.binding_id)', (group, nickname)))
            if len(unkeyed) == 1:
                binding = unkeyed[0]['binding_id']
            else:
                internal = nickname
                if db.execute('SELECT 1 FROM user_bindings WHERE channel_type="group" AND contact=? AND nickname=?', (group, internal)).fetchone():
                    internal = nickname[:160] + '（' + uuid.uuid4().hex[:12] + '）'
                created = registry._create(db, 'group', group, internal, identity_confirmed=False,
                                          nickname_confirmed=bool(normalize_name(nickname)), actual_nickname=nickname)
                binding = created['binding_id']
            db.execute('INSERT OR IGNORE INTO user_observation_keys VALUES(?,?)', (binding, key))
        merged = merge_same_named(db)
        for c in state['conversations']:
            if c['channel_type'] == 'group':
                c['person_id'] = ''
                continue
            binding = db.execute('SELECT user_id FROM user_bindings WHERE channel_type="dm" AND contact=? ORDER BY created_at,binding_id', (c['name'],)).fetchone()
            if binding:
                c['person_id'] = binding[0]
                continue
            name = normalize_name(c['name'])
            matches = [r['user_id'] for r in db.execute('SELECT p.user_id,p.display_name FROM user_profiles p WHERE NOT EXISTS '
                       '(SELECT 1 FROM user_redirects r WHERE r.old_user_id=p.user_id) ORDER BY p.created_at,p.user_id')
                       if name and normalize_name(r['display_name']) == name]
            person = matches[0] if matches else uuid.uuid5(uuid.NAMESPACE_URL, 'butler-person:' + c['name']).hex
            if not matches:
                db.execute('INSERT INTO user_profiles(user_id,display_name,memory_version,created_at) VALUES(?,?,0,?)',
                           (person, c['name'], time.time()))
            c['person_id'] = person
        by_name = {c['name']: c for c in state['conversations']}
        for identity in db.execute('SELECT owner,contact,channel_type FROM identities'):
            destination = by_name.get(identity['contact'])
            if destination and destination['channel_type'] == 'dm' and identity['channel_type'] in {'dm', 'private'}:
                adopt_legacy_notes(db, destination['person_id'], identity['owner'])
        for old in db.execute('SELECT l.old_owner,b.user_id FROM user_legacy_owners l JOIN user_bindings b ON b.binding_id=l.binding_id'):
            adopt_legacy_notes(db, old['user_id'], old['old_owner'])
        db.execute('CREATE TABLE IF NOT EXISTS contact_migrations(source TEXT PRIMARY KEY,digest TEXT,retired INTEGER NOT NULL)')
        for source in report['sources']:
            if source['present']:
                db.execute('INSERT OR REPLACE INTO contact_migrations VALUES(?,?,1)', (source['path'], source['sha256']))
        saved = store._save(db, state, store._snapshot(db)['version'], activate=True)
    # Memory contents remain in the database and authorized memory UI, never a
    # console report or backup manifest that might be shared for diagnostics.
    safe_merge = dict(merged=merged.get('merged', []),
                      conflicts=[dict(key=r['key'], source_user_id=r['source_user_id'])
                                 for r in merged.get('conflicts', [])])
    return saved, safe_merge


def migrate_contacts(root, *, acknowledge_stopped=False):
    """Publish a backed-up migration only after an explicit offline acknowledgement."""
    if acknowledge_stopped is not True:
        raise ValueError('contacts migration requires --acknowledge-stopped after stopping all old writers')
    root = Path(root).resolve()
    _, _, (_, wx), _ = _layout(root, [])
    if wx.get('installation', {}).get('mode', 'local') != 'local':
        raise ValueError('contacts migration currently requires local Butler mode; manage remote identities at their own service')
    report = preview_contacts(root)
    if not report['ok']:
        raise ValueError('; '.join(report['errors']))
    if report['active']:
        return dict(ok=True, already_migrated=True, database=report['database'], version=report['state']['version'])
    _ensure_stopped(root)
    database = Path(report['database'])
    folder = database.parent / 'backups' / ('contacts-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    backup = folder / 'business.sqlite3'
    if database.exists():
        _backup_database(database, backup)
    original_digest = _database_digest(database)
    source_folder = folder / 'sources'
    source_folder.mkdir()
    manifest = []
    for index, source in enumerate(report['sources']):
        path = Path(source['path'])
        if _digest(path) != source['sha256']:
            raise ValueError('contact source changed after preview; retry migration')
        if source['present'] and source['kind'] != 'nickname observations':
            destination = source_folder / (str(index) + '-' + path.name)
            shutil.copyfile(path, destination)
            manifest.append(dict(source=str(path), backup=str(destination), sha256=source['sha256']))
    (folder / 'manifest.json').write_text(json.dumps(dict(database=str(database), sources=manifest), ensure_ascii=False, indent=2), encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='stage-', dir=folder) as temporary:
        staged = Path(temporary) / 'business.sqlite3'
        if backup.exists():
            _backup_database(backup, staged)
        state, merged = _stage_contacts(staged, report)
        _ensure_stopped(root)
        if _database_digest(database) != original_digest or any(_digest(Path(s['path'])) != s['sha256'] for s in report['sources']):
            raise ValueError('contact source changed during migration; original database was left unchanged')
        # SQLite backup owns one destination transaction, including active flag,
        # identity redirects and migration ledger. No partial import is visible.
        _backup_database(staged, database)
    return dict(ok=True, already_migrated=False, database=str(database), version=state['version'],
                counts=report['counts'], merged=merged,
                backup=dict(database=str(backup) if backup.exists() else None, directory=str(folder), manifest=str(folder / 'manifest.json')),
                retired_sources=[s['path'] for s in report['sources'] if s['present']])
