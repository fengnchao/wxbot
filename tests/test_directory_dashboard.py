import tomllib

import pytest


def view_for(root):
    from log.config_view import ConfigView
    return ConfigView(root/'config.wxbot.toml',root/'config.butler.toml',root/'data',
                      repo_root=root,log_config_path=root/'config.log.toml')


def test_migrated_directory_edit_uses_contacts_without_recreating_toml_bindings(tmp_path):
    from butler.install_wizard import install, Connection
    from log.config_editor import ConfigEditor
    from butler.contact_admin import ContactAdmin
    from butler.directory import DirectoryStore
    install(tmp_path,Connection(),nickname='Bot')
    view=view_for(tmp_path)
    info=view.read()
    source=next(s for s in info['sources'] if s['id']=='contacts')
    before=(tmp_path/'config.wxbot.toml').read_bytes()
    payload={'source':'directory','version':source['version'],'acknowledge':True,
             'changes':[{'path':['channel','bot','bound_users'],'op':'set','value':['Alice']}]}
    with pytest.raises(ValueError,match='联系人'):ConfigEditor(view).save(payload)
    service=ContactAdmin(tmp_path/'data/business.sqlite3')
    created=service.save({'action':'create','version':int(source['version']),'name':'Alice'})
    route=next(r for p in created['rows'] for r in p['conversations'] if r['name']=='Alice')
    request={'action':'conversation','version':created['version'],'id':route['id'],'listening':True}
    service.save(request)
    assert DirectoryStore(tmp_path/'data/business.sqlite3').channel_projection()['bot']['bound_users']==['Alice']
    assert (tmp_path/'config.wxbot.toml').read_bytes()==before
    with pytest.raises(ValueError,match='version'):service.save(request)
    assert not any(row.get('editable') for sec in info['sections'] if sec.get('source_id')=='wxbot'
                   for row in sec['rows'] if row.get('path')==['bot','bound_users'])


def test_new_install_nickname_is_in_database(tmp_path):
    from butler.install_wizard import install, Connection
    from wxbot.config import load_config
    install(tmp_path,Connection(),nickname='机器人')
    assert load_config(tmp_path/'config.wxbot.toml')['bot']['mention_names']==['机器人']


def test_dashboard_queue_path_follows_wxbot_config(tmp_path):
    from log.config_view import ConfigView
    root=tmp_path/'installation';root.mkdir()
    (root/'config.wxbot.toml').write_text('[queue]\ndatabase="cache/queue.sqlite3"\n',encoding='utf-8')
    view=ConfigView(root/'config.wxbot.toml',root/'config.butler.toml',root/'data',repo_root=tmp_path)
    view.read()
    assert view.queue_options()['path']==str(root/'cache/queue.sqlite3')


def test_direct_mode_does_not_offer_butler_business_controls(tmp_path):
    from butler.install_wizard import install, Connection
    install(tmp_path,Connection(provider='deepseek',model='test'))
    result=view_for(tmp_path).read()
    assert result['connection']['mode']=='direct'
    assert result['connection']['business_tools'] is False
    assert not any(s['id'] in {'policies','groups','log_policies','log_groups'} for s in result['sections'])
