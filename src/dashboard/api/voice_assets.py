"""音色资产与会话绑定 API。"""

from dashboard.voice_admin import VoiceAdmin


def _admin(ctx):
    path = None
    try:
        path = ctx.wxbot_config_path()
    except Exception:
        path = None
    return VoiceAdmin(path)


def list_assets(ctx):
    try:
        return 200, _admin(ctx).list_assets()
    except ValueError as exc:
        return 400, {'error': str(exc)}


def preview(ctx):
    try:
        return 200, _admin(ctx).preview(ctx.one('id'))
    except ValueError as exc:
        return 404, {'error': str(exc)}


def bindings(ctx):
    try:
        return 200, _admin(ctx).bindings()
    except ValueError as exc:
        return 400, {'error': str(exc)}


def save(ctx):
    """统一写入口：action=register|rename|delete|bind。"""
    if not ctx.confirm('X-Wxbot-Voice-Action'):
        return 403, {'error': '需要本机页面确认音色操作'}
    body = ctx.body_large() if hasattr(ctx, 'body_large') else ctx.body()
    action = str((body or {}).get('action') or '').strip()
    admin = _admin(ctx)
    try:
        if action == 'register':
            return 200, admin.register(body)
        if action == 'rename':
            return 200, admin.rename(body)
        if action == 'delete':
            return 200, admin.delete(body)
        if action == 'bind':
            return 200, admin.bind(body)
        return 400, {'error': '未知 action（register/rename/delete/bind）'}
    except ValueError as exc:
        return 400, {'error': str(exc)}
