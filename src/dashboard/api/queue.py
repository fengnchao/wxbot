#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收发队列：只读总览 + 显式确认后的删除/重试/确认已发。

视图类与工具函数一律经 ctx 取（等价于拆分前直接引用 server 的全局名）。
"""
import sqlite3


def read(ctx):
    view = ctx.config_view()
    view.read()
    try:
        payload = ctx.QueueView(**view.queue_options()).read(
            contact=ctx.one('contact'), state=ctx.one('state', 'all'),
            limit=ctx.num('limit', 50), offset=ctx.num('offset', 0),
            scope=ctx.one('scope'), order=ctx.one('order'),
            offsets={t: ctx.num(t + '_offset', ctx.num('offset', 0))
                     for t in ('inbox', 'batches', 'outbox', 'rounds')})
        payload['telegram'] = ctx.TelegramView(view.root / 'config.telegram-bot.toml',
                                              view.butler_path).read(
            scope=ctx.one('scope', 'all'), state=ctx.one('state', 'all'),
            contact=ctx.one('contact'), limit=ctx.num('limit', 50),
            offset=ctx.num('telegram_offset', 0))
        return 200, view.scrub(payload)
    except Exception as exc:
        return 500, {'read_only': True, 'status': 'error',
                     'error': '无法读取队列配置（' + type(exc).__name__ + '）'}


def delete_unsent(ctx):
    if not ctx.confirm('X-Wxbot-Queue-Action'):
        return 403, {'ok': False, 'error': '队列删除仅接受当前页面发出的确认请求'}
    try:
        view = ctx.config_view()
        return 200, ctx.QueueActions(view.queue_options()['path']).delete_unsent(
            ctx.body(), telegram_config=view.root / 'config.telegram-bot.toml')
    except ValueError as exc:
        return 409, {'ok': False, 'error': str(exc)}
    except (OSError, sqlite3.Error) as exc:
        return 503, {'ok': False, 'error': '队列删除失败（' + type(exc).__name__ + '）'}


def action(ctx):
    if not ctx.confirm('X-Wxbot-Queue-Action'):
        return 403, {'ok': False, 'error': '队列操作仅接受当前页面发出的确认请求'}
    try:
        # 队列动作不涉及分组/日志配置，按最简形式建视图（与原实现一致）。
        view = ctx.ConfigView(ctx.wxbot_config_path(), ctx.butler_config_path(), ctx.home)
        return 200, ctx.QueueActions(view.queue_options()['path']).perform(ctx.body())
    except ValueError as exc:
        return 409, {'ok': False, 'error': str(exc)}
    except (OSError, sqlite3.Error) as exc:
        return 503, {'ok': False, 'error': '队列操作失败（' + type(exc).__name__ + '）'}
