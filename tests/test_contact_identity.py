"""Unified people keep their original membership evidence and conflicting notes."""
import pytest

from butler.business import BusinessStore
from butler.identity.user_registry import UserRegistry
from test_user_registry import avatar


def registry(tmp_path, active=True):
    result = UserRegistry(BusinessStore(tmp_path / 'business.sqlite3'))
    if active:
        with result.store.transaction() as db:
            db.execute('CREATE TABLE unified_contacts(id INTEGER PRIMARY KEY,version INTEGER,payload TEXT,active INTEGER)')
            db.execute("INSERT INTO unified_contacts VALUES(1,1,'{}',1)")
    return result


def test_active_cross_group_named_people_share_memory_and_keep_bindings(tmp_path):
    r = registry(tmp_path)
    first = r.observe('项目群', 'group', 'first-key', avatar(), ' 小王 ')
    r.change_memory(first['binding_id'], '饮料', '茶', 0)
    other = r.observe('同学群', 'group', 'other-key', avatar(8), '小王')
    assert other['user_id'] == first['user_id']
    assert other['binding_id'] != first['binding_id']
    assert r.memories(other['binding_id'])['items'][0]['value'] == '茶'
    assert r.resolve('项目群', 'group', 'first-key', avatar(), '小王')['binding_id'] == first['binding_id']


def test_name_normalization_excludes_placeholders_and_does_not_casefold():
    from butler.identity.contact_identity import normalize_name
    assert normalize_name('  e\u0301  ') == 'é'
    assert normalize_name('Alice') != normalize_name('alice')
    for name in ('', '  ', '成员-123', '待命名-abc', 'unknown-123'):
        assert normalize_name(name) == ''


def test_placeholder_people_stay_separate_and_disabled_binding_stays_disabled(tmp_path):
    r = registry(tmp_path)
    a = r.observe('甲群', 'group', 'first-key', '', '')
    b = r.observe('乙群', 'group', 'first-key', '', '')
    assert a['user_id'] != b['user_id']
    named = r.observe('项目群', 'group', 'known-key', avatar(), '小王')
    r.update_binding(named['binding_id'], named['version'], enabled=False)
    assert r.observe('项目群', 'group', 'fresh-key', '', '小王')['status'] == 'disabled'
    assert r.list_users(contact='项目群')['total'] == 1


