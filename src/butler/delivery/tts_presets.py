"""WebUI preset names bound to service-owned conversation names."""
import hashlib
import json
import os
from pathlib import Path
import uuid

from common.config_lock import config_lock
from .gradio_tts import GradioTtsClient


class PresetBindings:
    def __init__(self, path, *, client=None):
        self.path = Path(path).resolve()
        self.client = client or GradioTtsClient(timeout=15)

    def _state(self):
        if not self.path.exists():
            state = {'version': 1, 'presets': {}}
        else:
            if self.path.stat().st_size > 1024 * 1024:
                raise ValueError('预设绑定配置过大')
            try:
                state = json.loads(self.path.read_text(encoding='utf-8'))
            except (ValueError, UnicodeError) as exc:
                raise ValueError('预设绑定配置无效，请检查后重试') from exc
        if (not isinstance(state, dict) or set(state) != {'version', 'presets'}
                or type(state.get('version')) is not int or state['version'] != 1 or not isinstance(state.get('presets'), dict)
                or any(not isinstance(k, str) or not k.strip() or len(k) > 256 or
                       not isinstance(v, str) or not v.strip() or len(v) > 256 for k, v in state['presets'].items())):
            raise ValueError('预设绑定配置格式无效')
        encoded = json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        return state, hashlib.sha256(encoded).hexdigest()

    def snapshot(self, contact):
        state, version = self._state()
        return {'preset': state['presets'].get(contact, ''), 'version': version}

    def get(self, contact):
        return self.snapshot(contact)['preset']

    def list(self, contact):
        result = {'ok': True, **self.snapshot(contact)}
        try:
            result.update(presets=self.client.presets(), available=True, error='')
        except Exception:
            result.update(presets=[], available=False, error='网页预设读取失败，请确认本机 IndexTTS 网页已启动，再刷新预设。')
        return result

    def bind(self, contact, preset, version):
        if not isinstance(contact, str) or not contact.strip() or len(contact) > 256:
            raise ValueError('会话名称无效')
        if not isinstance(preset, str) or len(preset) > 256 or (preset and not preset.strip()):
            raise ValueError('音色预设名称无效')
        if not isinstance(version, str) or version != self.snapshot(contact)['version']:
            raise ValueError('preset version conflict；请刷新预设后重新选择')
        if preset:
            try:
                names = self.client.presets()
            except Exception as exc:
                raise ValueError('无法校验网页预设，请启动 IndexTTS 后重试') from exc
            if preset not in names:
                raise ValueError('网页音色预设不存在，请刷新后选择')
        # Do not hold the configuration lock while calling the WebUI.
        with config_lock(self.path):
            state, current = self._state()
            if current != version:
                raise ValueError('preset version conflict；请刷新预设后重新选择')
            if preset:
                state['presets'][contact] = preset
            else:
                state['presets'].pop(contact, None)
            encoded = json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
            if len(encoded) > 1024 * 1024:
                raise ValueError('预设绑定配置超过大小上限')
            saved = {'ok': True, 'preset': state['presets'].get(contact, ''),
                     'version': hashlib.sha256(encoded).hexdigest()}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
            try:
                with temporary.open('xb') as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
        return saved
