import base64
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from butler.business import BusinessStore
from support.paths import REPO_ROOT


def avatar(seed=0):
    im = Image.new('RGB', (72, 72), (25, 30, 45))
    draw = ImageDraw.Draw(im)
    draw.rectangle((5 + seed, 8, 30 + seed, 54), fill=(190, 60, 90))
    draw.ellipse((26, 18 + seed, 65, 65), fill=(40, 180, 210))
    stream = BytesIO(); im.save(stream, format='PNG')
    return base64.b64encode(stream.getvalue()).decode()


def registry(tmp_path):
    from butler.identity.user_registry import UserRegistry
    return UserRegistry(BusinessStore(tmp_path / 'business.sqlite3'))


def test_create_persistent_identity_empty_memory_and_duplicate_rejection(tmp_path):
    r = registry(tmp_path)
    row = r.create('group', '群', '甲', avatar())
    assert len(row['user_id']) == 32 and row['memory_count'] == 0
    assert row['avatar'].startswith('data:image/png;base64,')
    assert registry(tmp_path).list_users()['rows'][0]['user_id'] == row['user_id']
    assert r.memories(row['binding_id'])['items'] == []
    with pytest.raises(ValueError): r.create('group', '群', '甲', avatar())


def test_avatar_normalization_and_strict_scoped_resolution(tmp_path):
    from common.avatar_identity import normalize_avatar
    r = registry(tmp_path)
    row = r.create('group', '群', '甲', avatar())
    feature = normalize_avatar(base64.b64decode(avatar()))
    actual = r.resolve('群', 'group', feature['hash'], avatar(), '甲')
    assert actual['user_id'] == row['user_id'] and actual['status'] == 'confirmed'
    assert r.resolve('其他群', 'group', feature['hash'], avatar(), '甲')['status'] == 'unknown'
    assert r.resolve('群', 'group', 'unknown-x', '', '甲')['status'] == 'unknown'
    r.create('group', '群', '乙', avatar())
    assert r.resolve('群', 'group', feature['hash'], avatar())['status'] == 'ambiguous'


def test_bad_upload_and_stale_edit_rejected(tmp_path):
    from butler.identity.user_registry import VersionConflict
    r = registry(tmp_path)
    with pytest.raises(ValueError): r.create('dm', 'alice', 'Alice', 'not-base64')
    with pytest.raises(ValueError): r.create('dm', 'alice', 'Alice', base64.b64encode(b'<svg/>').decode())
    row = r.create('dm', 'alice', 'Alice', avatar())
    changed = r.update_binding(row['binding_id'], row['version'], nickname='Alice2')
    assert changed['user_id'] == row['user_id']
    with pytest.raises(VersionConflict): r.update_binding(row['binding_id'], row['version'], nickname='stale')


def test_memory_revision_delete_and_identity_link_conflicts(tmp_path):
    r = registry(tmp_path)
    a = r.create('group', '群', '甲', avatar())
    b = r.create('dm', 'alice', 'Alice', avatar(8))
    for row, value in ((a, '群偏好'), (b, '私聊偏好')):
        m = r.memories(row['binding_id'])
        r.change_memory(row['binding_id'], 'preference', value, m['version'])
    assert r.memories(a['binding_id'])['items'][0]['value'] == '群偏好'
    result = r.link(a['binding_id'], b['binding_id'], a['version'])
    assert result['conflicts'][0]['key'] == 'preference'
    assert r.memories(a['binding_id'])['items'][0]['value'] == '群偏好'
    linked = r.link(a['binding_id'], b['binding_id'], a['version'], {'preference': 'target'})
    assert linked['user_id'] == b['user_id']
    m = r.memories(a['binding_id'])
    assert m['items'][0]['value'] == '私聊偏好'
    old_version = m['version']
    r.change_memory(a['binding_id'], 'preference', '', old_version, delete=True)
    assert r.memories(b['binding_id'])['items'] == []
    assert r.memories(b['binding_id'])['version'] > old_version
    assert r.audit(a['binding_id'])['rows']


def test_dm_resolution_stable_and_group_unknown_has_no_owner(tmp_path):
    r = registry(tmp_path)
    a = r.resolve('alice', 'dm')
    assert a['user_id'] == r.resolve('alice', 'dm')['user_id']
    assert a['memory_owner'] != r.resolve('群', 'group', 'abcd')['memory_owner']


