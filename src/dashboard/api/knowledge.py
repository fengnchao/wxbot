#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对话记录与知识库：两个只读投影；提炼的触发只转发给 Butler。

库目录不存在不是错误——没聊过就是没有历史，页面显示空态即可。
提炼由 Butler 进程里的调度器写入，管理台不直接碰库：这里只读状态、转发一次手动触发。
"""


def _view(ctx, *, with_identity=False):
    from butler.config import load as load_butler
    cfg = load_butler(ctx.butler_config_path())
    root = cfg.data_path()
    identity_path = (cfg.contact_database or root / 'business.sqlite3') if with_identity else None
    return ctx.KnowledgeView(root / 'knowledge', identity_path=identity_path)


def _template_view(ctx):
    """模板写入走 data/knowledge/template.md，路径由数据目录推出，不由请求指定。"""
    from butler.config import load as load_butler
    cfg = load_butler(ctx.butler_config_path())
    return ctx.KnowledgeTemplateView(cfg.data_path())


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
    try:
        return 200, _view(ctx, with_identity=True).facts(
            owner=ctx.one('owner'), query=ctx.one('q'),
            limit=ctx.num('limit', 50), offset=ctx.num('offset', 0),
            contact=ctx.one('contact'), group=ctx.one('group'))
    except Exception as exc:
        return 500, {'read_only': True, 'status': 'error',
                     'error': '无法读取知识库（' + type(exc).__name__ + '）'}


def delete_fact(ctx):
    from dashboard.api.support import _butler_post

    if not ctx.confirm('X-Wxbot-Knowledge-Action'):
        return 403, {'error': '事实删除只接受当前页面的确认请求'}
    try:
        return _butler_post(ctx.load_butler_config(), '/v1/knowledge/facts/delete', ctx.body())
    except (RuntimeError, ValueError) as exc:
        return 503, {'ok': False, 'error': str(exc)}


def extract_status(ctx):
    """自动提炼的开关与进度：直接问 Butler，管理台不自己解析数据目录。"""
    _, config = ctx.load_butler_contacts()
    try:
        payload = ctx.fetch_butler_data(config, '/v1/knowledge/extract')
    except (RuntimeError, ValueError) as exc:
        return 200, {'available': False, 'error': str(exc)}
    return 200, {'available': True, **payload}


def template_read(ctx):
    """模板的当前内容与生效来源：覆盖层坏了也把原文和报错一起返回，页面才能修。"""
    try:
        return 200, _template_view(ctx).read()
    except Exception as exc:
        return 500, {'read_only': False, 'status': 'error',
                     'error': '无法读取知识模板（' + type(exc).__name__ + '）'}


def template_save(ctx):
    """校验 / 保存 / 恢复内置模板；只改配置，不碰任何 vault。"""
    if not ctx.confirm('X-Wxbot-Knowledge-Action'):
        return 403, {'ok': False, 'error': '知识模板修改只接受当前页面的确认请求'}
    TemplateConflict, TemplateError = ctx.TemplateConflict, ctx.TemplateError
    try:
        return 200, _template_view(ctx).save(ctx.body())
    except TemplateConflict as exc:
        return 409, {'ok': False, 'error': str(exc)}
    except TemplateError as exc:
        return 400, {'ok': False, 'error': '模板校验未通过', 'errors': exc.errors}
    except ValueError as exc:
        return 400, {'ok': False, 'error': str(exc)}
    except OSError as exc:
        return 503, {'ok': False, 'error': '知识模板保存失败（' + type(exc).__name__ + '）'}


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
