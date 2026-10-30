import json
from pathlib import Path
import socket
import sqlite3

import pytest


def legacy(root):
    ports = []
    for _ in range(3):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            ports.append(listener.getsockname()[1])
    (root / 'config.butler.toml').write_text(
        '[agent]\nprovider="codex"\ndata_dir="state"\n[directory]\ndatabase="state/business.sqlite3"\n'
        f'[server]\nhost="127.0.0.1"\nport={ports[0]}\ntoken="not-in-report"\n'
        '[[contacts]]\nname="Alice"\nuid="old-uid"\nprofile="old-profile"\n'
        'label="Old label"\nsession_key="old:{uid}"\n', encoding='utf-8')
    (root / 'config.wxbot.toml').write_text(
        '[directory]\ndatabase="state/business.sqlite3"\n'
        '[bot]\nbound_users=["Alice","Listen only"]\nbound_groups=["Team"]\nmention_names=["Robot"]\n'
        '[wechat.main_window]\nlisten_all=false\n'
        f'[outbound]\nhost="127.0.0.1"\nport={ports[1]}\n', encoding='utf-8')
    (root / 'config.log.toml').write_text(
        f'[server]\nhost="127.0.0.1"\nport={ports[2]}\n'
        '[sources]\nhome="state"\ngroups_file="state/cache/butler_groups.json"\n', encoding='utf-8')
    cache = root / 'state' / 'cache'
    cache.mkdir(parents=True)
    (cache / 'butler_heartbeat.json').write_text(json.dumps({'version': 1, 'users': {
        'Policy only': {'role_skill': 'paimon', 'allowed_skills': ['butler-memory'], 'heartbeat_enabled': False},
        'Team': {'role_skill': 'butler-companion', 'allowed_skills': [], 'heartbeat_enabled': True},
    }}), encoding='utf-8')
    (cache / 'butler_groups.json').write_text(json.dumps({'version': 1, 'groups': {
        '1': ['Team', 'Subscription only'], '9': ['Alice'],
    }}), encoding='utf-8')
    return root / 'state' / 'business.sqlite3'


def files(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def test_preview_is_read_only_even_when_database_does_not_exist(tmp_path):
    from butler.contact_migration import preview_contacts
    database = legacy(tmp_path)
    before = files(tmp_path)
    report = preview_contacts(tmp_path)
    assert report['ok'] and not report['active']
    assert report['database'] == str(database)
    assert files(tmp_path) == before
    assert 'not-in-report' not in json.dumps(report)


def test_union_preserves_routes_settings_destinations_and_passive_disabled_identity(tmp_path):
    from butler.contact_migration import migrate_contacts, preview_contacts
    from butler.business import BusinessStore
    from butler.directory import DirectoryStore
    from butler.user_registry import UserRegistry
    from butler.contact_store import ContactStore
    database = legacy(tmp_path)
    registry = UserRegistry(BusinessStore(database))
    with registry.store.transaction() as db:
        passive = registry._create(db, 'group', 'Historic group', 'Alice')
        db.execute('UPDATE user_bindings SET enabled=0 WHERE binding_id=?', (passive['binding_id'],))
    directory = DirectoryStore(database)
    state = directory.snapshot()
    state['contacts'] = [dict(name='Directory only', uid='directory-route', enabled=False)]
    state['channel'] = {'bot': {'bound_users': ['Historical listen'], 'bound_groups': []}}
    state['aliases'] = [dict(group='Historic group', member_key='member', name='Alice', source='manual', pending=False)]
    directory.save(state, state['version'])
    assert preview_contacts(tmp_path)['ok']
    originals = {p: p.read_bytes() for p in tmp_path.glob('config.*.toml')}
    result = migrate_contacts(tmp_path, acknowledge_stopped=True)
    assert result['ok']
    canonical = ContactStore(database).snapshot()
    by_name = {c['name']: c for c in canonical['conversations']}
    assert set(by_name) == {'Alice', 'Listen only', 'Team', 'Policy only', 'Subscription only',
                            'Historic group', 'Directory only', 'Historical listen'}
    alice = by_name['Alice']
    assert (alice['uid'], alice['profile'], alice['label'], alice['session_key']) == (
        'old-uid', 'old-profile', 'Old label', 'old:{uid}')
    assert alice['subscriptions'] == [9]
    assert by_name['Team']['subscriptions'] == [1]
    assert by_name['Subscription only']['subscriptions'] == [1]
    assert by_name['Policy only']['policy'] == {'role_skill': 'paimon', 'allowed_skills': ['butler-memory'], 'heartbeat_enabled': False}
    assert not by_name['Historic group']['listening']
    assert not by_name['Directory only']['enabled']
    assert by_name['Listen only']['listening'] and by_name['Historical listen']['listening']
    assert canonical['settings']['wechat']['main_window']['listen_all'] is False
    assert canonical['settings']['bot']['mention_names'] == ['Robot']
    assert canonical['aliases'][0]['name'] == 'Alice'
    assert {p: p.read_bytes() for p in originals} == originals
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT enabled FROM user_bindings WHERE binding_id=?', (passive['binding_id'],)).fetchone() == (0,)


def test_migration_requires_stop_acknowledgement_and_refuses_occupied_port(tmp_path):
    from butler.contact_migration import migrate_contacts
    legacy(tmp_path)
    before = files(tmp_path)
    with pytest.raises(ValueError, match='acknowledge'):
        migrate_contacts(tmp_path)
    assert files(tmp_path) == before
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); listener.listen()
        config = tmp_path / 'config.log.toml'
        config.write_text(f'[server]\nhost="127.0.0.1"\nport={listener.getsockname()[1]}\n', encoding='utf-8')
        before = files(tmp_path)
        with pytest.raises(ValueError, match='port'):
            migrate_contacts(tmp_path, acknowledge_stopped=True)
        assert files(tmp_path) == before