def test_observed_group_identity_is_idempotent_scoped_and_honors_disable(tmp_path):
    r = registry(tmp_path)
    first = r.observe('群', 'group', 'observed-key', avatar(), '甲')
    assert r.observe('群', 'group', 'observed-key', avatar(), '甲')['user_id'] == first['user_id']
    assert r.observe('另群', 'group', 'observed-key', avatar(), '甲')['user_id'] != first['user_id']
    r.update_binding(first['binding_id'], first['version'], enabled=False)
    assert r.observe('群', 'group', 'observed-key', avatar(), '甲')['status'] == 'disabled'
    assert r.list_users()['total'] == 2


def test_pending_observation_cannot_grant_shared_memory_until_admin_confirms(tmp_path):
    r = registry(tmp_path)
    first = r.observe('群', 'group', 'stable-key', '', '甲')
    assert r.observe('群', 'group', 'stable-key', '', '甲')['user_id'] == first['user_id']
    assert r.list_users(status='observed')['total'] == 1
    changed = r.update_binding(first['binding_id'], first['version'], nickname='确认甲')
    assert changed['status'] == 'confirmed'
    assert r.resolve('群', 'group', 'stable-key')['user_id'] == first['user_id']


def test_missing_avatar_observation_does_not_shadow_existing_avatar_identity(tmp_path):
    r = registry(tmp_path)
    first = r.observe('群','group','key',avatar(),'甲')
    partial = r.observe('群','group','key','','甲')
    assert partial['user_id'] == first['user_id'] and partial['status'] == 'observed'
    assert r.observe('群','group','key',avatar(),'甲')['user_id'] == first['user_id']
    assert r.list_users()['total'] == 1


def test_disabled_identity_stays_disabled_after_minor_avatar_pixel_changes(tmp_path):
    r = registry(tmp_path)
    first = r.observe('群','group','key',avatar(),'甲')
    r.update_binding(first['binding_id'],first['version'],enabled=False)
    image = Image.open(BytesIO(base64.b64decode(avatar()))).convert('RGB')
    shifted = image.point(lambda channel:min(channel+2,255))
    stream = BytesIO(); shifted.save(stream,format='PNG')
    changed = base64.b64encode(stream.getvalue()).decode()
    assert r.observe('群','group','key',changed,'甲')['status'] == 'disabled'
    assert r.list_users()['total'] == 1


def test_conflicting_nickname_with_same_avatar_never_inherits_another_users_memory(tmp_path):
    r = registry(tmp_path)
    first = r.observe('群','group','key-a',avatar(),'Alice')
    r.change_memory(first['binding_id'],'private','alice-secret',0)
    second = r.observe('群','group','key-b',avatar(),'Bob')
    assert second['status'] == 'observed' and second['user_id'] != first['user_id']
    assert r.memories(second['binding_id'])['items'] == []
    assert r.observe('群','group','key-b',avatar(),'Bob')['user_id'] == second['user_id']
    assert r.observe('群','group','key-a',avatar(),'Alice')['user_id'] == first['user_id']


def test_admin_confirmation_does_not_promote_shared_automatic_key_to_authority(tmp_path):
    r = registry(tmp_path)
    alice = r.observe('群','group','same-hash',avatar(),'Alice')
    bob = r.observe('群','group','same-hash',avatar(),'Bob')
    r.update_binding(bob['binding_id'],bob['version'],nickname='Bob')
    assert r.observe('群','group','same-hash',avatar(),'Alice')['user_id'] == alice['user_id']
    assert r.observe('群','group','same-hash',avatar(),'Bob')['user_id'] == bob['user_id']


def test_missing_nickname_cannot_inherit_automatic_avatar_identity_memory(tmp_path):
    r = registry(tmp_path)
    alice = r.observe('群','group','key-a',avatar(),'Alice')
    r.change_memory(alice['binding_id'],'private','alice-secret',0)
    uncertain = r.observe('群','group','key-b',avatar(),'')
    assert uncertain['status'] == 'observed' and not uncertain['memory_owner']
    assert r.observe('群','group','key-a',avatar(),'Alice')['status'] == 'confirmed'
    assert r.resolve('群', 'group', 'abcd')['memory_owner'] == ''


