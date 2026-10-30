import copy
import json

import pytest

from butler.identity.directory import DirectoryStore
from dashboard.config_view import ConfigView
from dashboard.config_editor import ConfigEditor


def legacy_directory(tmp_path):
    bt=tmp_path/'config.butler.toml';wx=tmp_path/'config.wxbot.toml'
    for path in (bt,wx):path.write_text('[directory]\ndatabase="data/business.sqlite3"\n',encoding='utf-8')
    directory=DirectoryStore(tmp_path/'data/business.sqlite3')
    state=directory.snapshot()
    state['contacts']=[{'name':'A','uid':'a','profile':'p','session_key':'agent:{uid}','note':'keep'}]
    state['channel']={'bot':{'bound_users':['A','B'],'bound_groups':['G'],'mention_names':['Bot']},'wechat':{'main_window':{'listen_all':True}}}
    state['aliases']=[{'group':'','member_key':'member-1','name':'Alice','source':'legacy','pending':True}]
    directory.save(state,state['version'])
    view=ConfigView(wx,bt,tmp_path/'data',log_config_path=tmp_path/'log.toml')
    return directory,view


def test_legacy_directory_exposes_one_contact_list_and_alias_table(tmp_path):
    directory,view=legacy_directory(tmp_path)
    data=view.read();section=next(s for s in data['sections'] if s['id']=='directory')
    rows={tuple(r['path']):r for r in section['rows']}
    assert ('contacts',) not in rows
    assert ('channel','bot','bound_users') not in rows
    assert ('channel','bot','bound_groups') not in rows
    entries=rows[('entries',)]
    assert entries['widget']=='directory-contacts'
    assert {c['name'] for c in entries['value']}=={'A','B','G'}
    assert all(c['listening'] is True for c in entries['value'])
    assert next(c for c in entries['value'] if c['name']=='G')['channel_type']=='group'
    assert rows[('aliases',)]['widget']=='alias-list'
    assert 'group / member_key' not in rows[('aliases',)]['description']


def test_combined_contact_edit_saves_routes_and_listening_atomically(tmp_path):
    directory,view=legacy_directory(tmp_path)
    data=view.read();source=next(s for s in data['sources'] if s['id']=='directory')
    row=next(r for s in data['sections'] if s['id']=='directory' for r in s['rows'] if r['path']==['entries'])
    entries=copy.deepcopy(row['value']);a=next(c for c in entries if c['name']=='A')
    a.update(name='Renamed',listening=False)
    request={'source':'directory','version':source['version'],'acknowledge':True,
             'changes':[{'path':['entries'],'op':'set','value':entries}]}
    ConfigEditor(view).save(request)
    state=directory.snapshot()
    assert state['channel']['bot']['bound_users']==['B']
    assert state['channel']['bot']['bound_groups']==['G']
    saved=next(c for c in state['contacts'] if c['name']=='Renamed')
    assert saved['session_key']=='agent:{uid}' and saved['note']=='keep'
    assert 'listening' not in saved
    assert state['aliases'][0]['pending'] is True
    with pytest.raises(ValueError):ConfigEditor(view).save(request)


def test_combined_editor_rejects_invalid_listening_without_partial_save(tmp_path):
    directory,view=legacy_directory(tmp_path);data=view.read()
    source=next(s for s in data['sources'] if s['id']=='directory');before=directory.snapshot()
    with pytest.raises(ValueError):
        ConfigEditor(view).save({'source':'directory','version':source['version'],'acknowledge':True,
            'changes':[{'path':['entries'],'op':'set','value':[{'name':'A','listening':'true'}]}]})
    assert directory.snapshot()==before


def test_active_alias_list_edit_keeps_observation_permissions_and_versions(tmp_path):
    from butler.identity.contact_store import ContactStore
    from butler.identity.contact_admin import ContactAdmin
    store=ContactStore(tmp_path/'contacts.db');store.activate(store.snapshot(),0)
    admin=ContactAdmin(store.path);data=admin.read()
    assert data['aliases']==[]
    aliases=[{'group':'G','member_key':'member-1','name':'Alice','source':'manual','pending':False}]
    changed=admin.save({'action':'aliases','version':data['version'],'aliases':aliases})
    assert changed['aliases']==aliases
    assert DirectoryStore(store.path).member_name('G','member-1')=='Alice'
    with store.transaction() as db:assert db.execute('SELECT COUNT(*) FROM user_bindings').fetchone()[0]==0
    with pytest.raises(ValueError,match='version'):admin.save({'action':'aliases','version':data['version'],'aliases':[]})
    with pytest.raises(ValueError):admin.save({'action':'aliases','version':changed['version'],'aliases':[dict(aliases[0],name='')]})
