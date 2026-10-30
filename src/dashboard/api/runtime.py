#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Butler 运行时状态（经本机 loopback 代理，凭证不出服务端）。"""


def read(ctx):
    config = ctx.load_butler_config()
    payload = ctx.fetch_butler_data(config, '/v1/runtime')
    view = ctx.config_view()
    view.read()
    return 200, view.scrub(payload)