@pytest.mark.parametrize('body', ['{broken', '{"users": []}', '{"users":{"Alice":{"role_skill":"paimon"}}}'])
def test_malformed_policy_fails_preview_and_migration_before_any_writes(tmp_path, body):
    from butler.contact_migration import preview_contacts, migrate_contacts
    legacy(tmp_path)
    (tmp_path / 'state/cache/butler_heartbeat.json').write_text(body, encoding='utf-8')
    before = files(tmp_path)
    preview = preview_contacts(tmp_path)
    assert not preview['ok'] and preview['errors']
    with pytest.raises(ValueError):
        migrate_contacts(tmp_path, acknowledge_stopped=True)
    assert files(tmp_path) == before


def test_log_relative_group_override_is_preserved_and_conflicts_are_reported(tmp_path):
    from butler.contact_migration import preview_contacts
    legacy(tmp_path)
    logpath = tmp_path / 'config.log.toml'
    logpath.write_text(logpath.read_text('utf-8').replace('state/cache/butler_groups.json', 'overrides/groups.json'), encoding='utf-8')
    override = tmp_path / 'overrides/groups.json'
    override.parent.mkdir()
    override.write_text('{"groups":{"1":["Different destination"]}}', encoding='utf-8')
    report = preview_contacts(tmp_path)
    assert not report['ok']
    assert any('conflict' in error.lower() for error in report['errors'])
    (tmp_path / 'state/cache/butler_groups.json').unlink()
    report = preview_contacts(tmp_path)
    assert report['ok']
    assert next(c for c in report['state']['conversations'] if c['name'] == 'Different destination')['subscriptions'] == [1]


def test_backup_precedes_initial_schema_and_idempotence_keeps_new_edits(tmp_path):
    from butler.contact_migration import migrate_contacts
    from butler.contact_store import ContactStore
    database = legacy(tmp_path)
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE original(value TEXT)')
        db.execute('INSERT INTO original VALUES("keep")')
    result = migrate_contacts(tmp_path, acknowledge_stopped=True)
    backup = Path(result['backup']['database'])
    with sqlite3.connect(backup) as db:
        assert db.execute('SELECT * FROM original').fetchall() == [('keep',)]
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='directory_state'").fetchone()
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='unified_contacts'").fetchone()
    store = ContactStore(database)
    state = store.snapshot()
    state['conversations'][0]['label'] = 'Changed after migration'
    store.save(state, state['version'])
    saved = store.snapshot()
    (tmp_path / 'state/cache/butler_heartbeat.json').write_text('broken old source', encoding='utf-8')
    result = migrate_contacts(tmp_path, acknowledge_stopped=True)
    assert result['already_migrated']
    assert store.snapshot() == saved


