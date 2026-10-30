import json
import time

import pytest

from butler.agent.catalogue import SkillCatalogue
from butler.business import BusinessStore
from butler.agent.tools import ToolService


def catalogue(tmp_path):
    for name, tags, tools in [('role', ['butler-role'], []), ('reminders', ['butler-tool'], ['reminder_create','reminder_list','reminder_cancel']), ('notes', ['butler-tool'], ['memory_get','memory_set','memory_search'])]:
        p = tmp_path / name / 'SKILL.md'
        p.parent.mkdir(parents=True)
        p.write_text('---\nname: '+name+'\ndescription: sample\nmetadata:\n  butler:\n    tags: '+json.dumps(tags)+'\n    tools: '+json.dumps(tools)+'\n---\nHello\n', encoding='utf-8')
    return SkillCatalogue(tmp_path)


def test_catalogue_tags_and_safe_references(tmp_path):
    cat = catalogue(tmp_path)
    assert len(cat.list()) == 3
    assert cat.validate({'role_skill':'role','allowed_skills':['notes']})['allowed_skills'] == ['notes']
    with pytest.raises(ValueError): cat.validate({'role_skill':'notes','allowed_skills':[]})
    with pytest.raises(ValueError): cat.read('role','../notes/SKILL.md')
    with pytest.raises(ValueError): cat.validate({'role_skill':'role','allowed_skills':['role']})


def test_store_fresh_and_persistent(tmp_path):
    path = tmp_path / '中文 空间' / 'business.sqlite3'
    store = BusinessStore(path)
    assert store.memories('alice') == []
    store.set_memory('alice','name','Alice')
    assert BusinessStore(path).memories('alice')[0]['value'] == 'Alice'
    assert store.memories('bob') == []
    store.set_session('scope','thread-123')
    assert BusinessStore(path).get_session('scope') == 'thread-123'


def service(tmp_path):
    cat = catalogue(tmp_path / 'skills')
    return ToolService(BusinessStore(tmp_path/'data.sqlite3'),cat,secret=b'x'*32)


def token(s, *, owner='alice', allowed=('notes','reminders'), read_only=False, ttl=60):
    return s.issue(owner=owner, contact=owner, policy={'role_skill':'role','allowed_skills':list(allowed)}, read_only=read_only, request_id='req-1', ttl=ttl)


def test_tools_enforce_owner_allowlist_and_readonly(tmp_path):
    s = service(tmp_path)
    a = token(s)
    s.call('memory_set',{'key':'name','value':'Alice'},a,'c1')
    assert s.call('memory_get',{},token(s,owner='bob'),'c2')['items'] == []
    for args in [{'owner':'bob'}, {'contact':'bob'}, {'uid':'bob'}]:
        with pytest.raises(PermissionError): s.call('memory_get',args,a,'c3')
    with pytest.raises(PermissionError): s.call('memory_set',{'key':'x','value':'y'},token(s,read_only=True),'c4')
    with pytest.raises(PermissionError): s.call('memory_get',{},token(s,allowed=()),'c5')
    with pytest.raises(PermissionError): s.call('skill_read',{'name':'notes'},token(s,allowed=()),'c6')
    with pytest.raises(PermissionError): s.call('memory_get',{},a+'bad','c7')
    with pytest.raises(PermissionError): s.call('memory_get',{},token(s,ttl=-1),'c8')


def test_changed_permissions_revoke_existing_capability(tmp_path):
    s=service(tmp_path)
    current={'role_skill':'role','allowed_skills':['notes','reminders']}
    s.policy_loader=lambda contact:current
    a=token(s)
    assert s.call('memory_get',{},a,'before')['items']==[]
    current={'role_skill':'role','allowed_skills':[]}
    with pytest.raises(PermissionError):s.call('memory_set',{'key':'x','value':'y'},a,'after')
    assert s.store.memories('alice')==[]


def test_reminder_idempotency_cancel_and_restart(tmp_path):
    s = service(tmp_path)
    a = token(s)
    args = {'text':'喝水','schedule':'in 2m'}
    first = s.call('reminder_create',args,a,'same')
    assert s.call('reminder_create',args,a,'same') == first
    assert s.call('reminder_create',args,a,'model-retry-with-new-rpc-id') == first
    assert len(s.store.reminders('alice')) == 1
    assert BusinessStore(s.store.path).reminders('alice')[0]['id'] == first['id']
    with pytest.raises(PermissionError):
        s.call('reminder_cancel',{'id':first['id']},token(s,owner='bob'),'cancel')
    s.call('reminder_cancel',{'id':first['id']},a,'cancel')
    assert s.store.reminders('alice')[0]['status'] == 'cancelled'


def test_recurring_reminder_and_failed_delivery_not_replayed(tmp_path):
    s = service(tmp_path)
    result = s.call('reminder_create',{'text':'喝水','schedule':'*/5 * * * *'},token(s),'r')
    jobs = s.store.claim_due(now=time.time()+301)
    assert jobs[0]['id'] == result['id']
    assert s.store.claim_due(now=time.time()+301) == []
    s.store.finish_reminder(jobs[0]['id'],False,'uncertain',now=time.time()+301)
    assert s.store.reminders('alice')[0]['status'] == 'failed'


def test_tool_schema_validation_and_mutation_id_collision(tmp_path):
    s=service(tmp_path);a=token(s)
    schemas={tool['name']:tool['inputSchema'] for tool in s.definitions(a)}
    assert schemas['memory_set']['required']==['key','value']
    assert schemas['reminder_create']['required']==['text','schedule']
    with pytest.raises(ValueError):s.call('memory_search',{'query':[]},a,'bad')
    with pytest.raises(ValueError):s.call('reminder_cancel',{'id':['bad']},a,'bad')
    s.call('memory_set',{'key':'a','value':'first'},a,'once')
    with pytest.raises(ValueError):s.call('memory_set',{'key':'a','value':'changed'},a,'once')
    assert s.store.memories('alice')[0]['value']=='first'
