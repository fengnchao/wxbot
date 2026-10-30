#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定时任务：按归属分组的总览 + 显式确认后的删除。"""


def read(ctx):
    """codex 模式直接读 Butler 运行时；否则扫 jobs.json + 脚本文本推断归属。"""
    config = ctx.load_butler_config()
    if (config.get('agent') or {}).get('provider') == 'codex':
        from dashboard.runtime_view import reminder_jobs
        return 200, reminder_jobs(ctx.fetch_butler_data(config, '/v1/runtime'))
    uid_filter = ctx.one("uid", "all")
    flt = (uid_filter or "all").split("@")[0].lower()
    jobs = ctx.collect_jobs(ctx.home)
    directory = ctx.load_directory(ctx.home)
    # 原始大小写 uid 的来源：收到的消息 > deliver 里的写法 > Profile 名
    msg_users, _, _ = ctx.build_users(ctx.home, directory)
    orig = {u["uid"].lower(): u["uid"] for u in msg_users}
    for j in jobs:
        k = j.get("uid_key") or ""
        if k and k in orig:
            j["uid"] = orig[k]
    by_uid = {}
    for j in jobs:
        k = j.get("uid_key") or ""
        if not k and j.get("scope") == "global":
            k = "global"                # 全局任务单独一组（群发，收件人按字典）
        if flt != "all" and k != flt:
            continue
        by_uid.setdefault(k or "(no-owner)", []).append(j)
    users_out = []
    for key, js in by_uid.items():
        nm = ""
        disp = ""
        if key == "global":
            nm = "全局任务"
        elif key != "(no-owner)":
            nm = ctx.display_of_ci(key, directory)
            disp = orig.get(key) or next((x.get("uid") for x in js if x.get("uid")), key)
            if not nm and disp:
                nm = disp
        for x in js:
            x["ui_state"] = ctx.jobs_ui_state(x)
        js.sort(key=lambda x: (x["ui_state"] != "active",
                               ctx._iso_to_epoch(x.get('next_run_at')) or float('inf'),
                               x.get('job_id') or ''))
        users_out.append({
            "uid": "global" if key == "global" else ("" if key == "(no-owner)" else key),
            "uid_display": "" if key in ("(no-owner)", "global") else (disp or key),
            "name": nm or "系统 / 无归属",
            "count": len(js),
            "active": sum(1 for x in js if x["ui_state"] == "active"),
            "paused": sum(1 for x in js if x["ui_state"] == "paused"),
            "error": sum(1 for x in js if x["ui_state"] == "error"),
            "jobs": js,
        })
    _rank = {"global": 1, "": 2}    # 用户在前，全局次之，无归属最后
    users_out.sort(key=lambda u: (_rank.get(u["uid"], 0), -u["active"], -u["count"], u["name"]))
    return 200, {
        "count": len(jobs),
        "active": sum(1 for j in jobs if ctx.jobs_ui_state(j) == "active"),
        "paused": sum(1 for j in jobs if ctx.jobs_ui_state(j) == "paused"),
        "error": sum(1 for j in jobs if ctx.jobs_ui_state(j) == "error"),
        "done": sum(1 for j in jobs if ctx.jobs_ui_state(j) == "done"),
        "users": users_out,
    }


def delete(ctx):
    # 函数内导入：测试会在 dashboard.job_admin 上打桩 request_job_delete。
    from dashboard.job_admin import request_job_delete
    if not ctx.confirm('X-Wxbot-Job-Action'):
        return 403, {'error': '任务删除仅接受当前页面的确认请求'}
    try:
        return request_job_delete(ctx.load_butler_config(), ctx.body())
    except (ValueError, TypeError):
        return 400, {'error': '任务删除请求无效，请刷新列表后重试'}