def test_failed_activation_preserves_original_database_and_source_files(tmp_path, monkeypatch):
    from butler.contact_migration import migrate_contacts
    from butler.contact_store import ContactStore
    database = legacy(tmp_path)
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE original(value TEXT)')
        db.execute('INSERT INTO original VALUES("keep")')
    before = database.read_bytes()
    def fail(*args, **kwargs):
        raise RuntimeError('activation interrupted')
    monkeypatch.setattr(ContactStore, '_save', fail)
    with pytest.raises(RuntimeError, match='interrupted'):
        migrate_contacts(tmp_path, acknowledge_stopped=True)
    assert database.read_bytes() == before
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT * FROM original').fetchall() == [('keep',)]
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='directory_state'").fetchone()


def test_new_install_is_empty_active_canonical_without_legacy_json(tmp_path):
    from butler.install_wizard import install
    from butler.contact_store import ContactStore, is_unified
    assert install(tmp_path, nickname='Robot')['ok']
    database = tmp_path / 'data/business.sqlite3'
    assert is_unified(database)
    state = ContactStore(database).snapshot()
    assert not state['conversations']
    assert state['settings']['bot']['mention_names'] == ['Robot']
    assert not (tmp_path / 'data/cache/butler_heartbeat.json').exists()
    assert not (tmp_path / 'data/cache/butler_groups.json').exists()


