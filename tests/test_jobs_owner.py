"""定时任务归属推断与看板分组：deliver → Profile → script sidecar → 脚本内置目标 → 全局/无归属。

对齐 Hermes 侧 no_agent 任务的格式（<Hermes root>/cron/jobs.json）：
  deliver=local，收件人线索在脚本同名 json 的 type/contact，或脚本内 TARGET= / "wxbot-<uid>"。
"""
from __future__ import annotations

import importlib.util
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dashboard():
    """log 不是包（无 __init__.py），按文件路径加载看板模块。"""
    spec = importlib.util.spec_from_file_location("_dash_server_jobs", ROOT / "log" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _req(url):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read().decode("utf-8") or "{}")


def _job(jid, name, script=None, deliver="local", enabled=True, state="scheduled", prompt=None):
    j = {"id": jid, "name": name, "deliver": deliver, "enabled": enabled, "state": state}
    if script:
        j["script"] = script
    if prompt:
        j["prompt"] = prompt
    return j


def _write_home(tmp: Path):
    """还原真实布局：6 个任务 + scripts/ 下的 sidecar json 与提醒 wrapper。"""
    scripts = tmp / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (tmp / "cron").mkdir(parents=True, exist_ok=True)

    (scripts / "morning_report.py").write_text("# noop\n", encoding="utf-8")
    (scripts / "morning_report.json").write_text(
        json.dumps({"type": 1, "messageType": 1, "contact": "101", "texts": ["早报"]},
                   ensure_ascii=False), encoding="utf-8")
    (scripts / "morning_weather.py").write_text("# noop\n", encoding="utf-8")
    (scripts / "morning_weather.json").write_text(
        json.dumps({"type": 1, "messageType": 2, "contact": "z"}, ensure_ascii=False),
        encoding="utf-8")
    (scripts / "greeting_dispatch.py").write_text("# noop\n", encoding="utf-8")
    (scripts / "greeting_dispatch.json").write_text(
        json.dumps({"type": 2, "messageType": 2}, ensure_ascii=False), encoding="utf-8")
    (scripts / "reminder_7f3a91c2.py").write_text(
        'TARGET = "101"\nTEXT = "该喝水啦"\n', encoding="utf-8")
    (scripts / "legacy_reminder.py").write_text(
        'import sys\nsys.argv = ["butler_reminder_push.py", "main", "8ff2ffa5", "wxbot-101"]\n',
        encoding="utf-8")

    jobs = [
        _job("j-report", "每日早报-微信101-9点10", script="morning_report.py"),
        _job("j-weather", "每日天气-带伞提醒-微信z-8点整", script="morning_weather.py"),
        _job("j-greet", "工作日问候-喝水活动-随机抖动", script="greeting_dispatch.py"),
        _job("j-drink", "喝水提醒-1min", script="reminder_7f3a91c2.py",
             enabled=False, state="completed"),
        _job("j-legacy", "旧提醒-8ff2ffa5", script="legacy_reminder.py"),
        _job("j-deliver", "微信群投递任务", script="morning_report.py",
             deliver="weixin:o9cq80abc@im.wechat"),
        _job("j-orphan", "无脚本本地任务"),
        _job("j-prompt", "提醒-权限通道自检-101",
             prompt='python C:/example/hermes/scripts/butler_push.py --contact 101 '
                    '--text "自检" --type 1 --message-type 3'),
    ]
    (tmp / "cron" / "jobs.json").write_text(
        json.dumps({"jobs": jobs, "updated_at": "2026-10-12T00:00:00+08:00"},
                   ensure_ascii=False), encoding="utf-8")
    return tmp


def test_collect_jobs_owner_inference(tmp_path):
    home = _write_home(tmp_path)
    dash = _load_dashboard()
    jobs = {j["job_id"]: j for j in dash.collect_jobs(str(home))}
    assert len(jobs) == 8

    r = jobs["j-report"]                       # sidecar：type=1 + contact
    assert (r["uid"], r["uid_source"], r["scope"]) == ("101", "script", "user")
    assert r["push_type"] == 1 and r["message_type"] == 1

    w = jobs["j-weather"]
    assert (w["uid"], w["uid_source"]) == ("z", "script")
    assert w["message_type"] == 2

    g = jobs["j-greet"]                        # sidecar：type=2 → 全局群发
    assert g["uid"] == "" and g["uid_key"] == ""
    assert g["scope"] == "global" and g["push_type"] == 2 and g["message_type"] == 2

    d = jobs["j-drink"]                        # 脚本内 TARGET = "101"
    assert (d["uid"], d["uid_source"]) == ("101", "script-target")

    l = jobs["j-legacy"]                       # 脚本内 "wxbot-101" 字面量
    assert (l["uid"], l["uid_source"]) == ("101", "script-profile")

    dv = jobs["j-deliver"]                     # deliver 优先，不信 sidecar
    assert (dv["uid"], dv["uid_source"]) == ("o9cq80abc@im.wechat", "deliver")

    o = jobs["j-orphan"]                       # 全无线索
    assert o["uid"] == "" and o["scope"] == "" and o["uid_source"] == "deliver"

    p = jobs["j-prompt"]                      # prompt 里 --contact 101（agent 任务）
    assert (p["uid"], p["uid_source"]) == ("101", "prompt")


def test_jobs_api_groups(tmp_path, monkeypatch):
    home = _write_home(tmp_path)
    legacy_config = tmp_path / 'test-butler.toml'
    legacy_config.write_text('[agent]\nprovider="hermes"\n', encoding='utf-8')
    monkeypatch.setenv('BUTLER_CONFIG', str(legacy_config))
    dash = _load_dashboard()
    dash.Handler.home = str(home)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), dash.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    try:
        code, body = _req(base + "/api/jobs")
        assert code == 200 and body["count"] == 8
        groups = {u["uid"]: u for u in body["users"]}
        assert set(groups) == {"101", "z", "o9cq80abc", "global", ""}

        assert groups["101"]["count"] == 4     # 早报 + 喝水提醒 + 旧提醒 + 自检
        assert groups["z"]["count"] == 1
        assert groups["global"]["name"] == "全局任务"
        assert groups["global"]["count"] == 1
        assert groups[""]["name"] == "系统 / 无归属"

        # 只有一个全局任务时它排无归属之前（用户 → 全局 → 无归属）
        order = [u["uid"] for u in body["users"]]
        assert order.index("global") < order.index("")
        assert set(order[:3]) == {"101", "z", "o9cq80abc"}

        # 侧栏过滤：只看全局任务 / 只看某个用户
        code, body = _req(base + "/api/jobs?uid=global")
        assert code == 200
        assert [u["uid"] for u in body["users"]] == ["global"]
        assert body["users"][0]["jobs"][0]["scope"] == "global"

        code, body = _req(base + "/api/jobs?uid=101")
        assert [u["uid"] for u in body["users"]] == ["101"]
        assert {j["job_id"] for j in body["users"][0]["jobs"]} == {
            "j-report", "j-drink", "j-legacy", "j-prompt"}
    finally:
        httpd.shutdown()
        httpd.server_close()
