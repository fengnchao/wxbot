#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""连接方式与进程自查。"""


def connection(ctx):
    """本机管理台还是对接外部管理台 —— 决定业务页面是否只读。"""
    mode = ctx.dashboard_mode()
    return 200, {'mode': mode, 'local_butler': mode == 'local', 'business_tools': mode == 'local',
                 'note': '外部服务的用户、记忆和心跳请在对端管理台维护' if mode != 'local' else ''}


def health(ctx):
    """数据源自查：home 与发现的 state.db 清单。"""
    return 200, {"ok": True, "home": ctx.home,
                 "dbs": [{"profile": a, "path": b} for a, b in ctx.discover_dbs(ctx.home)]}
