#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对话记录与知识库：两个只读投影；提炼的触发只转发给 Butler。

库目录不存在不是错误——没聊过就是没有历史，页面显示空态即可。
提炼由 Butler 进程里的调度器写入，管理台不直接碰库：这里只读状态、转发一次手动触发。
"""


def _view(ctx):
    from butler.config import load as load_butler
    cfg = load_butler(ctx.butler_config_path())
    return ctx.KnowledgeView(cfg.data_path() / 'knowledge')


def _session(ctx):
    """会话筛选：contact 精确匹配，channel_type 只认 dm/group，其余当没填。

    一个人可以同时有私聊和多个群的原文，所以 owner 之外还要能再缩一层。
    """
    channel = ctx.one('channel_type')
    return ctx.one('contact'), channel if channel in ('dm', 'group') else ''


def read(ctx):
    contact, channel = _session(ctx)
    try:
        return 200, _view(ctx).read(owner=ctx.one('owner'), query=ctx.one('q'),
                                    limit=ctx.num('limit', 50), offset=ctx.num('offset', 0),
                                    contact=contact, channel_type=channel)
    except Exception as exc:
        return 500, {'read_only': True, 'status': 'error',
                     'error': '无法读取对话记录（' + type(exc).__name__ + '）'}


def facts(ctx):
    contact, _ = _session(ctx)
    try:
        return 200, _view(ctx).facts(owner=ctx.one('owner'), query=ctx.one('q'),
                                     limit=ctx.num('limit', 50), offset=ctx.num('offset', 0),
                                     contact=contact)
    except Exception as exc:
        return 500, {'read_only': True, 'status': 'error',
                     'error': '无法读取知识库（' + type(exc).__name__ + '）'}


def extract_status(ctx):
    """自动提炼的开关与进度：直接问 Butler，管理台不自己解析数据目录。"""
    _, config = ctx.load_butler_contacts()
    try:
        payload = ctx.fetch_butler_data(config, '/v1/knowledge/extract')
    except (RuntimeError, ValueError) as exc:
        return 200, {'available': False, 'error': str(exc)}
    return 200, {'available': True, **payload}


def extract_trigger(ctx):
    """立即提炼一批：后台线程在 Butler 里跑，这里不等结果。"""
    _, config = ctx.load_butler_contacts()
    body = ctx.body()
    payload = {}
    owner = body.get('owner')
    if isinstance(owner, str) and owner.strip():
        payload['owner'] = owner.strip()
    if body.get('batch') is not None:
        payload['batch'] = body.get('batch')
    if body.get('dry_run') is True:
        payload['dry_run'] = True
    try:
        code, result = ctx.trigger_butler_extract(config, payload)
    except (RuntimeError, ValueError) as exc:
        return 503, {'ok': False, 'error': str(exc)}
    if code >= 400:
        return code, {'ok': False, 'code': result.get('code'),
                      'error': result.get('error') or f'Butler 返回 HTTP {code}'}
    return 202, {'ok': True, 'status': result.get('status', 'started')}
