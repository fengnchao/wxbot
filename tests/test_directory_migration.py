import sqlite3
from pathlib import Path
import tomllib
import pytest


def legacy(root):
    (root / 'config.butler.toml').write_text('''# keep comment
[agent]
data_dir="state"
[server]
token="secret"
[[contacts]]
name="Alice"
uid="old-uid"
profile="p"
session_key="old:{uid}"
''', encoding='utf-8')
    (root / 'config.wxbot.toml').write_text('''[bot]
bound_users=["Alice"]
bound_groups=["Team"]
mention_names=["Robot"]
[wechat.main_window]
listen_all=false
[wechat.group_sender.member_names]
hash="Manual"
''', encoding='utf-8')
    db = root / 'state' / 'business.sqlite3'
    db.parent.mkdir()
    with sqlite3.connect(db) as con:
        con.execute('create table stable(id text, permissions text)')
        con.execute('insert into stable values("binding-1","unchanged")')
    return db


def test_migrate_preserves_scope_routes_identity_and_comments(tmp_path):
    from butler.identity.directory import DirectoryStore, directory_path
    from butler.runtime.migration import migrate_installation
    db = legacy(tmp_path)
    result = migrate_installation(tmp_path)
    assert result['database'] == str(db.resolve())
    store = DirectoryStore(db)
    snap = store.snapshot()
    assert snap['channel']['bot']['bound_users'] == ['Alice']
    assert snap['channel']['wechat']['main_window']['listen_all'] is False
    assert snap['contacts'][0]['uid'] == 'old-uid'
    assert snap['contacts'][0]['session_key'] == 'old:{uid}'
    assert snap['aliases'][0]['pending'] is True
    assert store.member_name('Team', 'hash') == ''
    assert directory_path(tmp_path / 'config.wxbot.toml') == db.resolve()
    text = (tmp_path / 'config.butler.toml').read_text('utf-8')
    assert '# keep comment' in text and 'secret' in text and '[[contacts]]' not in text
    assert 'bound_users' not in (tmp_path / 'config.wxbot.toml').read_text('utf-8')
    with sqlite3.connect(db) as con:
        assert con.execute('select * from stable').fetchall() == [('binding-1','unchanged')]
    snap['channel']['bot']['mention_names'] = ['New']
    store.save(snap, expected_version=snap['version'])
    migrate_installation(tmp_path)
    assert store.snapshot()['channel']['bot']['mention_names'] == ['New']
    with pytest.raises(ValueError, match='version'):
        store.save(snap, expected_version=snap['version'])


def test_scoped_learning_manual_precedence_and_runtime(tmp_path):
    from butler.identity.directory import DirectoryStore
    from butler.runtime.migration import migrate_installation
    from wxbot.config import load_config
    from butler.config import load
    db = legacy(tmp_path)
    cache = tmp_path / 'cache'
    cache.mkdir()
    with sqlite3.connect(cache / 'wxbot_queue.sqlite3') as con:
        con.execute('create table group_member_names(contact text,member_key text,name text,updated_at real)')
        con.execute('insert into group_member_names values("Team","k","Learned",1)')
    migrate_installation(tmp_path)
    store = DirectoryStore(db)
    assert store.member_name('Team','k') == 'Learned'
    assert store.member_name('Other','k') == ''
    snap = store.snapshot()
    snap['aliases'].append(dict(group='Team',member_key='k',name='Manual',source='manual',pending=False))
    store.save(snap, expected_version=snap['version'])
    store.observe_member('Team','k','Changed')
    assert store.member_name('Team','k') == 'Manual'
    cfg = load_config(tmp_path/'config.wxbot.toml')
    assert cfg['bot']['bound_groups'] == ['Team']
    assert cfg['wechat']['main_window']['listen_all'] is False
    assert load(tmp_path/'config.butler.toml').contacts.get('Alice').uid == 'old-uid'

