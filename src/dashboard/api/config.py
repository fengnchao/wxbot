#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置总览与保存：wxbot/Butler 配置、新闻分组设置。

视图类与工具函数一律经 ctx 取（等价于拆分前直接引用 server 的全局名）。
"""


def read(ctx):
    return 200, ctx.config_view().read()


def save(ctx):
    ConfigEditor, ConfigConflict = ctx.ConfigEditor, ctx.ConfigConflict
    if not ctx.confirm('X-Wxbot-Config-Action'):
        return 403, {'ok': False, 'error': '配置修改只接受当前页面的确认请求'}
    view = ctx.config_view()
    try:
        result = ConfigEditor(view, policy_validator=ctx.validate_policy_skills).save(ctx.body())
        return 200, view.scrub(result)
    except ConfigConflict as exc:
        return 409, {'ok': False, 'error': view.scrub(str(exc))}
    except ValueError as exc:
        return 400, {'ok': False, 'error': view.scrub(str(exc))}
    except (OSError, RuntimeError) as exc:
        return 503, {'ok': False, 'error': '配置保存失败（' + type(exc).__name__ + '）'}
    except Exception as exc:
        return 500, {'ok': False, 'error': '配置保存失败（' + type(exc).__name__ + '）'}


def save_news(ctx):
    """新闻设置：与分组字典共用一份文件，写入走跨进程配置锁。"""
    if not ctx.confirm('X-Wxbot-Config-Action'):
        return 403, {'ok': False, 'error': '新闻设置仅接受当前页面的保存请求'}
    body = ctx.body()
    path = ctx.group_file_path(ctx.home)
    news = ctx.news_config
    try:
        if not isinstance(body, dict):
            raise ValueError('新闻设置格式无效')
        with ctx.config_lock(news.settings_path(path)):
            news.save_settings(path, body.get('settings'), body.get('version'))
        return 200, {'ok': True, 'news': news.payload(path)}
    except news.NewsConflict as exc:
        return 409, {'ok': False, 'error': str(exc)}
    except ValueError as exc:
        return 400, {'ok': False, 'error': str(exc)}
    except OSError as exc:
        return 503, {'ok': False, 'error': '新闻设置保存失败（' + type(exc).__name__ + '）'}
