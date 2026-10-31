#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP 路由单张表：方法 + 路径 → api 处理器。

处理器签名 `fn(ctx) -> (status, body)`；body 由 http 层序列化为 JSON。
`/` 跳转与 `/app/` 静态文件属于传输层，见 dashboard.http，不在这张表里。
"""
from dashboard.api import (config, contacts, flow, groups, heartbeat, jobs, queue,
                           relay, runtime, system, users, workflow)

# 对接外部管理台时（installation.mode != "local"），这些路径的读写一律 503：
# 用户、记忆、心跳与转发都由对端维护。列表与原实现的拦截范围逐条对应。
BUSINESS_GET = frozenset({
    '/api/contacts', '/api/contacts/memory', '/api/contacts/audit', '/api/contacts/merge-preview',
    '/api/users', '/api/users/memory', '/api/users/audit', '/api/runtime',
    '/api/jobs', '/api/groups', '/api/heartbeat-config', '/api/heartbeat-status',
    '/api/skills', '/api/telegram-relay',
})

BUSINESS_POST = frozenset({
    '/api/contacts', '/api/users', '/api/jobs/delete', '/api/heartbeat-trigger',
    '/api/heartbeat-config', '/api/groups', '/api/news-config',
    '/api/telegram-relay', '/api/telegram-relay/resolve',
})

ROUTES = (
    ("GET", "/api/connection", system.connection),

    ("GET", "/api/telegram-relay", relay.read),
    ("GET", "/api/contacts", contacts.read),
    ("GET", "/api/contacts/merge-preview", contacts.merge_preview),
    ("GET", "/api/contacts/memory", contacts.detail),
    ("GET", "/api/contacts/audit", contacts.detail),
    ("GET", "/api/users", users.read),
    ("GET", "/api/users/memory", users.read),
    ("GET", "/api/users/audit", users.read),
    ("GET", "/api/workflow-content", workflow.content),
    ("GET", "/api/workflow-stream", workflow.stream),
    ("GET", "/api/workflow", workflow.read),
    ("GET", "/api/flow", flow.read),
    ("GET", "/api/runtime", runtime.read),
    ("GET", "/api/queue", queue.read),
    ("GET", "/api/configuration", config.read),
    ("GET", "/api/health", system.health),
    ("GET", "/api/jobs", jobs.read),
    ("GET", "/api/wxbot", flow.wxbot),
    ("GET", "/api/groups", groups.read),
    ("GET", "/api/heartbeat-config", heartbeat.read_config),
    ("GET", "/api/heartbeat-status", heartbeat.status),
    ("GET", "/api/skills", heartbeat.skills),

    ("POST", "/api/contacts", contacts.save),
    ("POST", "/api/workflow-delete", workflow.delete),
    ("POST", "/api/jobs/delete", jobs.delete),
    ("POST", "/api/telegram-relay/resolve", relay.resolve),
    ("POST", "/api/telegram-relay", relay.save),
    ("POST", "/api/users", users.save),
    ("POST", "/api/news-config", config.save_news),
    ("POST", "/api/configuration", config.save),
    ("POST", "/api/queue-delete-unsent", queue.delete_unsent),
    ("POST", "/api/queue-action", queue.action),
    ("POST", "/api/heartbeat-trigger", heartbeat.trigger),
    ("POST", "/api/groups", groups.save),
    ("POST", "/api/heartbeat-config", heartbeat.save_config),
)

_BY_METHOD = {}
for _method, _path, _handler in ROUTES:
    _BY_METHOD.setdefault(_method, {})[_path] = _handler


def match(method, path):
    """返回该请求的处理器；没有匹配返回 None。"""
    return _BY_METHOD.get(method, {}).get(path)


def gated(method, path):
    """该请求是否属于「非本机模式下由对端维护」的业务路径。"""
    if method == "GET":
        return path in BUSINESS_GET
    if method == "POST":
        return path in BUSINESS_POST
    return False
