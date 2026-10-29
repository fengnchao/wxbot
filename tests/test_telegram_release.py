import importlib.util
from pathlib import Path


def release_module():
    path = Path(__file__).resolve().parents[1] / 'tools/release.py'
    spec = importlib.util.spec_from_file_location('telegram_release_check', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_distribution_includes_telegram_defaults_and_instructions():
    module = release_module()
    paths = {p.relative_to(module.ROOT).as_posix() for p in module.source_files()}
    assert 'butler/defaults.py' in paths
    assert not any(p.endswith('.example.toml') for p in paths)
    assert 'docs/TELEGRAM_NEWS.md' in paths


def test_telegram_sessions_are_excluded_even_inside_source_folder(tmp_path, monkeypatch):
    module = release_module()
    (tmp_path/'butler').mkdir()
    for name in ('account.session', 'account.session-journal', 'account.session.relay.lock', 'good.py'):
        (tmp_path/'butler'/name).write_text('fixture', encoding='utf-8')
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    assert [p.name for p in module.source_files()] == ['good.py']