def test_shared_memory_does_not_share_conversation_scope_and_revision_invalidates_thread(tmp_path):
    from dataclasses import replace
    from butler.identity.contacts import Contact
    from butler.backends.codex import owner_key, CodexBackend
    from types import SimpleNamespace
    r = registry(tmp_path)
    a = r.create('group', '群', '甲', avatar())
    b = r.create('dm', 'alice', 'Alice', avatar(8))
    linked = r.link(a['binding_id'], b['binding_id'], a['version'])
    ca = Contact('群', 'p', 'old-a', channel_type='group', binding_id=a['binding_id'], memory_owner=linked['memory_owner'])
    cb = Contact('alice', 'p', 'old-b', binding_id=b['binding_id'], memory_owner=linked['memory_owner'])
    assert owner_key(ca) == owner_key(cb)
    backend = CodexBackend.__new__(CodexBackend)
    backend.tools = SimpleNamespace(catalogue=SimpleNamespace(validate=lambda p: p))
    assert backend.scope(ca) != backend.scope(cb)
    assert backend.scope(ca) != backend.scope(replace(ca, memory_version=1))


def test_unknown_identity_cannot_call_memory_even_when_group_skill_enabled(tmp_path):
    from butler.agent.catalogue import SkillCatalogue
    from butler.agent.tools import ToolService
    from pathlib import Path
    service = ToolService(BusinessStore(tmp_path/'business.sqlite3'), SkillCatalogue(REPO_ROOT/'plugins'/'butler-wechat'/'skills'))
    policy = {'role_skill':'butler-companion','allowed_skills':['butler-memory']}
    token = service.issue(owner='unknown',contact='群',policy=policy,request_id='test',memory_allowed=False)
    assert not any(d['name'].startswith('memory_')for d in service.definitions(token))
    with pytest.raises(PermissionError): service.call('memory_set',{'key':'x','value':'y'},token,'test')


def test_admin_audit_is_not_mislabeled_as_model_and_link_copies_all_notes(tmp_path):
    r=registry(tmp_path)
    a=r.create('group','群','甲',avatar())
    b=r.create('dm','alice','Alice',avatar(8))
    r.change_memory(a['binding_id'],'note','first',0)
    actions=r.audit(a['binding_id'])['rows']
    assert not any(row['action']=='model_memory_set'for row in actions)
    with r.store.transaction()as db:
        for i in range(120):
            r.store.set_memory(a['memory_owner'],'key-'+str(i),'value',db=db)
    r.link(a['binding_id'],b['binding_id'],a['version'])
    assert r.memories(b['binding_id'])['binding']['memory_count']==121


def test_stale_link_preview_is_rejected_without_partial_merge(tmp_path):
    from butler.identity.user_registry import VersionConflict
    r=registry(tmp_path)
    a=r.create('group','群','甲',avatar());b=r.create('dm','alice','Alice',avatar(8))
    r.change_memory(a['binding_id'],'same','source',0)
    r.change_memory(b['binding_id'],'same','target',0)
    expected={'source_memory':1,'target_memory':1,'target_binding':b['version']}
    r.change_memory(b['binding_id'],'same','newer',1)
    with pytest.raises(VersionConflict):r.link(a['binding_id'],b['binding_id'],a['version'],{'same':'source'},expected_versions=expected)
    assert r.memories(b['binding_id'])['items'][0]['value']=='newer'


def test_manual_observed_alias_is_used_even_when_message_has_avatar(tmp_path):
    r=registry(tmp_path)
    a=r.create('group','群','甲',avatar())
    row=r.update_binding(a['binding_id'],a['version'],member_key='manually-checked')
    resolved=r.resolve('群','group','manually-checked',avatar(25))
    assert resolved['user_id']==a['user_id']
    b=r.create('group','群','乙',avatar(8))
    r.update_binding(b['binding_id'],b['version'],member_key='manually-checked')
    assert r.resolve('群','group','manually-checked',avatar())['status']=='ambiguous'


def test_recall_finds_relevant_notes_older_than_latest_hundred(tmp_path):
    r=registry(tmp_path)
    row=r.create('dm','alice','Alice',avatar())
    with r.store.transaction()as db:
        r.store.set_memory(row['memory_owner'],'favorite_fruit','mango',db=db)
        for i in range(101):r.store.set_memory(row['memory_owner'],'noise-'+str(i),'unrelated',db=db)
    result=r.recall(row['memory_owner'],'favorite_fruit mango')
    assert result[0]['key']=='favorite_fruit'