def test_cli_preview_and_migrate_have_explicit_separate_cutover(tmp_path, capsys):
    from butler.__main__ import main
    from butler.contact_store import is_unified
    database = legacy(tmp_path)
    assert main(['contacts-preview', '--directory', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['ok']
    assert not is_unified(database)
    assert main(['contacts-migrate', '--directory', str(tmp_path)]) == 1
    assert 'acknowledge' in capsys.readouterr().out
    assert main(['contacts-migrate', '--directory', str(tmp_path), '--acknowledge-stopped']) == 0
    assert json.loads(capsys.readouterr().out)['ok']
    assert is_unified(database)


def test_preview_reports_same_name_memory_conflicts_and_migration_retains_variants(tmp_path):
    from butler.contact_migration import preview_contacts, migrate_contacts
    from butler.contact_identity import conflict_memories
    from butler.business import BusinessStore
    from butler.user_registry import UserRegistry
    database = legacy(tmp_path)
    registry = UserRegistry(BusinessStore(database))
    with registry.store.transaction() as db:
        first = registry._create(db, 'dm', 'Alice', 'Alice')
        second = registry._create(db, 'group', 'Team', 'Alice')
        for binding, value in [(first, 'coffee'), (second, 'tea')]:
            db.execute('INSERT INTO memory VALUES(?,?,?,1)', ('user:' + binding['user_id'], 'drink', value))
    report = preview_contacts(tmp_path)
    assert report['ok']
    assert report['same_name_merges'][0]['name'] == 'Alice'
    assert report['memory_conflicts'] == [dict(name='Alice', key='drink', variants=2,
                                             user_ids=sorted([first['user_id'], second['user_id']]))]
    migrate_contacts(tmp_path, acknowledge_stopped=True)
    with registry.store.transaction() as db:
        assert db.execute('SELECT DISTINCT user_id FROM user_bindings').fetchall()[0][0] == first['user_id']
        variants = conflict_memories(db, first['user_id'])
        assert {r['value'] for r in variants} == {'coffee', 'tea'}


def test_existing_directory_ledger_keeps_current_routes_and_historical_listen_names(tmp_path):
    from butler.contact_migration import preview_contacts
    from butler.migration import migrate_installation
    from butler.directory import DirectoryStore
    database = legacy(tmp_path)
    migrate_installation(tmp_path)
    directory = DirectoryStore(database)
    state = directory.snapshot()
    state['contacts'][0]['uid'] = 'changed-since-import'
    state['channel']['bot']['bound_users'].append('Historical listen only')
    directory.save(state, state['version'])
    report = preview_contacts(tmp_path)
    assert report['ok']
    routes = {c['name']: c for c in report['state']['conversations']}
    assert routes['Alice']['uid'] == 'changed-since-import'
    assert routes['Historical listen only']['listening']


def test_same_destination_private_group_conflict_is_not_guessed(tmp_path):
    from butler.contact_migration import preview_contacts
    legacy(tmp_path)
    config = tmp_path / 'config.wxbot.toml'
    config.write_text(config.read_text('utf-8').replace('bound_groups=["Team"]', 'bound_groups=["Team","Alice"]'), encoding='utf-8')
    assert not preview_contacts(tmp_path)['ok']


def test_preview_uses_committed_wal_and_never_imports_or_changes_database(tmp_path):
    from butler.contact_migration import preview_contacts
    from butler.business import BusinessStore
    from butler.directory import DirectoryStore
    database = legacy(tmp_path)
    BusinessStore(database)
    directory = DirectoryStore(database)
    with sqlite3.connect(database) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        state = {'contacts': [{'name': 'WAL contact', 'uid': 'wal-route'}], 'aliases': [], 'channel': {}}
        writer.execute('UPDATE directory_state SET payload=? WHERE id=1', (json.dumps(state),))
        writer.commit()
        before = _logical_database(database)
        assert preview_contacts(tmp_path)['ok']
        assert any(c['name'] == 'WAL contact' for c in preview_contacts(tmp_path)['state']['conversations'])
        assert _logical_database(database) == before


def _logical_database(database):
    with sqlite3.connect(database) as db:
        return list(db.iterdump())


def test_ordinary_upgrade_does_not_activate_legacy_contacts(tmp_path):
    from butler.upgrade import upgrade_installation
    from butler.contact_store import is_unified
    database = legacy(tmp_path)
    assert upgrade_installation(tmp_path)['ok']
    assert not is_unified(database)


def test_legacy_upgrade_is_safe_after_canonical_activation(tmp_path):
    from butler.contact_migration import migrate_contacts
    from butler.upgrade import upgrade_installation
    from butler.contact_store import ContactStore
    database = legacy(tmp_path)
    migrate_contacts(tmp_path, acknowledge_stopped=True)
    before = ContactStore(database).snapshot()
    assert upgrade_installation(tmp_path)['ok']
    assert ContactStore(database).snapshot() == before


def test_known_old_identity_route_and_memory_are_passive_but_preserved(tmp_path):
    from butler.contact_migration import preview_contacts, migrate_contacts
    from butler.business import BusinessStore
    from butler.contact_store import ContactStore
    database = legacy(tmp_path)
    business = BusinessStore(database)
    with business.transaction() as db:
        db.execute('INSERT INTO identities VALUES(?,?,?,?,?)', ('old-owner', 'Known old', 'old-profile', 'old-id', 'dm'))
        db.execute('INSERT INTO memory VALUES(?,?,?,1)', ('old-owner', 'preference', 'saved before bindings'))
    report = preview_contacts(tmp_path)
    old = next(c for c in report['state']['conversations'] if c['name'] == 'Known old')
    assert (old['uid'], old['profile'], old['listening']) == ('old-id', 'old-profile', False)
    migrate_contacts(tmp_path, acknowledge_stopped=True)
    old = next(c for c in ContactStore(database).snapshot()['conversations'] if c['name'] == 'Known old')
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT value FROM memory WHERE owner=? AND key="preference"', ('user:' + old['person_id'],)).fetchone() == ('saved before bindings',)
        assert db.execute('SELECT COUNT(*) FROM user_bindings WHERE contact="Known old"').fetchone() == (0,)


def test_scoped_aliases_become_observed_memberships_without_granting_identity(tmp_path):
    from butler.contact_migration import migrate_contacts
    from butler.directory import DirectoryStore
    from butler.user_registry import UserRegistry
    from butler.business import BusinessStore
    database = legacy(tmp_path)
    directory = DirectoryStore(database)
    state = directory.snapshot()
    state['aliases'] = [dict(group='Alias group', member_key=key, name='Real nickname', source='manual', pending=False)
                        for key in ['member-a', 'member-b']]
    directory.save(state, state['version'])
    migrate_contacts(tmp_path, acknowledge_stopped=True)
    registry = UserRegistry(BusinessStore(database))
    rows = registry.list_users(contact='Alias group')['rows']
    assert len(rows) == 2
    assert {row['nickname'] for row in rows} == {'Real nickname'}
    assert len({row['user_id'] for row in rows}) == 1
    assert all(not row['identity_confirmed'] for row in rows)
    assert {key for row in rows for key in row['observed_member_keys']} == {'member-a', 'member-b'}


def test_inferred_destinations_need_route_and_retired_people_are_not_reused(tmp_path):
    from butler.contact_migration import preview_contacts, migrate_contacts
    from butler.business import BusinessStore
    from butler.user_registry import UserRegistry
    from butler.contact_identity import ensure_schema
    from butler.contact_store import ContactStore
    database = legacy(tmp_path)
    registry = UserRegistry(BusinessStore(database))
    with registry.store.transaction() as db:
        ensure_schema(db)
        db.execute('INSERT INTO user_profiles VALUES("retired","Policy only",0,1)')
        db.execute('INSERT INTO user_profiles VALUES("current","New name",0,2)')
        db.execute('INSERT INTO user_redirects VALUES("retired","current")')
    report = preview_contacts(tmp_path)
    assert next(c for c in report['state']['conversations'] if c['name'] == 'Policy only')['needs_route']
    migrate_contacts(tmp_path, acknowledge_stopped=True)
    policy = next(c for c in ContactStore(database).snapshot()['conversations'] if c['name'] == 'Policy only')
    assert policy['person_id'] != 'retired'


def test_custom_directory_database_refuses_separate_existing_business_data(tmp_path):
    from butler.contact_migration import preview_contacts, migrate_contacts
    from butler.business import BusinessStore
    legacy(tmp_path)
    for name in ['config.butler.toml', 'config.wxbot.toml']:
        config = tmp_path / name
        config.write_text(config.read_text('utf-8').replace('state/business.sqlite3', 'custom/directory.sqlite3'), encoding='utf-8')
    business = BusinessStore(tmp_path / 'state/business.sqlite3')
    with business.transaction() as db:
        db.execute('INSERT INTO memory VALUES("old-owner","key","private",1)')
    before = files(tmp_path)
    report = preview_contacts(tmp_path)
    assert not report['ok']
    assert any('business database' in error for error in report['errors'])
    with pytest.raises(ValueError, match='business database'):
        migrate_contacts(tmp_path, acknowledge_stopped=True)
    # SQLite read-only WAL connections may create their own lock/index sidecars;
    # authoritative database bytes, configuration and data must remain unchanged.
    authoritative = lambda entries: {key: value for key, value in entries.items()
                                     if not key.endswith(('.sqlite3-wal', '.sqlite3-shm'))}
    assert authoritative(files(tmp_path)) == authoritative(before)


def test_custom_directory_database_is_supported_when_secondary_business_file_absent(tmp_path):
    from butler.contact_migration import preview_contacts, migrate_contacts
    from butler.contact_store import is_unified
    legacy(tmp_path)
    for name in ['config.butler.toml', 'config.wxbot.toml']:
        config = tmp_path / name
        config.write_text(config.read_text('utf-8').replace('state/business.sqlite3', 'custom/directory.sqlite3'), encoding='utf-8')
    assert preview_contacts(tmp_path)['ok']
    assert migrate_contacts(tmp_path, acknowledge_stopped=True)['ok']
    assert is_unified(tmp_path / 'custom/directory.sqlite3')
    assert not (tmp_path / 'state/business.sqlite3').exists()


@pytest.mark.parametrize('provider', ['deepseek', 'butler'])
def test_nonlocal_install_preserves_channel_management_and_rejects_cutover(tmp_path, provider):
    from butler.install_wizard import install, Connection
    from butler.contact_store import is_unified
    from butler.directory import DirectoryStore
    from butler.contact_migration import migrate_contacts
    install(tmp_path, Connection(provider=provider, model='test-model'), nickname='Robot')
    database = tmp_path / 'data/business.sqlite3'
    assert not is_unified(database)
    directory = DirectoryStore(database)
    assert directory.snapshot()['channel']['bot']['mention_names'] == ['Robot']
    assert not (tmp_path / 'data/cache/butler_heartbeat.json').exists()
    assert not (tmp_path / 'data/cache/butler_groups.json').exists()
    before = files(tmp_path)
    with pytest.raises(ValueError, match='local Butler'):
        migrate_contacts(tmp_path, acknowledge_stopped=True)
    assert files(tmp_path) == before
    from butler.upgrade import upgrade_installation
    upgrade_installation(tmp_path)
    assert directory.snapshot()['channel']['bot']['mention_names'] == ['Robot']