def test_migration_merges_current_names_private_first_and_preserves_all_evidence(tmp_path):
    from butler.identity.contact_identity import ensure_schema, merge_same_named, reuse_person
    r = registry(tmp_path, active=False)
    a = r.create('group', '甲群', ' 小王 ', avatar())
    b = r.create('group', '乙群', '小王', avatar(8))
    private = r.create('dm', '王的窗口', '小王', avatar(16))
    with r.store.transaction() as db:
        db.execute('UPDATE user_bindings SET enabled=0 WHERE binding_id=?', (b['binding_id'],))
        db.execute('INSERT INTO user_member_aliases VALUES(?,?)', (a['binding_id'], 'alias'))
        db.execute('INSERT INTO user_observation_keys VALUES(?,?)', (b['binding_id'], 'observation'))
        ensure_schema(db)
        assert reuse_person(db, '小王') is None  # Schema creation alone is not activation.
        report = merge_same_named(db)
        assert len(report['merged']) == 2
        assert {row[0] for row in db.execute('SELECT user_id FROM user_bindings')} == {private['user_id']}
        assert db.execute('SELECT enabled FROM user_bindings WHERE binding_id=?', (b['binding_id'],)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM user_avatars').fetchone()[0] == 3
        assert db.execute('SELECT member_key FROM user_member_aliases').fetchone()[0] == 'alias'
        assert db.execute('SELECT member_key FROM user_observation_keys').fetchone()[0] == 'observation'
        assert merge_same_named(db)['merged'] == []


def test_same_key_conflicts_are_visible_with_sources_in_admin_and_recall(tmp_path):
    from butler.identity.contact_identity import merge_same_named, conflict_memories
    r = registry(tmp_path, active=False)
    a = r.create('group', '甲群', '小王', avatar())
    b = r.create('dm', '王的窗口', '小王', avatar(8))
    r.change_memory(a['binding_id'], '饮料', '茶', 0)
    r.change_memory(b['binding_id'], '饮料', '咖啡', 0)
    with r.store.transaction() as db:
        merge_same_named(db)
        variants = conflict_memories(db, b['user_id'])
        assert {row['value'] for row in variants} == {'茶', '咖啡'}
        assert all(row['source_label'] and row['source_user_id'] for row in variants)
        assert db.execute('SELECT value FROM memory WHERE owner=?', (a['memory_owner'],)).fetchone()[0] == '茶'
        db.execute('CREATE TABLE unified_contacts(id INTEGER PRIMARY KEY,version INTEGER,payload TEXT,active INTEGER)')
        db.execute("INSERT INTO unified_contacts VALUES(1,1,'{}',1)")
    items = r.memories(a['binding_id'])['items']
    assert {row['value'] for row in items} == {'茶', '咖啡'}
    assert all(row['source_label'] for row in items)
    recalled = r.recall('user:' + b['user_id'], '饮料')
    assert {row['value'] for row in recalled} == {'茶', '咖啡'}
    assert all(row['source_label'] for row in recalled)


def test_active_explicit_link_moves_all_person_bindings_and_retains_conflicts(tmp_path):
    r = registry(tmp_path)
    a = r.create('group', '项目群', '王工', avatar())
    sibling = r.create('group', '工作群', '王工', avatar(8))
    b = r.create('dm', '小王窗口', '小王', avatar(16))
    r.change_memory(a['binding_id'], '饮料', '茶', 0)
    r.change_memory(b['binding_id'], '饮料', '咖啡', 0)
    linked = r.link(a['binding_id'], b['binding_id'], a['version'])
    assert linked['user_id'] == b['user_id']
    assert not linked.get('requires_confirmation')
    assert r.memories(sibling['binding_id'])['binding']['user_id'] == b['user_id']
    assert {row['value'] for row in r.memories(sibling['binding_id'])['items']} == {'茶', '咖啡'}


def test_rename_collision_merges_but_old_names_only_participate_in_search(tmp_path):
    r = registry(tmp_path)
    a = r.create('group', '甲群', '老王', avatar())
    b = r.create('dm', '李的窗口', '小李', avatar(8))
    changed = r.update_binding(a['binding_id'], a['version'], nickname='小李')
    assert changed['user_id'] == b['user_id']
    assert r.list_users(query='老王')['total'] == 2
    newcomer = r.create('group', '乙群', '老王', avatar(16))
    assert newcomer['user_id'] != changed['user_id']


def test_old_user_id_redirects_to_shared_memory_and_transitive_merge_keeps_variants(tmp_path):
    from butler.identity.contact_identity import merge_users, conflict_memories
    r = registry(tmp_path, active=False)
    rows = [r.create('group', '群' + str(i), str(i), avatar(i * 8)) for i in range(3)]
    for row, value in zip(rows, ('茶', '咖啡', '水')):
        r.change_memory(row['binding_id'], '饮料', value, 0)
    with r.store.transaction() as db:
        merge_users(db, rows[0]['user_id'], rows[1]['user_id'])
        merge_users(db, rows[1]['user_id'], rows[2]['user_id'])
        assert {row['value'] for row in conflict_memories(db, rows[0]['user_id'])} == {'茶', '咖啡', '水'}
        db.execute('CREATE TABLE unified_contacts(id INTEGER PRIMARY KEY,version INTEGER,payload TEXT,active INTEGER)')
        db.execute("INSERT INTO unified_contacts VALUES(1,1,'{}',1)")
    assert {row['value'] for row in r.recall(rows[0]['memory_owner'], '饮料')} == {'茶', '咖啡', '水'}


def test_nonconflicting_memory_retains_original_source_for_a_later_conflict(tmp_path):
    from butler.identity.contact_identity import merge_users, conflict_memories
    r = registry(tmp_path, active=False)
    a = r.create('group', '甲群', '王工', avatar())
    b = r.create('dm', '小王窗口', '小王', avatar(8))
    c = r.create('group', '乙群', '阿王', avatar(16))
    r.change_memory(a['binding_id'], '饮料', '茶', 0)
    r.change_memory(c['binding_id'], '饮料', '咖啡', 0)
    with r.store.transaction() as db:
        merge_users(db, a['user_id'], b['user_id'])
        merge_users(db, c['user_id'], b['user_id'])
        variants = conflict_memories(db, b['user_id'])
        assert {row['source_user_id'] for row in variants} == {a['user_id'], c['user_id']}


def test_same_group_duplicate_name_retains_each_member_key_and_true_nickname(tmp_path):
    r = registry(tmp_path)
    a = r.observe('项目群', 'group', 'member-one', '', '小王')
    b = r.observe('项目群', 'group', 'member-two', '', '小王')
    assert a['binding_id'] != b['binding_id']
    assert a['user_id'] == b['user_id']
    assert b['nickname'] == '小王'
    assert r.observe('项目群', 'group', 'member-two', '', '小王')['binding_id'] == b['binding_id']
    for row, key in ((a, 'member-one'), (b, 'member-two')):
        changed = r.update_binding(row['binding_id'], row['version'], nickname='小王')
        assert changed['mention_name'] == '小王'
        assert r.resolve('项目群', 'group', key)['binding_id'] == row['binding_id']
    assert r.list_users(query='小王')['total'] == 2


def test_merge_redirects_canonical_routes_and_freezes_original_default_policies(tmp_path):
    from butler.identity.contact_identity import merge_users
    from butler.identity.contact_store import ContactStore
    r = registry(tmp_path, active=False)
    a = r.create('group', '项目群', '王工', avatar())
    b = r.create('dm', '小王窗口', '小王', avatar(8))
    contacts = ContactStore(r.store.path)
    source_policy = {'role_skill': 'butler-companion', 'allowed_skills': ['butler-memory'], 'heartbeat_enabled': False}
    target_policy = {'role_skill': 'paimon', 'allowed_skills': [], 'heartbeat_enabled': True}
    state = contacts.snapshot()
    state['person_policies'] = {a['user_id']: source_policy, b['user_id']: target_policy}
    state['conversations'] = [{'id': 'dm-one', 'name': '小王窗口', 'channel_type': 'dm', 'uid': 'route-a',
        'profile': 'p', 'label': '王工', 'session_key': 'original-session', 'listening': True, 'enabled': True,
        'person_id': a['user_id'], 'policy': None, 'subscriptions': [1]}]
    before = contacts.activate(state)
    with r.store.transaction() as db:
        merge_users(db, a['user_id'], b['user_id'])
    after = contacts.snapshot()
    route = after['conversations'][0]
    assert route['person_id'] == b['user_id']
    assert route['policy'] == source_policy
    assert route['uid'] == 'route-a' and route['session_key'] == 'original-session'
    assert route['subscriptions'] == [1] and route['listening'] is True
    assert after['person_policies'] == {b['user_id']: target_policy}
    assert after['version'] > before['version']


def test_merge_keeps_no_policy_route_from_inheriting_targets_policy(tmp_path):
    from butler.identity.contact_identity import merge_users
    from butler.identity.contact_store import ContactStore
    r = registry(tmp_path, active=False)
    a = r.create('group', '项目群', '王工', avatar())
    b = r.create('dm', '小王窗口', '小王', avatar(8))
    contacts = ContactStore(r.store.path)
    state = contacts.snapshot()
    state['person_policies'] = {b['user_id']: {'role_skill': 'paimon', 'allowed_skills': [], 'heartbeat_enabled': True}}
    state['conversations'] = [{'id': 'dm-one', 'name': '旧窗口', 'person_id': a['user_id']}]
    contacts.activate(state)
    with r.store.transaction() as db:
        merge_users(db, a['user_id'], b['user_id'])
    assert contacts.snapshot()['conversations'][0]['inherit_person_policy'] is False
    assert contacts.policies() == {}


def test_conflicting_values_deduplicate_sources_and_recall_includes_every_variant(tmp_path):
    from butler.identity.contact_identity import merge_users, conflict_memories
    r = registry(tmp_path, active=False)
    people = [r.create('group', '群' + str(i), str(i), avatar()) for i in range(12)]
    for i, row in enumerate(people):
        r.change_memory(row['binding_id'], '偏好', '值' + str(max(0, i - 1)), 0)
    with r.store.transaction() as db:
        for row in people[1:]:
            merge_users(db, row['user_id'], people[0]['user_id'])
        variants = conflict_memories(db, people[0]['user_id'])
        assert len(variants) == 11
        shared_value = next(row for row in variants if row['value'] == '值0')
        assert set(shared_value['source_user_ids']) == {people[0]['user_id'], people[1]['user_id']}
        db.execute('CREATE TABLE unified_contacts(id INTEGER PRIMARY KEY,version INTEGER,payload TEXT,active INTEGER)')
        db.execute("INSERT INTO unified_contacts VALUES(1,1,'{}',1)")
    recalled = r.recall(people[0]['memory_owner'], '偏好')
    assert len(recalled) == 11
    assert {row['value'] for row in recalled} == {'值' + str(i) for i in range(11)}


def test_active_legacy_import_exposes_both_values_and_preserves_reminder_destination(tmp_path):
    r = registry(tmp_path)
    row = r.create('group', '项目群', '王工', avatar())
    r.change_memory(row['binding_id'], '饮料', '咖啡', 0)
    r.store.set_memory('old-service-owner', '饮料', '茶')
    with r.store.transaction() as db:
        db.execute("INSERT INTO reminders(id,owner,contact,text,status) VALUES('reminder','old-service-owner','项目群','喝茶','scheduled')")
    r.adopt_legacy(row['binding_id'], 'old-service-owner')
    assert {note['value'] for note in r.memories(row['binding_id'])['items']} == {'茶', '咖啡'}
    assert any('old-service-owner' in note['source_label'] for note in r.recall(row['memory_owner'], '饮料'))
    assert r.store.reminders()[0]['contact'] == '项目群'
    assert r.store.reminders()[0]['owner'] == 'binding:' + row['binding_id']
    r.adopt_legacy(row['binding_id'], 'old-service-owner')
    assert len(r.memories(row['binding_id'])['items']) == 2


def test_migration_can_stage_duplicate_real_names_before_activation(tmp_path):
    from butler.identity.contact_identity import merge_same_named
    r = registry(tmp_path, active=False)
    a = r.create('group', '项目群', '小王', avatar())
    with r.store.transaction() as db:
        b = r._create(db, 'group', '项目群', '小王（internal-key）', actual_nickname='小王',
                      identity_confirmed=False, nickname_confirmed=True)
        merge_same_named(db)
        db.execute('CREATE TABLE unified_contacts(id INTEGER PRIMARY KEY,version INTEGER,payload TEXT,active INTEGER)')
        db.execute("INSERT INTO unified_contacts VALUES(1,1,'{}',1)")
    final = r.memories(b['binding_id'])['binding']
    assert final['user_id'] == a['user_id']
    assert final['nickname'] == '小王'
    assert final['status'] == 'observed'


@pytest.mark.parametrize('channel_type', ['dm', 'group'])
def test_runtime_name_match_cannot_reactivate_person_disabled_in_every_binding(tmp_path, channel_type):
    r = registry(tmp_path)
    old = r.create('group', '旧群', '小王', avatar())
    r.update_binding(old['binding_id'], old['version'], enabled=False)
    observed = r.observe('新窗口', channel_type, 'new-member', avatar(8), '小王')
    assert observed['status'] == 'disabled'
    assert r.list_users()['total'] == 1
