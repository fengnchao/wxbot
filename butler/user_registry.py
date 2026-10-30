"""Administrator-owned identities and memory scopes. Avatar hashes are evidence, not IDs."""
import json
from pathlib import Path
import sqlite3
import time
import uuid
import heapq
from contextlib import closing
from threading import RLock

from common.avatar_identity import avatar_distance, decode_avatar, normalize_avatar
from . import contact_identity


class VersionConflict(ValueError):
    pass


def _text(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(label + '不能为空或过长')
    return value.strip()


class UserRegistry:
    def __init__(self, store):
        self.store = store
        self._observe_lock = RLock()
        # Back up an existing business database before the additive migration.
        with closing(sqlite3.connect(store.path)) as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='user_bindings'").fetchone()
            columns = {row[1] for row in db.execute('PRAGMA table_info(user_bindings)')}
            observation_table = db.execute("SELECT 1 FROM sqlite_master WHERE name='user_observation_keys'").fetchone()
            if not exists or not observation_table or not {'identity_confirmed','nickname_confirmed'}.issubset(columns):
                folder = store.path.parent / 'backups'
                folder.mkdir(parents=True, exist_ok=True)
                with closing(sqlite3.connect(folder / ('users-' + uuid.uuid4().hex + '.sqlite3'))) as target:
                    db.backup(target)
        with store.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
                memory_version INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS user_bindings (
                binding_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                channel_type TEXT NOT NULL, contact TEXT NOT NULL, nickname TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL, UNIQUE(channel_type,contact,nickname))''')
            db.execute('''CREATE TABLE IF NOT EXISTS user_avatars (
                id TEXT PRIMARY KEY, binding_id TEXT NOT NULL, image TEXT NOT NULL,
                feature TEXT NOT NULL, algorithm TEXT NOT NULL, created_at REAL NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS user_member_aliases (
                binding_id TEXT NOT NULL, member_key TEXT NOT NULL,
                PRIMARY KEY(binding_id,member_key))''')
            db.execute('''CREATE TABLE IF NOT EXISTS user_observation_keys (
                binding_id TEXT NOT NULL, member_key TEXT NOT NULL,
                PRIMARY KEY(binding_id,member_key))''')
            db.execute('''CREATE TABLE IF NOT EXISTS user_audit (
                id INTEGER PRIMARY KEY, binding_id TEXT NOT NULL, action TEXT NOT NULL,
                details TEXT NOT NULL, at REAL NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS user_legacy_owners (
                old_owner TEXT PRIMARY KEY, binding_id TEXT NOT NULL)''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(user_bindings)')}
            for column in ('identity_confirmed', 'nickname_confirmed'):
                if column not in columns:
                    db.execute(f'ALTER TABLE user_bindings ADD COLUMN {column} INTEGER NOT NULL DEFAULT 1')
            contact_identity.ensure_schema(db)

    @staticmethod
    def _audit(db, binding, action, details):
        db.execute('INSERT INTO user_audit(binding_id,action,details,at)VALUES(?,?,?,?)',
                   (binding, action, json.dumps(details, ensure_ascii=False), time.time()))

    @staticmethod
    def _get(db, binding_id):
        row = db.execute('SELECT * FROM user_bindings WHERE binding_id=?', (binding_id,)).fetchone()
        if not row:
            raise ValueError('用户绑定不存在')
        return row

    def _row(self, db, binding_id):
        row = dict(self._get(db, binding_id))
        row['nickname'] = contact_identity.binding_name(db, row)
        picture = db.execute('SELECT image FROM user_avatars WHERE binding_id=? ORDER BY created_at DESC LIMIT 1', (binding_id,)).fetchone()
        row['avatar'] = 'data:image/png;base64,' + picture[0] if picture else ''
        row['memory_owner'] = 'user:' + row['user_id']
        row['memory_count'] = db.execute('SELECT COUNT(*)FROM memory WHERE owner=?', (row['memory_owner'],)).fetchone()[0]
        if contact_identity.is_active(db):
            row['memory_count'] = len(contact_identity.memory_items(db, row['user_id']))
        row['memory_version'] = db.execute('SELECT memory_version FROM user_profiles WHERE user_id=?', (row['user_id'],)).fetchone()[0]
        row['status'] = ('confirmed' if row['identity_confirmed'] else 'observed') if row['enabled'] else 'disabled'
        row['mention_name'] = row['nickname'] if row['nickname_confirmed'] and row['status'] == 'confirmed' else ''
        row['observed_member_keys'] = [r[0] for r in db.execute(
            'SELECT member_key FROM user_member_aliases WHERE binding_id=? UNION '
            'SELECT member_key FROM user_observation_keys WHERE binding_id=?', (binding_id,binding_id))]
        observed = db.execute("SELECT details FROM user_audit WHERE binding_id=? AND action='observed' ORDER BY id DESC LIMIT 1",
                              (binding_id,)).fetchone()
        confirmation = db.execute("SELECT action FROM user_audit WHERE binding_id=? AND action IN "
                                  "('observed','binding_updated','linked') ORDER BY id DESC LIMIT 1",
                                  (binding_id,)).fetchone()
        row['legacy_import_allowed'] = confirmation is None or confirmation[0] != 'observed'
        if observed:
            key = json.loads(observed[0]).get('member_key')
            if key and key not in row['observed_member_keys']:
                row['observed_member_keys'].append(key)
        row['avatar_count'] = db.execute('SELECT COUNT(*) FROM user_avatars WHERE binding_id=?', (binding_id,)).fetchone()[0]
        return row

    def _create(self, db, channel_type, contact, nickname, feature=None, *, identity_confirmed=True,
                nickname_confirmed=True, actual_nickname=None):
        if channel_type not in {'dm', 'group'}:
            raise ValueError('会话类型必须为 dm 或 group')
        contact, nickname = _text(contact, '会话名称'), _text(nickname, '昵称')
        if channel_type == 'dm' and db.execute('SELECT 1 FROM user_bindings WHERE channel_type=? AND contact=?', ('dm', contact)).fetchone():
            raise ValueError('该私聊已有用户绑定')
        effective_name = actual_nickname if actual_nickname is not None else nickname
        user_id = contact_identity.reuse_person(db, effective_name)
        binding_id = uuid.uuid4().hex
        if user_id is None:
            user_id = uuid.uuid4().hex
            db.execute('INSERT INTO user_profiles VALUES(?,?,0,?)', (user_id, effective_name, time.time()))
        try:
            db.execute('INSERT INTO user_bindings(binding_id,user_id,channel_type,contact,nickname,enabled,'
                       'version,created_at,identity_confirmed,nickname_confirmed) VALUES(?,?,?,?,?,1,1,?,?,?)',
                       (binding_id, user_id, channel_type, contact, nickname, time.time(),
                        int(identity_confirmed), int(nickname_confirmed)))
        except sqlite3.IntegrityError:
            raise ValueError('该会话昵称已有绑定') from None
        if actual_nickname is not None:
            db.execute('INSERT INTO user_binding_names VALUES(?,?)', (binding_id, actual_nickname))
        if feature:
            self._add_avatar(db, binding_id, feature)
        contact_identity.touch_version(db)
        self._audit(db, binding_id, 'created', {'channel_type': channel_type, 'contact': contact})
        return self._row(db, binding_id)

    @staticmethod
    def _add_avatar(db, binding_id, feature):
        if not db.execute('SELECT 1 FROM user_avatars WHERE binding_id=? AND image=?', (binding_id, feature['image'])).fetchone():
            db.execute('INSERT INTO user_avatars VALUES(?,?,?,?,?,?)',
                       (uuid.uuid4().hex, binding_id, feature['image'], feature['hash'], feature['algorithm'], time.time()))
            contact_identity.touch_version(db)

    def create(self, channel_type, contact, nickname, avatar):
        feature = normalize_avatar(decode_avatar(avatar))
        with self.store.transaction() as db:
            return self._create(db, channel_type, contact, nickname, feature)

    def list_users(self, query='', contact='', offset=0, limit=50, channel_type='', status=''):
        if channel_type not in {'','dm','group'} or status not in {'','confirmed','disabled','observed'}:
            raise ValueError('身份筛选无效')
        offset, limit = max(0, int(offset)), min(100, max(1, int(limit)))
        with self.store.transaction() as db:
            where = 'WHERE (?=\'\' OR contact=?) AND (?=\'\' OR nickname LIKE ? OR contact LIKE ? OR user_id LIKE ?'
            args = (contact, contact, query, '%' + query + '%', '%' + query + '%', '%' + query + '%')
            if contact_identity.is_active(db):
                where += ' OR EXISTS(SELECT 1 FROM user_name_history h WHERE h.user_id=user_bindings.user_id AND h.name LIKE ?)'
                where += ' OR EXISTS(SELECT 1 FROM user_binding_names n WHERE n.binding_id=user_bindings.binding_id AND n.nickname LIKE ?)'
                args += ('%' + query + '%', '%' + query + '%')
            where += ')'
            if channel_type:
                where += ' AND channel_type=?'; args += (channel_type,)
            if status:
                where += ' AND enabled=?'; args += (int(status!='disabled'),)
                if status != 'disabled':
                    where += ' AND identity_confirmed=?'; args += (int(status=='confirmed'),)
            total = db.execute('SELECT COUNT(*)FROM user_bindings ' + where, args).fetchone()[0]
            rows = db.execute('SELECT binding_id FROM user_bindings ' + where + ' ORDER BY contact,nickname,binding_id LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
            return {'rows': [self._row(db, row[0]) for row in rows], 'total': total, 'offset': offset, 'limit': limit}

    def update_binding(self, binding_id, version, **changes):
        if set(changes) - {'nickname', 'contact', 'enabled', 'avatar', 'member_key'}:
            raise ValueError('不支持的绑定字段')
        feature = normalize_avatar(decode_avatar(changes['avatar'])) if changes.get('avatar') else None
        with self.store.transaction() as db:
            row = self._get(db, binding_id)
            if type(version) is not int or row['version'] != version:
                raise VersionConflict('绑定已更新，请刷新后重试')
            old_name = contact_identity.binding_name(db, row)
            nickname = _text(changes.get('nickname', old_name), '昵称')
            contact = _text(changes.get('contact', row['contact']), '会话名称')
            enabled = changes.get('enabled', bool(row['enabled']))
            if type(enabled) is not bool:
                raise ValueError('启用状态必须为布尔值')
            if row['channel_type'] == 'dm' and db.execute('SELECT 1 FROM user_bindings WHERE channel_type=? AND contact=? AND binding_id!=?', ('dm', contact, binding_id)).fetchone():
                raise ValueError('该私聊已有用户绑定')
            nickname_confirmed = row['nickname_confirmed'] or nickname != old_name
            active = contact_identity.is_active(db)
            stored_name = nickname
            if active and db.execute('SELECT 1 FROM user_bindings WHERE channel_type=? AND contact=? '
                    'AND nickname=? AND binding_id!=?', (row['channel_type'], contact, nickname, binding_id)).fetchone():
                stored_name = nickname[:160] + '（' + binding_id[:12] + '）'
            try:
                db.execute('UPDATE user_bindings SET nickname=?,contact=?,enabled=?,identity_confirmed=1,'
                           'nickname_confirmed=?,version=version+1 WHERE binding_id=?',
                           (stored_name, contact, int(enabled), int(nickname_confirmed), binding_id))
            except sqlite3.IntegrityError:
                raise ValueError('该会话昵称已有绑定') from None
            if active:
                if stored_name != nickname:
                    db.execute('INSERT OR REPLACE INTO user_binding_names VALUES(?,?)', (binding_id, nickname))
                else:
                    db.execute('DELETE FROM user_binding_names WHERE binding_id=?', (binding_id,))
                if nickname != old_name:
                    contact_identity.remember_name(db, row['user_id'], old_name)
                    profile = db.execute('SELECT display_name FROM user_profiles WHERE user_id=?', (row['user_id'],)).fetchone()
                    if contact_identity.normalize_name(profile[0]) == contact_identity.normalize_name(old_name):
                        db.execute('UPDATE user_profiles SET display_name=? WHERE user_id=?', (nickname, row['user_id']))
                    contact_identity.merge_same_named(db)
            if feature:
                self._add_avatar(db, binding_id, feature)
            if not row['identity_confirmed']:
                # Saving an explicitly pending identity is an administrator confirmation.
                self._confirm_observation_keys(db,binding_id)
            if changes.get('member_key'):
                alias = _text(changes['member_key'], '头像观测ID', 128)
                db.execute('INSERT OR IGNORE INTO user_member_aliases VALUES(?,?)', (binding_id, alias))
            contact_identity.touch_version(db)
            self._audit(db, binding_id, 'binding_updated', {'fields': list(changes)})
            return self._row(db, binding_id)

    def _confirm_observation_keys(self, db, binding_id):
        binding = self._get(db,binding_id)
        for (key,) in db.execute('SELECT member_key FROM user_observation_keys WHERE binding_id=?', (binding_id,)).fetchall():
            collision = db.execute('''SELECT 1 FROM user_bindings b WHERE b.contact=? AND b.channel_type=?
                AND b.binding_id!=? AND (EXISTS(SELECT 1 FROM user_observation_keys o
                    WHERE o.binding_id=b.binding_id AND o.member_key=?) OR
                    EXISTS(SELECT 1 FROM user_member_aliases a WHERE a.binding_id=b.binding_id AND a.member_key=?)) LIMIT 1''',
                (binding['contact'],binding['channel_type'],binding_id,key,key)).fetchone()
            if not collision:
                db.execute('INSERT OR IGNORE INTO user_member_aliases VALUES(?,?)', (binding_id,key))

    @staticmethod
    def _disabled_named_person(db, nickname):
        user_id = contact_identity.reuse_person(db, nickname)
        return bool(user_id and db.execute('SELECT 1 FROM user_bindings WHERE user_id=?', (user_id,)).fetchone()
                    and not db.execute('SELECT 1 FROM user_bindings WHERE user_id=? AND enabled=1', (user_id,)).fetchone())

    def resolve(self, contact, channel_type, member_key='', avatar='', nickname=''):
        with self.store.transaction() as db:
            if channel_type == 'dm':
                rows = db.execute('SELECT binding_id FROM user_bindings WHERE channel_type=? AND contact=? AND enabled=1', ('dm', contact)).fetchall()
                if not rows and not db.execute('SELECT 1 FROM user_bindings WHERE channel_type=? AND contact=?', ('dm', contact)).fetchone():
                    if self._disabled_named_person(db, nickname or contact):
                        return self._unknown('disabled')
                    return self._create(db, 'dm', contact, nickname or contact)
                return self._row(db, rows[0][0]) if len(rows) == 1 else self._unknown('unknown')
            rows = db.execute('''SELECT a.binding_id,a.image,a.feature,b.nickname,b.nickname_confirmed FROM user_avatars a
                JOIN user_bindings b ON a.binding_id=b.binding_id
                WHERE b.channel_type='group' AND b.contact=? AND b.enabled=1''', (contact,)).fetchall()
            aliases = db.execute('''SELECT a.binding_id FROM user_member_aliases a JOIN user_bindings b
                ON a.binding_id=b.binding_id WHERE b.contact=? AND b.channel_type='group' AND b.enabled=1 AND a.member_key=?''', (contact, member_key)).fetchall() if member_key else []
            if aliases:
                return self._row(db,aliases[0][0]) if len(aliases)==1 else self._unknown('ambiguous')
            if contact_identity.is_active(db):
                rows = [dict(row) for row in rows]
                for row in rows:
                    row['nickname'] = contact_identity.binding_name(db, row)
            matches = {}
            conflicting = False
            named = bool(contact_identity.normalize_name(nickname))
            if avatar:
                try:
                    candidate = normalize_avatar(decode_avatar(avatar))
                    if not 1 < int(candidate['hash'],16).bit_count() < 63:
                        return self._unknown('unknown')
                    for row in rows:
                        score = self._avatar_score(candidate,row['image'],row['feature'])
                        if score is not None:
                            if named and row['nickname_confirmed'] and contact_identity.normalize_name(nickname) != contact_identity.normalize_name(row['nickname']):
                                conflicting = True
                                continue
                            matches[row['binding_id']] = min(score, matches.get(row['binding_id'], float('inf')))
                except ValueError:
                    pass
            ranked = sorted(matches, key=matches.get)
            if len(ranked) > 1 and matches[ranked[1]] - matches[ranked[0]] < 2:
                return self._unknown('ambiguous')
            if ranked:
                row = self._row(db, ranked[0])
                if not named and not row['legacy_import_allowed']:
                    # A common avatar without the original nickname is not enough
                    # evidence to expose an automatically enrolled person's notes.
                    row.update(status='observed',memory_owner='',mention_name='')
                return row
            if conflicting:
                return self._unknown('ambiguous')
            if not avatar and member_key:
                observed = db.execute('''SELECT b.binding_id,COALESCE(n.nickname,b.nickname) AS nickname FROM user_observation_keys o
                    JOIN user_bindings b ON b.binding_id=o.binding_id
                    LEFT JOIN user_binding_names n ON n.binding_id=b.binding_id
                    WHERE b.contact=? AND b.channel_type='group' AND b.enabled=1 AND o.member_key=?''',
                    (contact,member_key)).fetchall()
                if named:
                    observed = [row for row in observed if row['nickname'] == nickname.strip()]
                if len(observed) == 1:
                    row = self._row(db,observed[0]['binding_id'])
                    # Automatic keys only deduplicate observations. They are never authority.
                    row.update(status='observed',memory_owner='',mention_name='')
                    return row
                if observed:
                    return self._unknown('ambiguous')
            return self._unknown('unknown')

    @staticmethod
    def _avatar_score(candidate, image, feature):
        distance = (int(candidate['hash'],16) ^ int(feature,16)).bit_count()
        if distance <= 4:
            _, color_error = avatar_distance(candidate['image'],image)
            if color_error <= 24:
                return distance + color_error / 24
        return None

    def observe(self, contact, channel_type, member_key='', avatar='', nickname=''):
        """Create an empty, isolated identity independently of a model request."""
        if channel_type not in {'dm', 'group'}:
            raise ValueError('会话类型必须为 dm 或 group')
        contact = _text(contact, '会话名称')
        if not all(isinstance(value, str) for value in (member_key, avatar, nickname)):
            raise ValueError('身份观测字段必须为文本')
        with self._observe_lock:
            resolved = self.resolve(contact, channel_type, member_key, avatar, nickname)
            feature = normalize_avatar(decode_avatar(avatar)) if avatar else None
            if resolved['status'] not in {'unknown','ambiguous'}:
                if channel_type == 'dm' and feature and resolved.get('binding_id'):
                    with self.store.transaction() as db:
                        self._add_avatar(db, resolved['binding_id'], feature)
                        return self._row(db, resolved['binding_id'])
                if (channel_type == 'group' and resolved['status']=='confirmed'
                        and member_key and not member_key.startswith('unknown-')):
                    key = _text(member_key, '头像观测ID', 128)
                    with self.store.transaction() as db:
                        db.execute('INSERT OR IGNORE INTO user_observation_keys VALUES(?,?)', (resolved['binding_id'],key))
                        return self._row(db,resolved['binding_id'])
                return resolved
            if channel_type == 'dm':
                return resolved  # A disabled private identity must not be recreated.
            key = member_key if member_key and not member_key.startswith('unknown-') else feature['hash'] if feature else ''
            if not key:
                return resolved  # No durable evidence with which to deduplicate a person.
            key = _text(key, '头像观测ID', 128)
            with self.store.transaction() as db:
                if self._disabled_named_person(db, nickname):
                    return self._unknown('disabled')
                # A disabled identity must not reappear as a new enabled user.
                disabled = db.execute('''SELECT b.binding_id,a.image,a.feature,m.member_key,
                    o.member_key AS observed_key FROM user_bindings b
                    LEFT JOIN user_member_aliases m ON m.binding_id=b.binding_id
                    LEFT JOIN user_observation_keys o ON o.binding_id=b.binding_id
                    LEFT JOIN user_avatars a ON a.binding_id=b.binding_id
                    WHERE b.contact=? AND b.channel_type='group' AND b.enabled=0''', (contact,)).fetchall()
                for item in disabled:
                    if (item['member_key']==key or (not feature and item['observed_key']==key)
                            or (feature and item['image'] and self._avatar_score(feature,item['image'],item['feature']) is not None)):
                        return self._unknown('disabled')
                named = bool(contact_identity.normalize_name(nickname))
                active = contact_identity.is_active(db)
                if active and named:
                    for item in db.execute("SELECT * FROM user_bindings WHERE contact=? AND channel_type='group' AND enabled=0", (contact,)):
                        if contact_identity.normalize_name(contact_identity.binding_name(db, item)) == contact_identity.normalize_name(nickname):
                            return self._unknown('disabled')
                existing = db.execute('''SELECT b.binding_id,COALESCE(n.nickname,b.nickname) AS nickname,b.identity_confirmed FROM user_observation_keys o
                    JOIN user_bindings b ON b.binding_id=o.binding_id
                    LEFT JOIN user_binding_names n ON n.binding_id=b.binding_id
                    WHERE b.contact=? AND b.channel_type='group' AND b.enabled=1 AND o.member_key=?''', (contact,key)).fetchall()
                pending = [item for item in existing if not item['identity_confirmed']
                           and (not named or item['nickname']==nickname.strip())]
                if len(pending)==1:
                    if feature:
                        self._add_avatar(db,pending[0]['binding_id'],feature)
                    return self._row(db,pending[0]['binding_id'])
                name = nickname.strip() if named else '待命名-' + key[:12]
                actual_nickname = None
                if db.execute('SELECT 1 FROM user_bindings WHERE channel_type=? AND contact=? AND nickname=?',
                              ('group', contact, name)).fetchone():
                    if active and named:
                        actual_nickname = name
                    name = name[:160] + '（' + uuid.uuid4().hex[:12] + '）'
                    if not actual_nickname:
                        named = False
                row = self._create(db, 'group', contact, name, feature,
                    identity_confirmed=bool(feature and named and not existing and resolved['status']!='ambiguous'
                                            and 1 < int(feature['hash'],16).bit_count() < 63), nickname_confirmed=named,
                    actual_nickname=actual_nickname)
                db.execute('INSERT INTO user_observation_keys VALUES(?,?)', (row['binding_id'], key))
                self._audit(db, row['binding_id'], 'observed', {'member_key': key, 'has_avatar': bool(feature)})
                return self._row(db, row['binding_id'])

    @staticmethod
    def _unknown(status):
        return {'binding_id': '', 'user_id': '', 'memory_owner': '', 'memory_version': 0, 'status': status}

    def memories(self, binding_id):
        with self.store.transaction() as db:
            row = self._row(db, binding_id)
            items = [dict(r) for r in db.execute('SELECT key,value,updated FROM memory WHERE owner=? ORDER BY key', (row['memory_owner'],))]
            if contact_identity.is_active(db):
                items = contact_identity.memory_items(db, row['user_id'])
            return {'binding': row, 'items': items, 'version': row['memory_version']}

    def change_memory(self, binding_id, key, value, version, delete=False):
        key = _text(key, '记忆 key')
        with self.store.transaction() as db:
            row = self._row(db, binding_id)
            if type(version) is not int or version != row['memory_version']:
                raise VersionConflict('记忆已更新，请刷新后重试')
            old = db.execute('SELECT value FROM memory WHERE owner=? AND key=?', (row['memory_owner'], key)).fetchone()
            if delete:
                self.store.delete_memory(row['memory_owner'], key, db=db,source='administrator')
            else:
                self.store.set_memory(row['memory_owner'], key, value, db=db,source='administrator')
            if contact_identity.is_active(db):
                db.execute('DELETE FROM user_memory_variants WHERE user_id=? AND key=?', (row['user_id'], key))
            self._audit(db, binding_id, 'memory_deleted' if delete else 'memory_set', {'key': key, 'previous': old[0] if old else None, 'value': None if delete else value, 'source': 'administrator'})
            return {'ok': True, 'version': self._row(db, binding_id)['memory_version']}

    def link(self, binding_id, target_id, version, resolutions=None, expected_versions=None):
        with self.store.transaction() as db:
            source, target = self._row(db, binding_id), self._row(db, target_id)
            if source['version'] != version:
                raise VersionConflict('绑定已更新，请刷新后重试')
            if expected_versions is not None and expected_versions != {'source_memory':source['memory_version'],
                    'target_memory':target['memory_version'],'target_binding':target['version']}:
                raise VersionConflict('合并预览已过期，请重新查看两侧记忆')
            if source['user_id'] == target['user_id']:
                return source
            if contact_identity.is_active(db):
                result = contact_identity.merge_users(db, source['user_id'], target['user_id'])
                db.execute('UPDATE user_bindings SET identity_confirmed=1 WHERE binding_id=?', (binding_id,))
                self._confirm_observation_keys(db, binding_id)
                self._audit(db, binding_id, 'linked', {'previous_user_id': source['user_id'],
                    'user_id': target['user_id'], 'retained_conflicts': len(result['conflicts'])})
                contact_identity.touch_version(db)
                return self._row(db, binding_id)
            source_notes = dict(db.execute('SELECT key,value FROM memory WHERE owner=?',(source['memory_owner'],)))
            target_notes = dict(db.execute('SELECT key,value FROM memory WHERE owner=?',(target['memory_owner'],)))
            conflicts = [{'key': k, 'source': v, 'target': target_notes[k]} for k, v in source_notes.items() if k in target_notes and v != target_notes[k]]
            if conflicts and (not isinstance(resolutions, dict) or any(resolutions.get(c['key']) not in {'source', 'target'} for c in conflicts)):
                return {'conflicts': conflicts, 'source': source, 'target': target, 'requires_confirmation': True}
            for key, value in source_notes.items():
                if key not in target_notes or resolutions and resolutions.get(key) == 'source':
                    self.store.set_memory(target['memory_owner'], key, value, db=db,source='administrator')
            db.execute('UPDATE user_bindings SET user_id=?,identity_confirmed=1,version=version+1 WHERE binding_id=?', (target['user_id'], binding_id))
            self._confirm_observation_keys(db,binding_id)
            # Invalidate both memory-derived and binding-derived thread scopes even when no notes were merged.
            db.execute('UPDATE user_profiles SET memory_version=memory_version+1 WHERE user_id=?', (target['user_id'],))
            self._audit(db, binding_id, 'linked', {'previous_user_id': source['user_id'], 'user_id': target['user_id'], 'resolutions': resolutions or {}})
            return self._row(db, binding_id)

    def audit(self, binding_id, offset=0, limit=50):
        with self.store.transaction() as db:
            self._get(db, binding_id)
            rows = [dict(r) for r in db.execute('SELECT * FROM user_audit WHERE binding_id=? ORDER BY id DESC LIMIT ? OFFSET ?', (binding_id, min(100, max(1, int(limit))), max(0, int(offset))))]
            for row in rows:
                row['details'] = json.loads(row['details'])
            return {'rows': rows, 'total': db.execute('SELECT COUNT(*)FROM user_audit WHERE binding_id=?', (binding_id,)).fetchone()[0]}

    def adopt_legacy(self, binding_id, old_owner):
        """Only called with a server-computed legacy owner and an explicit binding."""
        with self.store.transaction() as db:
            row = self._row(db, binding_id)
            if db.execute('SELECT 1 FROM user_legacy_owners WHERE old_owner=?', (old_owner,)).fetchone():
                return
            notes = [dict(r)for r in db.execute('SELECT key,value FROM memory WHERE owner=?',(old_owner,))]
            if contact_identity.is_active(db):
                contact_identity.adopt_legacy_notes(db, row['user_id'], old_owner)
            else:
                for note in notes:
                    current = db.execute('SELECT value FROM memory WHERE owner=? AND key=?', (row['memory_owner'], note['key'])).fetchone()
                    if current and current[0] != note['value']:
                        raise ValueError('旧记忆存在冲突，需要在用户管理中处理')
                    self.store.set_memory(row['memory_owner'], note['key'], note['value'], db=db,source='legacy_import')
            # Reminder authority remains tied to the original conversation binding,
            # even if its memory is explicitly shared with another conversation.
            db.execute('UPDATE reminders SET owner=? WHERE owner=? AND contact=?',
                ('binding:'+binding_id,old_owner,row['contact']))
            db.execute('INSERT INTO user_legacy_owners VALUES(?,?)', (old_owner, binding_id))
            if notes:
                self._audit(db, binding_id, 'legacy_imported', {'old_owner': old_owner, 'count': len(notes)})

    def recall(self, memory_owner, query, max_chars=2000):
        tokens = set(query.lower().split()) | {query[i:i + 2] for i in range(max(0, len(query) - 1))}
        def relevance(row):
            return (sum(t in (row['key']+' '+row['value']).lower() for t in tokens if len(t)>1),row['updated'])
        # Stream this owner's notes into a bounded heap; recent-100 truncation
        # before ranking can permanently hide an older but exact preference.
        with self.store.transaction() as db:
            if contact_identity.is_active(db) and memory_owner.startswith('user:'):
                available = contact_identity.memory_items(db, memory_owner[5:])
                best = heapq.nlargest(10, available, key=relevance)
                keys = {row['key'] for row in best}
                rows = sorted((row for row in available if row['key'] in keys), key=relevance, reverse=True)
            else:
                available = (dict(row) for row in db.execute('SELECT key,value,updated FROM memory WHERE owner=?', (memory_owner,)))
                rows = heapq.nlargest(10, available, key=relevance)
        selected, used = [], 0
        for row in rows:
            text = row['key'] + ': ' + row['value']
            if used + len(text) > max_chars:
                continue
            item = {'key': row['key'], 'value': row['value']}
            for field in ('source', 'source_label', 'source_user_id', 'source_user_ids', 'source_labels'):
                if field in row:
                    item[field] = row[field]
            selected.append(item); used += len(text)
        return selected
