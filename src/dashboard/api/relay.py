#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram 转发（desktop relay）：只读写本机配置，核对动作走 Butler 服务端。"""


def read(ctx):
    try:
        return 200, ctx.relay_admin().read()
    except (OSError, ValueError, RuntimeError):
        return 503, {'error': 'Telegram 转发配置暂不可读，请检查本机配置'}


def save(ctx):
    SettingsConflict = ctx.SettingsConflict
    if not ctx.confirm('X-Wxbot-Relay-Action'):
        return 403, {'error': '转发设置仅接受当前页面的保存请求'}
    try:
        return 200, ctx.relay_admin().update(ctx.body())
    except SettingsConflict:
        return 409, {'error': '配置已被修改，草稿已保留；请刷新后重新编辑'}
    except ValueError as exc:
        return 400, {'error': str(exc)}
    except (OSError, RuntimeError):
        return 503, {'error': 'Telegram 转发设置保存失败，请检查本机配置'}


def resolve(ctx):
    if not ctx.confirm('X-Wxbot-Relay-Action'):
        return 403, {'error': '任务核对仅接受当前页面的确认请求'}
    try:
        return ctx.request_relay_resolution(ctx.load_butler_config(), ctx.body())
    except (OSError, ValueError, RuntimeError):
        return 503, {'error': 'Telegram 转发任务核对暂不可用'}
