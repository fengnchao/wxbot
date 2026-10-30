"""用户分组：字典读写（butler/identity/groups.py）+ /v1/push 的 type/messageType 路由 + 看板 /api/groups。

对齐 Hermes 侧约定：
  type: 1=指定用户发送（contact）/ 2=群发（按 messageType 查字典）
  messageType: 1=新闻消息 2=问候消息 3=其他
"""
from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from butler.identity.groups import GroupStore, parse_int
from support.paths import REPO_ROOT

ROOT = REPO_ROOT


def _load_dashboard():
    """看板已是常规包，按文件路径加载以便隔离配置。"""
    spec = importlib.util.spec_from_file_location("_dash_server_groups", ROOT / "src" / "dashboard" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _req(url, body=None, headers=None, method=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"))
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def _call_push(base, payload, token="t0ken"):
    headers = {"Authorization": "Bearer " + token} if token else {}
    return _req(base + "/v1/push", payload, headers=headers)


# ---------------------------------------------------------------- 字典（butler/identity/groups.py）

def test_parse_int():
    assert parse_int(1) == 1 and parse_int(" 2 ") == 2 and parse_int(3.0) == 3
    assert parse_int("abc") is None and parse_int(None) is None and parse_int(True) is None


def test_group_store_roundtrip(tmp_path):
    path = tmp_path / "cache" / "butler_groups.json"
    st = GroupStore(str(path))
    assert st.users_of(1) == []
    assert st.bind(1, "101") == ["101"]
    assert st.bind(1, "z") == ["101", "z"]
    assert st.bind(1, "z") == ["101", "z"]            # 幂等
    assert st.bind(2, "101") == ["101"]
    assert st.unbind(1, "z") == ["101"]
    snap = st.snapshot()
    assert snap["1"] == ["101"] and snap["2"] == ["101"] and snap["3"] == []
    # 另一个实例（模拟看板进程）现读同一文件
    assert GroupStore(str(path)).users_of(1) == ["101"]
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1 and data["groups"]["1"] == ["101"]
    assert "updated_at" in data


def test_group_store_absent_and_disabled(tmp_path):
    st = GroupStore(str(tmp_path / "nope" / "butler_groups.json"))
    assert st.users_of(2) == []
    assert st.snapshot() == {"1": [], "2": [], "3": []}
    off = GroupStore("")                              # hermes.root 与 [groups].file 都未配
    assert off.users_of(1) == []
    with pytest.raises(RuntimeError):
        off.bind(1, "101")


def test_group_store_keeps_unknown_types(tmp_path):
    path = tmp_path / "butler_groups.json"
    path.write_text(json.dumps({"groups": {"1": ["101", " "], "7": ["9"]}}, ensure_ascii=False),
                    encoding="utf-8")
    snap = GroupStore(str(path)).snapshot()
    assert snap["1"] == ["101"] and snap["7"] == ["9"] and snap["2"] == []


# ---------------------------------------------------------------- /v1/push 路由

@pytest.fixture
def push_home(make_home, start_server, monkeypatch):
    """临时 HERMES_HOME + 真 HTTP；wxbot 代发已被替换，calls 记录逐条外发。"""
    import butler.agent.core as core

    calls = []
    monkeypatch.setattr(core, "push_to_wxbot",
                        lambda cfg, contact, text, log=None: (calls.append((contact, text)),
                                                              (True, "sent"))[1])
    home = make_home()

    def set_groups(groups: dict):
        gf = home.root / "cache" / "butler_groups.json"
        gf.parent.mkdir(parents=True, exist_ok=True)
        gf.write_text(json.dumps({"version": 1, "groups": groups}, ensure_ascii=False),
                      encoding="utf-8")

    home.set_groups = set_groups
    home.calls = calls
    home.base = start_server(home.butler, home.cfg)
    return home


def test_push_group_by_message_type(push_home):
    """type=2 群发：新闻消息（messageType=1）发给字典里绑定的 101 与 z。"""
    push_home.set_groups({"1": ["101", "z"], "2": ["101"]})
    code, body = _call_push(push_home.base, {"type": 2, "messageType": 1, "text": "今日新闻"})
    assert code == 200 and body["reply"] is None
    meta = body["meta"]
    assert meta["ok"] is True and meta["type"] == 2 and meta["messageType"] == 1
    assert meta["targets"] == ["101", "z"]
    assert push_home.calls == [("101", "今日新闻"), ("z", "今日新闻")]
    flow = Path(push_home.cfg.flow_log_path()).read_text(encoding="utf-8")
    assert "[外发] 已发出 → 101: 今日新闻" in flow
    assert "[外发] 已发出 → z: 今日新闻" in flow


def test_push_group_reads_bindings_at_push_time(push_home):
    """绑定在请求时才生效（看板改完字典，下一条群发就用新名单）。"""
    push_home.set_groups({"1": ["101"]})
    assert _call_push(push_home.base, {"type": 2, "messageType": 1, "text": "第一次"})[1]["meta"]["targets"] == ["101"]
    push_home.set_groups({"1": ["101", "z"]})
    code, body = _call_push(push_home.base, {"type": 2, "messageType": 1, "text": "第二次"})
    assert body["meta"]["targets"] == ["101", "z"]
    assert push_home.calls[-2:] == [("101", "第二次"), ("z", "第二次")]


def test_push_group_no_bindings(push_home):
    push_home.set_groups({"1": ["101"]})
    code, body = _call_push(push_home.base, {"type": 2, "messageType": 3, "text": "没人绑"})
    assert code == 200
    assert body["meta"]["ok"] is False and "未绑定" in body["meta"]["detail"]
    assert push_home.calls == []


def test_push_direct_records_message_type(push_home):
    """type=1 指定用户发送：messageType 只做记录，不影响目标。"""
    code, body = _call_push(push_home.base,
                            {"contact": "101", "text": "hi", "type": 1, "messageType": 2})
    assert code == 200
    meta = body["meta"]
    assert meta["ok"] is True and meta["contact"] == "101"
    assert meta["type"] == 1 and meta["messageType"] == 2
    assert push_home.calls == [("101", "hi")]


def test_push_type_validation(push_home):
    base = push_home.base
    assert _call_push(base, {"type": 2, "text": "x"})[0] == 400            # 群发缺 messageType
    assert _call_push(base, {"type": 2, "messageType": "abc", "text": "x"})[0] == 400
    assert _call_push(base, {"type": 3, "text": "x"})[0] == 400            # type 只支持 1/2
    assert _call_push(base, {"type": "abc", "text": "x"})[0] == 400
    assert _call_push(base, {"text": "x"})[0] == 400                       # type=1 缺 contact
    # 旧请求（不给 type / messageType）行为不变
    code, body = _call_push(base, {"contact": "101", "text": "hi"})
    assert code == 200 and body["meta"]["ok"] is True \
        and body["meta"]["type"] == 1 and body["meta"]["messageType"] is None


# ---------------------------------------------------------------- 看板 /api/groups

def test_dashboard_groups_api(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_GROUP_FILE", str(tmp_path / "cache" / "butler_groups.json"))
    wxcfg = tmp_path / "config.wxbot.toml"
    wxcfg.write_text('[bot]\nbound_users = ["101", "z"]\n', encoding="utf-8")
    monkeypatch.setenv("WXBOT_CONFIG", str(wxcfg))

    dash = _load_dashboard()
    dash.Handler.home = str(tmp_path)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), dash.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        code, body = _req(base + "/api/groups")
        assert code == 200 and body["ok"] is True
        assert [t["type"] for t in body["message_types"]] == [1, 2, 3]
        assert [t["label"] for t in body["message_types"]] == ["新闻消息", "问候消息", "其他"]
        assert [c["name"] for c in body["contacts"]] == ["101", "z"]

        # 把 z 绑定到 messageType=1（看板上的「绑定」操作）
        code, body = _req(base + "/api/groups", {"action": "bind", "type": 1, "user": "z"})
        assert code == 200 and body["ok"] is True
        t1 = next(t for t in body["message_types"] if t["type"] == 1)
        assert t1["users"] == ["z"] and t1["count"] == 1
        assert t1["members"][0]["name"] == "z" and t1["members"][0]["known"] is True

        # 字典文件真的写下去了（butler 侧读得到）
        assert GroupStore(str(tmp_path / "cache" / "butler_groups.json")).users_of(1) == ["z"]

        # 再绑 101 → 两个用户
        _, body = _req(base + "/api/groups", {"action": "bind", "type": 1, "user": "101"})
        t1 = next(t for t in body["message_types"] if t["type"] == 1)
        assert t1["users"] == ["z", "101"]

        # 解绑
        _, body = _req(base + "/api/groups", {"action": "unbind", "type": 1, "user": "z"})
        t1 = next(t for t in body["message_types"] if t["type"] == 1)
        assert t1["users"] == ["101"]

        # 校验
        assert _req(base + "/api/groups", {"action": "bind", "type": 0, "user": "z"})[0] == 400
        assert _req(base + "/api/groups", {"action": "nope", "type": 1, "user": "z"})[0] == 400
        assert _req(base + "/api/groups", {"action": "bind", "type": 1, "user": ""})[0] == 400
    finally:
        httpd.shutdown()
        httpd.server_close()
