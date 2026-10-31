"""Typed administrator operations. Callers must authenticate the server token first."""
from __future__ import annotations


def _text(data, key, *, required=True):
    value = data.get(key, '')
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f'{key} 必须是非空文本' if required else f'{key} 必须是文本')
    return value


def _version(data, minimum=1):
    value = data.get('version')
    if type(value) is not int or value < minimum:
        raise ValueError('version 无效，请刷新页面')
    return value


def _page(query):
    values = {}
    for name, default, minimum, maximum in (('offset', 0, 0, 1_000_000), ('limit', 50, 1, 100)):
        raw = query.get(name, [str(default)])
        raw = raw[0] if isinstance(raw, list) and raw else raw
        try:
            if isinstance(raw, bool):
                raise ValueError()
            value = int(raw)
        except (ValueError, TypeError):
            raise ValueError(f'{name} 必须是整数') from None
        if not minimum <= value <= maximum:
            raise ValueError(f'{name} 超出允许范围')
        values[name] = value
    return values


def dispatch_user_get(registry, path, query):
    def one(name):
        value = query.get(name, [''])
        value = value[0] if isinstance(value, list) and value else value
        if not isinstance(value, str):
            raise ValueError(f'{name} 必须是文本')
        return value
    if path == '/v1/users':
        filters = {key: one(key) for key in ('channel_type', 'status') if key in query}
        if filters.get('channel_type', '') not in ('', 'group', 'dm') or filters.get('status', '') not in ('', 'confirmed', 'disabled','observed'):
            raise ValueError('用户筛选条件无效')
        return registry.list_users(query=one('query'), contact=one('contact'), **_page(query), **filters)
    binding_id = one('binding_id')
    if not binding_id:
        raise ValueError('缺少 binding_id')
    if path == '/v1/users/memory':
        return registry.memories(binding_id)
    if path == '/v1/users/audit':
        return registry.audit(binding_id, **_page(query))
    raise ValueError('未知用户接口')


def dispatch_user_post(registry, payload):
    if not isinstance(payload, dict):
        raise ValueError('用户操作必须是 JSON 对象')
    action = _text(payload, 'action')
    fields = {
        'create': {'channel_type', 'contact', 'nickname', 'avatar'},
        'update': {'binding_id', 'version', 'nickname', 'contact', 'enabled', 'member_key', 'avatar'},
        'avatar': {'binding_id', 'version', 'avatar'},
        'link': {'binding_id', 'target_id', 'version', 'resolutions', 'expected_versions'},
        'memory_set': {'binding_id', 'version', 'key', 'value'},
        'memory_delete': {'binding_id', 'version', 'key'},
    }
    if action not in fields or set(payload) - fields[action] - {'action'}:
        raise ValueError('未知用户操作或字段')
    if action == 'create':
        values = {key: _text(payload, key) for key in ('channel_type', 'contact', 'nickname', 'avatar')}
        if values['channel_type'] not in ('group', 'dm'):
            raise ValueError('channel_type 只支持 group / dm')
        return registry.create(**values, reuse_name=False)
    binding_id = _text(payload, 'binding_id')
    version = _version(payload, minimum=0 if action.startswith('memory_') else 1)
    if action == 'update':
        changes = {key: _text(payload, key) for key in ('nickname', 'contact') if key in payload}
        if 'member_key' in payload:
            changes['member_key'] = _text(payload, 'member_key', required=False)
        if 'avatar' in payload:
            changes['avatar'] = _text(payload, 'avatar')
        if 'enabled' in payload:
            if type(payload['enabled']) is not bool:
                raise ValueError('enabled 必须是布尔值')
            changes['enabled'] = payload['enabled']
        if not changes:
            raise ValueError('缺少修改字段')
        return registry.update_binding(binding_id, version, **changes)
    if action == 'avatar':
        return registry.update_binding(binding_id, version, avatar=_text(payload, 'avatar'))
    if action == 'link':
        target = _text(payload, 'target_id')
        expected = payload.get('expected_versions')
        if not isinstance(expected, dict) or set(expected) != {'source_memory', 'target_memory', 'target_binding'} or any(
                type(value) is not int or value < (1 if key == 'target_binding' else 0) for key, value in expected.items()):
            raise ValueError('请先预览两个绑定及其记忆版本')
        resolutions = payload.get('resolutions')
        if resolutions is not None and (not isinstance(resolutions, dict) or any(
                not isinstance(key, str) or value not in ('source', 'target') for key, value in resolutions.items())):
            raise ValueError('冲突处理必须逐项选择 source / target')
        from butler.identity.contact_store import is_unified
        if is_unified(registry.store.path):
            raise ValueError('统一联系人请使用联系人身份合并预览，再确认合并')
        return registry.link(binding_id, target, version, resolutions=resolutions, expected_versions=expected)
    key = _text(payload, 'key')
    value = _text(payload, 'value', required=False) if action == 'memory_set' else ''
    return registry.change_memory(binding_id, key, value, version, delete=action == 'memory_delete')
