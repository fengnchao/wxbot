import importlib.util
from pathlib import Path
import zipfile
from support.paths import REPO_ROOT


def test_release_excludes_runtime_and_contains_plugin(tmp_path):
    path=REPO_ROOT/'tools/release.py'
    spec=importlib.util.spec_from_file_location('release_tools',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.build_release(tmp_path)
    for name in ('application','plugin'):
        with zipfile.ZipFile(result[name]) as archive:
            names=archive.namelist()
            assert names
            assert not any('/.venv/' in p or p.endswith('.pyc') or 'auth.json' in p or p.endswith('.sqlite3') for p in names)
            assert not any(p.endswith('config.butler.toml') or p.endswith('config.wxbot.toml') for p in names)
    with zipfile.ZipFile(result['application']) as archive:
        assert 'plugins/butler-wechat/.codex-plugin/plugin.json' in archive.namelist()
        assert '.agents/plugins/marketplace.json' in archive.namelist()
        assert 'scripts/wechat_stack_ctl.py' not in archive.namelist()
        for required in ('src/butler/defaults.py', 'src/butler/runtime/install_wizard.py', 'docs/MESSAGE_API.md'):
            assert required in archive.namelist()
        assert not any(Path(name).name.startswith('config.') and name.endswith('.toml') for name in archive.namelist())


def test_invalid_plugin_names_cannot_escape_workspace(tmp_path):
    import pytest
    from butler.agent.catalogue import SkillCatalogue
    p=tmp_path/'evil/SKILL.md';p.parent.mkdir()
    p.write_text('---\nname: ../../escape\ndescription: bad\nmetadata:\n  butler:\n    tags: [butler-role]\n---\ntext',encoding='utf-8')
    with pytest.raises(ValueError):SkillCatalogue(tmp_path).list()


def test_release_excludes_config_templates_at_any_depth(tmp_path, monkeypatch):
    path = REPO_ROOT / 'tools/release.py'
    spec = importlib.util.spec_from_file_location('release_no_templates', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    (tmp_path / 'butler').mkdir()
    for name in ('config.telegram.example.toml', 'butler/config.hidden.example.toml', 'butler/config.actual.toml'):
        (tmp_path / name).write_text('fixture', encoding='utf-8')
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    assert module.source_files() == []
