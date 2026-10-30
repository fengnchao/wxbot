"""主流程不变量：顺序、行动标记、白名单、静默语义、故障降级、提醒 skill。"""
from __future__ import annotations

import json

import pytest

from butler.agent import router
from butler.agent.hermes import HermesError
from conftest import DEFAULT_PENDING


def act(**kw) -> str:
    """拼一个行动标记（模型该吐出来的东西）。"""
    return "<<butler:action %s>>" % json.dumps(kw, ensure_ascii=False)


def test_claim_precedes_the_model_call(make_home):
    """补发必须先读、先认领，最后才调模型 —— 否则模型自己再查一次会重复送达。"""
    home = make_home(replies=["好，我给你列一下" + act(skill="reminder.list")])
    home.butler.handle("101", "我有哪些提醒")
    assert home.log() == ["json", "flush reminder-x@2026-10-11 00:00:00", "chat"]


def test_forwards_profile_uid_and_untouched_text(make_home):
    home = make_home(replies=["嗯"])
    home.butler.handle("101", "我有哪些提醒")
    call = home.hermes.calls[0]
    assert (call["profile"], call["uid"]) == ("wxbot-101", "101")
    assert call["text"] == "我有哪些提醒", "用户文本必须原样进 payload"


def test_marker_stripped_and_action_executed(make_home):
    home = make_home(replies=["我给你列一下" + act(skill="reminder.list")])
    res = home.butler.handle("101", "我有哪些提醒")
    assert "<<butler:action" not in (res.reply or "")
    assert [a.skill for a in res.actions] == ["reminder.list"] and res.actions[0].ok
    assert "喝水" in res.reply, "本地 skill 产出的文本要进最终回复"
    assert res.reply.startswith(router.PENDING_HEADER)


def test_unknown_skill_refused_without_losing_the_reply(make_home):
    home = make_home(replies=["我把文件删了" + act(skill="rm -rf /")])
    res = home.butler.handle("101", "随便")
    assert res.actions and not res.actions[0].ok
    assert "白名单" in res.actions[0].detail
    assert "删了" in res.reply, "拒绝一个动作不能把回复也丢掉"


@pytest.mark.parametrize("reply,backlog", [
    ("[SILENT]", False),       # 静默 + 无积压 → 什么都不发
    ("[SILENT]", True),        # 静默 + 有积压 → 积压照样发（静默的模型不能吞队列）
    ("好的", False),           # 正常回复
    ("好的", True),            # 正常回复 + 补发
])
def test_silence_and_backlog_are_independent(make_home, reply, backlog):
    home = make_home(replies=[reply], pending_items=DEFAULT_PENDING if backlog else [])
    res = home.butler.handle("101", "嗯")
    silent = reply.startswith("[SILENT]")
    assert res.meta["model_silent"] is silent
    assert (res.reply is None) is (silent and not backlog)
    assert res.meta["sent"] is (res.reply is not None)
    assert ("⏰ 该喝水啦" in (res.reply or "")) is backlog
    if silent:
        assert "[SILENT]" not in (res.reply or ""), "标记本身不能漏给用户"


@pytest.mark.parametrize("exc,expect", [
    (HermesError("boom", 0), "稍后再试"),
    (HermesError("bad key", 401), "密钥"),          # 401 是配置错，不该报成"网络抖动"
])
def test_hermes_failure_degrades_but_still_ships_backlog(make_home, exc, expect):
    home = make_home(replies=[exc])
    res = home.butler.handle("101", "在吗")
    assert expect in res.reply
    assert res.reply.startswith(router.PENDING_HEADER), "模型挂了也要把认领过的补发发出去"


def test_reminder_cancel_marks_and_prunes_only_its_cron(make_home):
    home = make_home(replies=["好" + act(skill="reminder.cancel", args={"id": "abc123"})],
                     cron_jobs=[{"id": "j1", "name": "提醒-x"}, {"id": "j2", "name": "追1"},
                                {"id": "j9", "name": "别的任务"}])
    res = home.butler.handle("101", "把喝水那个提醒撤了")
    store = json.loads((home.profile / "reminders.json").read_text(encoding="utf-8"))
    assert store["reminders"][0]["status"] == "cancelled"
    assert [j["id"] for j in home.jobs()["jobs"]] == ["j9"], "只能摘掉这条提醒自己的任务"
    assert res.actions[0].ok


def test_reminder_create_shells_out_to_the_local_script(make_home, tmp_path):
    """本地脚本优先：create 不该让模型自由发挥。"""
    home = make_home(replies=["稍等" + act(skill="reminder.create",
                                           args={"content": "喝水", "at": "+30m"})])
    (tmp_path / "butler_reminder_create.py").write_text(
        "import sys\nprint('stub ok')\nsys.exit(0)\n", encoding="utf-8")
    home.cfg.script_dir = str(tmp_path)
    res = home.butler.handle("101", "30 分钟后提醒我喝水")
    assert res.actions[0].ok and res.actions[0].detail == "stub ok"


def test_missing_script_is_reported_not_swallowed(make_home):
    home = make_home(replies=["稍等" + act(skill="reminder.create",
                                           args={"content": "喝水", "at": "+30m"})])
    home.cfg.script_dir = ""
    res = home.butler.handle("101", "提醒我喝水")
    assert not res.actions[0].ok and "找不到脚本" in res.actions[0].detail
