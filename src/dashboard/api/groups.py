#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户分组字典（messageType → 绑定用户）：读取与 bind / unbind。"""


def read(ctx):
    return 200, ctx.build_groups_payload(ctx.home)


def save(ctx):
    body = ctx.body()
    store = ctx.unified_contact_store()
    if store:
        if not ctx.confirm('X-Wxbot-Contact-Action'):
            return 403, {'error': '请从联系人页面确认订阅修改'}
        try:
            conversation = next((c for c in store.snapshot()['conversations']
                                 if c['name'] == body.get('user')), None)
            if (conversation is None or body.get('action') not in {'bind', 'unbind'}
                    or ctx._as_pos_int(body.get('type')) is None):
                raise ValueError('订阅会话或类型无效')
            subscriptions = set(conversation['subscriptions'])
            mt = ctx._as_pos_int(body['type'])
            if body['action'] == 'bind':
                subscriptions.add(mt)
            else:
                subscriptions.discard(mt)
            ctx.contact_admin().save({'action': 'conversation', 'version': body.get('version'),
                                      'id': conversation['id'],
                                      'subscriptions': sorted(subscriptions)})
            return 200, ctx.build_groups_payload(ctx.home)
        except ValueError as exc:
            return (409 if 'version conflict' in str(exc) else 400), {'error': str(exc)}
    mt = ctx._as_pos_int(body.get("type"))
    action = str(body.get("action") or "").strip()
    user = str(body.get("user") or "").strip()
    if mt is None:
        return 400, {"ok": False,
                     "error": "type 非法（须为正整数：1=新闻消息 2=问候消息 3=其他）"}
    if action not in ("bind", "unbind"):
        return 400, {"ok": False, "error": "action 只支持 bind / unbind"}
    if not user or len(user) > 64:
        return 400, {"ok": False, "error": "user 为空或过长（微信窗口标题，≤64 字符）"}
    path = ctx.group_file_path(ctx.home)
    with ctx.config_lock(path):
        groups, _ = ctx.load_groups_file(path)
        users = list(groups.get(str(mt), []))
        if action == "bind":
            if user not in users:
                users.append(user)
        else:
            users = [x for x in users if x != user]
        groups[str(mt)] = users
        ctx.save_groups_file(path, groups)
    return 200, ctx.build_groups_payload(ctx.home)
