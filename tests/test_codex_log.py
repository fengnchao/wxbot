import json
from pathlib import Path

from butler.setup import initialize
from log.config_view import ConfigView


def test_dashboard_uses_codex_business_paths_and_editable_config(tmp_path):
    initialize(tmp_path)
    view=ConfigView(tmp_path/'config.wxbot.toml',tmp_path/'config.butler.toml',tmp_path/'data',
                    repo_root=tmp_path,log_config_path=tmp_path/'config.log.toml')
    data=view.read()
    rows={r['key']:r for section in data['sections'] for r in section['rows']}
    assert rows['butler.agent.provider']['value']=='codex'
    assert rows['butler.codex.max_workers']['editable']
    assert rows['butler.codex.max_workers']['label']=='Codex 最大进程数'
    assert view.flow_options()['trace_paths'][1]==tmp_path/'data/cache/wxbot.log.events.jsonl'
    assert not data['warnings']


def test_codex_skills_are_loaded_from_butler_not_hermes(monkeypatch):
    import log.server as server
    seen=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self):return json.dumps({'data':[{'name':'paimon','tags':['butler-role']}]}).encode()
    def urlopen(req,**kw):
        seen.append(req);return Response()
    monkeypatch.setattr(server,'urlopen',urlopen)
    skills=server.fetch_hermes_skills({'name':'alice'},{'agent':{'provider':'codex'},'server':{'port':9876,'token':'local-only'}})
    assert seen[0].full_url=='http://127.0.0.1:9876/v1/skills'
    assert skills[0]['name']=='paimon'
