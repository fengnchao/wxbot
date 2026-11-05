"""Local admin HTTP adapter; preset ownership and writes belong to Butler."""
from butler.config import load
from butler.delivery.tts_presets import PresetBindings


def _known_contact(ctx, contact):
    store = ctx.unified_contact_store()
    if store is not None:
        contacts = store.snapshot()['conversations']
    else:
        contacts, _ = ctx.load_butler_contacts()
    if not isinstance(contact, str) or not any(row['name'] == contact for row in contacts):
        raise ValueError('未知的 Butler 联系人，请刷新联系人列表')


def _bindings(ctx):
    cfg = load(ctx.butler_config_path())
    return PresetBindings(cfg.data_path() / 'tts-presets.json')


def read(ctx):
    try:
        contact = ctx.one('contact')
        _known_contact(ctx, contact)
        return 200, _bindings(ctx).list(contact)
    except ValueError as exc:
        return 400, {'error': str(exc)}
    except OSError:
        return 503, {'error': '网页预设绑定配置暂不可读'}


def save(ctx):
    if not ctx.confirm('X-Wxbot-TTS-Action'):
        return 403, {'error': '请从联系人页面保存网页音色预设'}
    try:
        body = ctx.body()
        if not isinstance(body, dict) or set(body) != {'contact', 'preset', 'version'}:
            raise ValueError('网页预设绑定字段无效')
        _known_contact(ctx, body['contact'])
        return 200, _bindings(ctx).bind(body['contact'], body['preset'], body['version'])
    except ValueError as exc:
        return (409 if 'version conflict' in str(exc) else 400), {'error': str(exc)}
    except OSError:
        return 503, {'error': '网页预设绑定保存失败，请重试'}
