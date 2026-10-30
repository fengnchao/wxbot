#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联系人档案：读取、记忆与审计流水、保存（需本机页面确认）。"""


def read(ctx):
    try:
        return 200, ctx.contact_admin().read(id=ctx.one('id'), query=ctx.one('query'),
                                             kind=ctx.one('kind'))
    except ValueError as exc:
        return 400, {'error': str(exc)}


def detail(ctx):
    """`/api/contacts/memory` 与 `/api/contacts/audit` 共用：按 id 读明细。"""
    try:
        service = ctx.contact_admin()
        if ctx.path.endswith('/memory'):
            return 200, service.memory(ctx.one('id'))
        return 200, service.audit(ctx.one('id'), ctx.num('offset', 0), ctx.num('limit', 20))
    except ValueError as exc:
        return 400, {'error': str(exc)}


def save(ctx):
    if not ctx.confirm('X-Wxbot-Contact-Action'):
        return 403, {'error': '需要本机页面确认联系人操作'}
    try:
        return 200, ctx.contact_admin().save(ctx.body())
    except ValueError as exc:
        return (409 if 'version conflict' in str(exc) else 400), {'error': str(exc)}
