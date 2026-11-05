"""IndexTTS WebUI's named Gradio queue API; no second model process."""
import copy
import ipaddress
import json
import time
import threading
import uuid
from urllib.parse import quote, urlsplit

import requests

from common.voice_audio import MAX_AUDIO_BYTES


class GradioTtsClient:
    def __init__(self, base_url='http://127.0.0.1:7860', *, timeout=600):
        parts = urlsplit(base_url)
        host = '127.0.0.1' if parts.hostname == 'localhost' else parts.hostname
        if (parts.scheme != 'http' or not host or not ipaddress.ip_address(host).is_loopback
                or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ('', '/')):
            raise ValueError('IndexTTS 地址必须是本机 HTTP 服务')
        self.base_url = f'http://[{host}]' if ':' in host else f'http://{host}'
        self.base_url += ':' + str(parts.port or 80)
        self.timeout = timeout
        self._local = threading.local()

    def _request(self, method, path, *, body=None, limit=2 * 1024 * 1024):
        with requests.Session() as session:
            session.trust_env = False
            with session.request(method, self.base_url + path, json=body, stream=True,
                                 allow_redirects=False, timeout=(5, 30)) as response:
                if response.status_code != 200:
                    raise RuntimeError('IndexTTS HTTP 请求失败')
                data = bytearray()
                for chunk in response.iter_content(65536):
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ValueError('IndexTTS 响应超出大小上限')
                return bytes(data)

    def _json(self, path):
        return json.loads(self._request('GET', path))

    def _call(self, name, data):
        started = time.monotonic()
        if not getattr(self._local, 'session_hash', None):
            self._local.session_hash = uuid.uuid4().hex
        config = self._json('/config')
        dependency = next(d for d in config['dependencies'] if d.get('api_name') == name)
        result = json.loads(self._request('POST', '/gradio_api/queue/join', body={
            'data': data, 'fn_index': dependency['id'], 'session_hash': self._local.session_hash}))
        event_id = result['event_id']
        uuid.UUID(event_id)  # Validate without changing Gradio's exact opaque key.
        with requests.Session() as session:
            session.trust_env = False
            with session.get(self.base_url + '/gradio_api/queue/data',
                             params={'session_hash': self._local.session_hash},
                             stream=True, allow_redirects=False, timeout=(5, 45)) as response:
                if response.status_code != 200:
                    raise RuntimeError('IndexTTS 队列连接失败，结果未知；勿自动重试')
                payload, size = [], 0
                for line in response.iter_lines(chunk_size=1, decode_unicode=False):
                    if time.monotonic() - started > self.timeout:
                        raise TimeoutError('IndexTTS 队列等待超时，勿自动重试')
                    size += len(line)
                    if size > 2 * 1024 * 1024:
                        raise ValueError('IndexTTS 队列响应过大')
                    line = line.decode('utf-8')
                    if line.startswith('data:'):
                        payload.append(line[5:].strip())
                    elif not line and payload:
                        message = json.loads('\n'.join(payload))
                        payload = []
                        if message.get('event_id') != event_id:
                            continue
                        if message.get('msg') == 'process_completed':
                            if message.get('success') is not True:
                                raise RuntimeError('IndexTTS 任务失败，勿自动重试')
                            value = message.get('output', {}).get('data')
                            if not isinstance(value, list):
                                raise ValueError('IndexTTS 队列回执无效')
                            return value
        raise RuntimeError('IndexTTS 队列断流，结果未知；勿自动重试')

    def presets(self):
        result = self._call('refresh_preset_choices', [])
        choices = result[0].get('choices', [])
        names = [value[1] if isinstance(value, (list, tuple)) else value for value in choices]
        return [name for name in names if isinstance(name, str) and name.strip()]

    def prepare(self, preset):
        self._local.session_hash = uuid.uuid4().hex
        if preset not in self.presets():
            raise ValueError('音色预设不存在，请先查询网页预设')
        info, config = self._json('/gradio_api/info'), self._json('/config')
        params = info['named_endpoints']['/gen_single']['parameters']
        names = [p['parameter_name'] for p in params]
        if names.count('prompt') != 1 or names.count('text') != 1:
            raise ValueError('IndexTTS 生成接口不兼容')
        gen = next(d for d in config['dependencies'] if d.get('api_name') == 'gen_single')
        loader = next(d for d in config['dependencies'] if d.get('api_name') == 'on_preset_load')
        components = {c['id']: c for c in config.get('components', [])}
        defaults = []
        for p in params:
            if p['parameter_name'] not in ('prompt', 'text') and not p.get('parameter_has_default'):
                component = components.get(gen['inputs'][len(defaults)], {})
                # Gradio marks empty optional Audio inputs as required in /info.
                if not (p['parameter_name'] == 'emo_ref_path' and component.get('type') == 'audio'
                        and component.get('props', {}).get('value') is None):
                    raise ValueError('IndexTTS 生成接口缺少默认参数')
            defaults.append(copy.deepcopy(p.get('parameter_default')))
        if len(gen['inputs']) != len(params):
            raise ValueError('IndexTTS 参数映射不兼容')
        prompt_component = gen['inputs'][names.index('prompt')]
        reference = self._call('on_preset_load', [preset])[loader['outputs'].index(prompt_component)]
        while isinstance(reference, dict) and reference.get('__type__') == 'update':
            reference = reference.get('value')
        # Some Gradio versions omit __type__ in update outputs.
        if isinstance(reference, dict) and 'value' in reference:
            reference = reference['value']
        if not isinstance(reference, dict) or not reference.get('path'):
            raise ValueError('音色预设没有可用参考音频')
        defaults[names.index('prompt')] = reference
        return defaults, names.index('text')

    def _download(self, value):
        while isinstance(value, dict) and 'value' in value:
            value = value['value']
        if not isinstance(value, dict):
            raise ValueError('IndexTTS 未返回音频文件')
        url = value.get('url')
        if not url and value.get('path'):
            url = self.base_url + '/gradio_api/file=' + quote(value['path'], safe=':/')
        parsed, origin = urlsplit(url or ''), urlsplit(self.base_url)
        host = '127.0.0.1' if parsed.hostname == 'localhost' else parsed.hostname
        if (parsed.scheme, host, parsed.port or 80) != (origin.scheme, origin.hostname, origin.port or 80):
            raise ValueError('IndexTTS 音频地址不属于当前服务')
        if not parsed.path.startswith('/gradio_api/file=') or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('IndexTTS 音频地址无效')
        return self._request('GET', parsed.path, limit=MAX_AUDIO_BYTES)

    def synthesize(self, text, template):
        defaults, text_index = template
        data = copy.deepcopy(defaults)
        data[text_index] = text
        result = self._call('gen_single', data)
        if len(result) != 1:
            raise ValueError('IndexTTS 生成回执无效')
        return self._download(result[0])