def test_import_rollback_and_retry_after_file_replace_interruption(tmp_path, monkeypatch):
    from butler.identity.directory import DirectoryStore
    import butler.runtime.migration as migration
    db = legacy(tmp_path)
    original = (tmp_path/'config.wxbot.toml').read_text('utf-8')
    real_replace = migration._replace
    monkeypatch.setattr(migration, '_replace', lambda *args: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        migration.migrate_installation(tmp_path)
    store = DirectoryStore(db)
    state = store.snapshot()
    state['channel']['bot']['mention_names'] = ['After interruption']
    store.save(state, expected_version=state['version'])
    monkeypatch.setattr(migration, '_replace', real_replace)
    migration.migrate_installation(tmp_path)
    assert store.channel_projection()['bot']['mention_names'] == ['After interruption']
    assert 'bound_users' not in (tmp_path/'config.wxbot.toml').read_text('utf-8')


def test_shared_queue_and_dynamic_names_and_relative_paths(tmp_path, monkeypatch):
    from butler.identity.directory import DirectoryStore, directory_path
    from wxbot.queue_store import QueueStore, queue_database
    from wxbot.config import load_config
    path = tmp_path/'config.wxbot.toml'
    path.write_text('[directory]\ndatabase="state/shared.db"\n[bot]\n[wechat]\n', encoding='utf-8')
    shared = DirectoryStore(directory_path(path))
    shared.initialize_channel('Robot')
    monkeypatch.chdir(tmp_path.parent)
    cfg = load_config(path)
    assert queue_database(cfg) == tmp_path/'cache/wxbot_queue.sqlite3'
    queue = QueueStore(':memory:', directory_path=cfg['_directory_path'])
    try:
        queue.remember_group_member('Team','k','Learned',now=1)
        assert shared.member_name('Team','k') == 'Learned'
        snap = shared.snapshot()
        snap['aliases'].append(dict(group='Team', member_key='k', name='Manual', source='manual', pending=False))
        shared.save(snap, expected_version=snap['version'])
        assert queue.group_member_name('Team','k') == 'Manual'
    finally:
        queue.close()


def test_bad_source_does_not_remove_legacy_fields(tmp_path):
    from butler.runtime.migration import migrate_installation
    legacy(tmp_path)
    path = tmp_path/'config.wxbot.toml'
    path.write_text('[bot]\nbound_users="wrong"\n',encoding='utf-8')
    with pytest.raises(ValueError):
        migrate_installation(tmp_path)
    assert '[[contacts]]' in (tmp_path/'config.butler.toml').read_text('utf-8')

def test_loaded_butler_routes_refresh_without_rebuilding_identity(tmp_path):
    from butler.config import load
    from butler.identity.directory import DirectoryStore
    from butler.runtime.migration import migrate_installation
    db = legacy(tmp_path)
    migrate_installation(tmp_path)
    cfg = load(tmp_path/'config.butler.toml')
    state = DirectoryStore(db).snapshot()
    state['contacts'][0]['label'] = 'Updated display'
    DirectoryStore(db).save(state, expected_version=state['version'])
    assert cfg.contacts.get('Alice').label == 'Updated display'
    assert cfg.contacts.get('Alice').uid == 'old-uid'

def test_conflicting_explicit_database_is_rejected_before_removing_fields(tmp_path):
    from butler.runtime.migration import migrate_installation
    legacy(tmp_path)
    path = tmp_path/'config.wxbot.toml'
    path.write_text(path.read_text('utf-8')+'\n[directory]\ndatabase="other/business.sqlite3"\n',encoding='utf-8')
    with pytest.raises(ValueError,match='database'):
        migrate_installation(tmp_path)
    assert '[[contacts]]' in (tmp_path/'config.butler.toml').read_text('utf-8')

def test_ledger_does_not_copy_secrets_and_preserves_utf8_bom(tmp_path):
    from butler.runtime.migration import migrate_installation
    db = legacy(tmp_path)
    path = tmp_path/'config.butler.toml'
    path.write_bytes(b'\xef\xbb\xbf'+path.read_bytes())
    migrate_installation(tmp_path)
    assert path.read_bytes().startswith(b'\xef\xbb\xbf')
    with sqlite3.connect(db) as con:
        rows = con.execute('select * from directory_migrations').fetchall()
    assert 'secret' not in repr(rows)


@pytest.mark.parametrize('field,value', [('uid',[]),('profile',123),('session_key',{}),('name',False)])
def test_directory_rejects_malformed_contact_routes(tmp_path, field, value):
    from butler.identity.directory import DirectoryStore
    store = DirectoryStore(tmp_path/'business.db')
    snap = store.snapshot()
    row = dict(name='Alice',uid='stable',profile='default',session_key='route')
    row[field] = value
    snap['contacts'] = [row]
    with pytest.raises(ValueError):
        store.save(snap,expected_version=snap['version'])


def test_directory_rejects_duplicate_contacts_and_malformed_aliases(tmp_path):
    from butler.identity.directory import DirectoryStore
    store = DirectoryStore(tmp_path/'business.db')
    snap = store.snapshot()
    snap['contacts'] = [dict(name='Alice'),dict(name='Alice')]
    with pytest.raises(ValueError):
        store.save(snap,expected_version=snap['version'])
    snap['contacts'] = []
    snap['aliases'] = [dict(group=23, member_key='k',name='n',source='manual',pending=False)]
    with pytest.raises(ValueError):
        store.save(snap,expected_version=snap['version'])

def test_failed_migration_keeps_legacy_loaders_active(tmp_path):
    from butler.runtime.migration import migrate_installation
    from butler.config import load
    from wxbot.config import load_config
    legacy(tmp_path)
    path = tmp_path/'config.butler.toml'
    path.write_text(path.read_text('utf-8').replace('profile="p"','profile=12'),encoding='utf-8')
    with pytest.raises(ValueError):
        migrate_installation(tmp_path)
    assert load(path).contacts.get('Alice').uid == 'old-uid'
    cfg = load_config(tmp_path/'config.wxbot.toml')
    assert cfg['bot']['bound_users'] == ['Alice']
    assert cfg['wechat']['main_window']['listen_all'] is False
    assert '_directory_path' not in cfg


@pytest.mark.parametrize('absolute_legacy_key', [False,True])
def test_moved_install_does_not_reimport_or_clean_old_root(tmp_path,monkeypatch,absolute_legacy_key):
    import shutil
    import butler.runtime.migration as migration
    from butler.identity.directory import DirectoryStore
    original = tmp_path/'old'
    original.mkdir()
    db = legacy(original)
    real_replace = migration._replace
    monkeypatch.setattr(migration, '_replace', lambda *args: (_ for _ in ()).throw(OSError('interrupted')))
    with pytest.raises(OSError):
        migration.migrate_installation(original)
    state = DirectoryStore(db).snapshot()
    state['channel']['bot']['mention_names'] = ['New nickname']
    DirectoryStore(db).save(state,expected_version=state['version'])
    if absolute_legacy_key:
        with sqlite3.connect(db) as con:
            entries = con.execute('select source from directory_migrations').fetchall()
            for (key,) in entries:
                con.execute('update directory_migrations set source=? where source=?',(str(original/Path(key).name),key))
    moved = tmp_path/'new'
    shutil.copytree(original,moved)
    monkeypatch.setattr(migration, '_replace', real_replace)
    migration.migrate_installation(moved)
    assert DirectoryStore(moved/'state/business.sqlite3').channel_projection()['bot']['mention_names'] == ['New nickname']
    assert 'bound_users' not in (moved/'config.wxbot.toml').read_text('utf-8')
    assert 'bound_users' in (original/'config.wxbot.toml').read_text('utf-8')
    with sqlite3.connect(moved/'state/business.sqlite3') as con:
        assert set(row[0] for row in con.execute('select source from directory_migrations')) == {'config.butler.toml','config.wxbot.toml'}

def test_route_private_compatibility_and_template_validation(tmp_path):
    from butler.identity.directory import DirectoryStore
    store = DirectoryStore(tmp_path/'directory.db')
    state = store.snapshot()
    state['contacts'] = [dict(name='Alice',uid='old',channel_type='private',session_key='{profile}:{uid}')]
    saved = store.save(state,expected_version=state['version'])
    assert saved['contacts'][0]['channel_type'] == 'dm'
    for invalid in ('{unknown}', '{uid.bad}', '{uid'):
        state = store.snapshot()
        state['contacts'][0]['session_key'] = invalid
        with pytest.raises(ValueError,match='session_key'):
            store.save(state,expected_version=state['version'])
