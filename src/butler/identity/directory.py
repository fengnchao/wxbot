"""Butler-owned local channel directory; never grants identity or tool permissions."""
from contextlib import contextmanager, closing
from copy import deepcopy
import json
from pathlib import Path, PureWindowsPath
import sqlite3
import tomllib


def directory_path(config_path, raw=None):
    config_path = Path(config_path).resolve()
    if raw is None:
        raw = tomllib.loads(config_path.read_text('utf-8-sig')) if config_path.exists() else {}
    explicit = (raw.get('directory') or {}).get('database')
    if explicit:
        path = Path(explicit).expanduser()
        return (path if path.is_absolute() else config_path.parent / path).resolve()
    butler = config_path.parent / 'config.butler.toml'
    owner = raw if config_path.name == 'config.butler.toml' else (
        tomllib.loads(butler.read_text('utf-8-sig')) if butler.exists() else {})
    explicit = (owner.get('directory') or {}).get('database')
    value = explicit or str(Path((owner.get('agent') or {}).get('data_dir') or 'data') / 'business.sqlite3')
    path = Path(value).expanduser()
    return (path if path.is_absolute() else config_path.parent / path).resolve()


_CONFIG_NAMES = {'config.butler.toml', 'config.wxbot.toml'}


def migration_source_name(source):
    """Recognize historical absolute keys without following their old locations."""
    if source in _CONFIG_NAMES:
        return source
    path = Path(source)
    windows = PureWindowsPath(source)
    if path.is_absolute() or windows.is_absolute():
        name = windows.name if windows.is_absolute() else path.name
        return name if name in _CONFIG_NAMES else None
    return None


def directory_enabled(config_path, raw):
    path = directory_path(config_path, raw)
    from butler.identity.contact_store import is_unified
    if is_unified(path):
        return True
    if (raw.get('directory') or {}).get('database'):
        return True
    if not path.exists():
        return False
    with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='directory_migrations'").fetchone():
            return False
        name = Path(config_path).name
        return any(migration_source_name(row[0]) == name for row in
                   db.execute('SELECT source FROM directory_migrations'))


class DirectoryStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from butler.identity.contact_store import is_unified
        if is_unified(self.path):
            return
        if self.path.exists():
            with closing(sqlite3.connect(f'{self.path.as_uri()}?mode=ro', uri=True)) as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE name='directory_state'").fetchone():
                    return
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS directory_state(id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS directory_migrations(source TEXT PRIMARY KEY, digest TEXT NOT NULL, fields TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO directory_state VALUES(1,0,?)', (json.dumps(dict(contacts=[],channel={},aliases=[])),))

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _snapshot(db):
        row = db.execute('SELECT version,payload FROM directory_state WHERE id=1').fetchone()
        return dict(json.loads(row['payload']), version=row['version'])

    def snapshot(self):
        from butler.identity.contact_store import ContactStore,is_unified
        if is_unified(self.path):
            return ContactStore(self.path).directory_snapshot()
        with closing(sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=30)) as db:
            db.row_factory = sqlite3.Row
            return self._snapshot(db)

    @staticmethod
    def _save(db, payload, expected_version):
        current = DirectoryStore._snapshot(db)
        if type(expected_version) is not int or expected_version != current['version']:
            raise ValueError('directory version conflict; reload before saving')
        value = {key: deepcopy(payload.get(key, current[key])) for key in ('contacts','channel','aliases')}
        if not isinstance(value['contacts'], list) or not isinstance(value['channel'], dict) or not isinstance(value['aliases'], list):
            raise ValueError('invalid directory payload')
        channel = value['channel']
        if set(channel) - {'bot', 'wechat'}:
            raise ValueError('invalid channel section')
        bot = channel.get('bot', {})
        if not isinstance(bot, dict) or set(bot) - {'bound_users', 'bound_groups', 'mention_names'}:
            raise ValueError('invalid channel bot settings')
        for key, names in bot.items():
            if not isinstance(names, list) or any(not isinstance(name,str) or not name.strip() for name in names):
                raise ValueError(f'bot.{key} must be a list of names')
        if set(bot.get('bound_users', [])) & set(bot.get('bound_groups', [])):
            raise ValueError('contact cannot be both dm and group')
        wechat = channel.get('wechat', {})
        if not isinstance(wechat, dict) or set(wechat) - {'main_window'}:
            raise ValueError('invalid channel wechat settings')
        main = wechat.get('main_window', {})
        if not isinstance(main, dict) or set(main) - {'listen_all'}:
            raise ValueError('invalid channel listening settings')
        if 'listen_all' in main and type(main['listen_all']) is not bool:
            raise ValueError('listen_all must be boolean')
        names = set()
        for row in value['contacts']:
            if not isinstance(row, dict) or not isinstance(row.get('name'),str) or not row['name'].strip():
                raise ValueError('contact name is required')
            name = row['name'].strip()
            if name in names:
                raise ValueError('duplicate contact name; review routes before merging')
            names.add(name)
            for key in ('uid','profile','label','session_key','channel_type'):
                if key in row and not isinstance(row[key],str):
                    raise ValueError(f'contact {key} must be a string')
            if row.get('channel_type') == 'private':
                row['channel_type'] = 'dm'
            if row.get('channel_type','dm') not in {'dm','group'}:
                raise ValueError('contact channel_type must be dm or group')
            if 'session_key' in row:
                try:
                    row['session_key'].format(name=row['name'],uid=row.get('uid') or row['name'],
                        profile=row.get('profile') or 'default',channel_type=row.get('channel_type','dm'))
                except (ValueError,KeyError,IndexError,AttributeError):
                    raise ValueError('invalid contact session_key template') from None
        aliases = set()
        for row in value['aliases']:
            if not isinstance(row, dict):
                raise ValueError('invalid alias')
            for key in ('group','member_key','name','source'):
                if not isinstance(row.get(key),str):
                    raise ValueError(f'alias {key} must be a string')
            if not row['member_key'].strip() or not row['name'].strip() or type(row.get('pending')) is not bool:
                raise ValueError('alias member_key/name and boolean pending required')
            identity = (row['group'],row['member_key'],row['source'])
            if identity in aliases:
                raise ValueError('duplicate alias source')
            aliases.add(identity)
            if row.get('source') not in {'manual','learned','legacy'}:
                raise ValueError('invalid alias source')
            if not row.get('group') and not row.get('pending'):
                raise ValueError('unscoped aliases must remain pending')
        db.execute('UPDATE directory_state SET version=version+1,payload=? WHERE id=1', (json.dumps(value, ensure_ascii=False),))
        return DirectoryStore._snapshot(db)

    def save(self, payload, expected_version):
        from butler.identity.contact_store import ContactStore,is_unified
        if is_unified(self.path):
            return ContactStore(self.path).save_directory(payload,expected_version)
        with self.transaction() as db:
            return self._save(db, payload, expected_version)

    def initialize_channel(self, nickname=''):
        from butler.identity.contact_store import ContactStore,is_unified
        if is_unified(self.path):
            store=ContactStore(self.path);state=store.snapshot()
            if not state['settings']:
                state['settings']={'bot':{'mention_names':[nickname] if nickname else []},'wechat':{'main_window':{'listen_all':True}}}
                store.save(state,state['version'])
            return self.snapshot()
        with self.transaction() as db:
            state = self._snapshot(db)
            if not state['channel']:
                state['channel'] = dict(bot=dict(bound_users=[],bound_groups=[],mention_names=[nickname] if nickname else []),
                    wechat=dict(main_window=dict(listen_all=True)))
                self._save(db,state,state['version'])
        return self.snapshot()

    def channel_projection(self):
        return self.snapshot()['channel']

    def contact_rows(self):
        return self.snapshot()['contacts']

    def member_name(self, group, member_key):
        rows = [row for row in self.snapshot()['aliases'] if row.get('group') == group and
                row['member_key'] == member_key and not row.get('pending')]
        rows.sort(key=lambda row: row.get('source') != 'manual')
        return rows[0]['name'] if rows else ''

    def observe_member(self, group, member_key, name):
        from butler.identity.contact_store import ContactStore,is_unified
        if is_unified(self.path):
            return ContactStore(self.path).observe_member(group,member_key,name)
        if not group or not member_key or not name:
            return
        with self.transaction() as db:
            state = self._snapshot(db)
            row = next((row for row in state['aliases'] if row.get('group') == group and
                row['member_key'] == member_key and row['source'] == 'learned'), None)
            if row is None:
                state['aliases'].append(dict(group=group,member_key=member_key,name=name,source='learned',pending=False))
            else:
                if row['name'] == name:
                    return
                row['name'] = name
            self._save(db,state,state['version'])

class DirectoryContactMap:
    """Live compatibility projection; routing metadata never confirms a user binding."""
    def __init__(self, path):
        self.path = path

    def _current(self):
        from butler.identity.contacts import load_contacts
        return load_contacts(DirectoryStore(self.path).contact_rows())

    @property
    def by_name(self):
        return self._current().by_name

    def get(self, name):
        return self._current().get(name)

    def names(self):
        return self._current().names()

    def profiles(self):
        return self._current().profiles()

    def is_sole_profile_owner(self, contact):
        return self._current().is_sole_profile_owner(contact)
