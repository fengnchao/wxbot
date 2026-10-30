"""Vue 版管理台只挂在 /app/；旧版首页、静态脚本和接口保持不变。"""
import importlib.util
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_server(tmp_path, monkeypatch):
    monkeypatch.setenv('LOG_CONFIG', str(tmp_path / 'log.toml'))
    monkeypatch.setenv('WXBOT_CONFIG', str(tmp_path / 'wxbot.toml'))
    monkeypatch.setenv('BUTLER_CONFIG', str(tmp_path / 'butler.toml'))
    spec = importlib.util.spec_from_file_location('_log_webapp_server', ROOT / 'log' / 'server.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_dist(tmp_path):
    """Rendering does not depend on a local npm build."""
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text(
        '<!doctype html><script type="module" src="/app/assets/app.js"></script>', encoding='utf-8')
    (dist / 'assets' / 'app.js').write_text('console.log("vue")', encoding='utf-8')
    return dist


def _serve(module, home, dist):
    handler = type('WebHandler', (module.Handler,), {'home': str(home), 'WEBAPP_DIR': str(dist)})
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.headers.get('Content-Type', ''), response.read().decode('utf-8')


def _redirect(url):
    """返回 (状态码, Location)；不跟随跳转，避免读到前端产物。"""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(url, timeout=5)
    except urllib.error.HTTPError as failure:
        return failure.code, failure.headers.get('Location', '')
    return 0, ''


def test_vue_entry_serves_its_own_assets_and_root_redirects(tmp_path, monkeypatch):
    module = _load_server(tmp_path, monkeypatch)
    server, thread = _serve(module, tmp_path / 'hermes', _fake_dist(tmp_path))
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        status, ctype, html = _get(base + '/app')
        assert status == 200 and 'text/html' in ctype and '/app/assets/app.js' in html
        status, ctype, script = _get(base + '/app/assets/app.js')
        assert status == 200 and 'javascript' in ctype and 'console.log' in script
        assert _redirect(base + '/') == (302, '/app/')
        assert _redirect(base + '/?tab=contacts') == (302, '/app/?tab=contacts')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_webapp_rejects_unknown_and_traversing_assets(tmp_path, monkeypatch):
    module = _load_server(tmp_path, monkeypatch)
    server, thread = _serve(module, tmp_path / 'hermes', _fake_dist(tmp_path))
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        for path in ('/app/assets/missing.js', '/app/assets/../server.py', '/assets/app.js'):
            with pytest.raises(urllib.error.HTTPError) as failure:
                urllib.request.urlopen(base + path, timeout=5)
            assert failure.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_unbuilt_webapp_explains_how_to_build(tmp_path, monkeypatch):
    module = _load_server(tmp_path, monkeypatch)
    server, thread = _serve(module, tmp_path / 'hermes', tmp_path / 'missing-dist')
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        status, _, html = _get(base + '/app')
        assert status == 200 and 'npm run build' in html
        assert _redirect(base + '/') == (302, '/app/')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_vue_shell_renders_without_a_browser():
    """jsdom 回归；未安装前端依赖时跳过，不阻塞纯后端环境。"""
    node = shutil.which('node')
    web = Path(__file__).resolve().parents[1] / 'log' / 'web'
    if not node or not (web / 'node_modules').is_dir():
        pytest.skip('需要先在 log/web 执行 npm install 与 npm run build')
    result = subprocess.run([node, str(web / 'scripts' / 'smoke.mjs')], cwd=web,
                            capture_output=True, text=True, encoding='utf-8', timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'smoke passed' in result.stdout
