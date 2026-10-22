"""Versioned contract between a portable plugin bundle and the application."""
import json
from pathlib import Path

APPLICATION_VERSION='1.0.0'
PROTOCOL_VERSION=1


def validate_plugin(root):
    root=Path(root)
    protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'))
    if protocol.get('protocol_version')!=PROTOCOL_VERSION:
        raise ValueError('插件业务协议不兼容，请更新插件与项目（protocol v1 required）')
    try:
        minimum=tuple(int(x) for x in protocol['minimum_application_version'].split('.'))
        current=tuple(int(x) for x in APPLICATION_VERSION.split('.'))
    except (KeyError,ValueError,TypeError):
        raise ValueError('插件最低版本声明无效') from None
    if minimum>current:
        raise ValueError('插件需要更新版本的 Butler 项目')
    manifest=json.loads((root/'.codex-plugin/plugin.json').read_text(encoding='utf-8'))
    if manifest.get('name')!='butler-wechat':
        raise ValueError('Unexpected Butler plugin identifier')
    return {'protocol_version':PROTOCOL_VERSION,'version':manifest['version']}
