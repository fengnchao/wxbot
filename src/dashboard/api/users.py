#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Butler 用户目录代理：凭证只留服务端，浏览器只看脱敏结果。"""


def read(ctx):
    path = '/v1' + ctx.path.removeprefix('/api') + ('?' + ctx.url.query if ctx.url.query else '')
    return ctx.request_user_admin(ctx.load_butler_config(), path)


def save(ctx):
    if not ctx.confirm('X-Wxbot-User-Action'):
        return 403, {'error': '用户操作仅接受当前页面发出的确认请求'}
    return ctx.request_user_admin(ctx.load_butler_config(), '/v1/users', ctx.body())
