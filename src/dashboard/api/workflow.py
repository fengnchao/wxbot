#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消息工作流：全链路总览、单条全文、模型实时输出与记录删除。

视图类与工具函数一律经 ctx 取（等价于拆分前直接引用 server 的全局名）。
"""
import sqlite3


def read(ctx):
    """收发队列 + wxbot + Telegram 三条链路合成一张图。"""
    from dashboard.model_stream_view import resolve_model
    try:
        view = ctx.config_view()
        view.read()
        config = view._raw.get('butler') or {}
        wx = view._raw.get('wxbot') or {}
        model = resolve_model(wx, config)
        contacts = ctx.load_wxbot_contacts()
        payload = ctx.WorkflowView(**view.flow_options(),
                                   contacts=list(contacts.values()) if isinstance(contacts, dict) else contacts,
                                   backend=model['provider'], model=model).read()
        telegram = ctx.TelegramView(view.root / 'config.telegram-bot.toml',
                                    view.butler_path).workflow()
        payload['sources'].append(telegram['source'])
        payload['nodes'].append(dict(id=8, key='telegram', label='Telegram', description='机器人收件与新闻提交'))
        payload['nodes'].append(dict(id=9, key='news', label='Butler · 新闻投递', description='按新闻分组逐人投递'))
        payload['messages'].extend(telegram['messages'])
        counts = telegram['counts']
        payload['counts']['telegram'] = sum(counts.values())
        payload['counts']['active'] = payload['counts'].get('active', 0) + sum(
            v for k, v in counts.items() if k not in ctx.TELEGRAM_TERMINAL)
        payload['counts']['issues'] = payload['counts'].get('issues', 0) + sum(
            v for k, v in counts.items() if k in ctx.TELEGRAM_ISSUES)
        if payload['status'] != 'ok':
            payload['sources'].append(dict(name='wxbot 队列', status=payload['status'],
                                           error=payload['error'], truncated=False))
            if telegram['messages']:
                payload['status'] = 'ok'
        return 200, view.scrub(payload)
    except Exception as exc:
        return 500, {'status': 'error', 'error': '工作流配置不可读取（' + type(exc).__name__ + '）'}


def content(ctx):
    """单条消息的完整收发正文（服务端脱敏后返回）。"""
    from dashboard.workflow_content import read_content
    try:
        view = ctx.config_view()
        view.read()
        detail = read_content(view.queue_options()['path'], view.root / 'config.telegram-bot.toml',
                              ctx.one('id'))
        if detail is None:
            return 404, {'status': 'missing', 'error': '消息已删除或记录不存在'}
        for field in ('text', 'reply_text'):
            detail[field] = view.scrub_message_text(detail[field])
        return 200, {'status': 'ok', **detail}
    except ValueError:
        return 400, {'status': 'error', 'error': '消息标识或配置无效'}
    except (OSError, sqlite3.Error, KeyError, TypeError):
        return 503, {'status': 'error', 'error': '消息全文暂时不可读取'}


def stream(ctx):
    """模型实时输出分片：只脱敏展示值，保留协议结构。"""
    from dashboard.model_stream_view import read_stream
    from dashboard.workflow_content import read_content
    try:
        view = ctx.config_view()
        view.read()
        record_id = ctx.one('id', '')
        after = int(ctx.one('after', '0'))
        queue_path = view.queue_options()['path']
        if read_content(queue_path, view.root / 'config.telegram-bot.toml', record_id) is None:
            return 404, {'status': 'missing', 'error': '消息已移除或不存在'}
        payload = read_stream(queue_path, record_id, after=after)
        for event in payload['events']:
            for key in ('text', 'message', 'model', 'provider', 'tool', 'fallback'):
                if isinstance(event.get(key), str):
                    event[key] = view.scrub_message_text(event[key])
        return 200, payload
    except (ValueError, TypeError):
        return 400, {'error': '消息标识或读取位置无效'}
    except (OSError, sqlite3.Error):
        return 503, {'error': '模型实时输出暂不可读取'}


def delete(ctx):
    from dashboard.workflow_history import WorkflowConflict, WorkflowHistory
    if not ctx.confirm('X-Wxbot-Workflow-Action'):
        return 403, {'error': '删除记录仅接受当前页面的确认请求'}
    try:
        view = ctx.config_view()
        view.read()
        return 200, WorkflowHistory(view.queue_options()['path']).delete(ctx.body())
    except WorkflowConflict as exc:
        return 409, {'error': str(exc)}
    except (ValueError, TypeError) as exc:
        return 400, {'error': str(exc)}
    except (OSError, sqlite3.Error):
        return 503, {'error': '工作流记录暂不可删除，请刷新后重试'}
