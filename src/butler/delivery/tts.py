"""Authorized, idempotent speech generation and submission to wxbot."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import uuid

from common.media_bundle import validate_media_id
from common.voice_audio import prepare_voice_parts, split_text, validate_voice_wav
from .gradio_tts import GradioTtsClient
from .tts_presets import PresetBindings


class AudioStore:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def put(self, owner, data):
        validate_voice_wav(data)
        owner_hash = hashlib.sha256(owner.encode()).hexdigest()
        # IDs include no identity or source path; files remain owner-partitioned.
        media_id = uuid.uuid4().hex
        directory = self.root / owner_hash
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink() or directory.resolve().parent != self.root:
            raise ValueError('无效音频存储目录')
        target = directory / (media_id + '.wav')
        with target.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return media_id

    def read(self, media_id):
        validate_media_id(media_id)
        matches = list(self.root.glob('*/' + media_id + '.wav'))
        if len(matches) != 1:
            raise FileNotFoundError('音频不存在')
        target = matches[0]
        if target.is_symlink() or target.parent.is_symlink() or not target.resolve().is_relative_to(self.root):
            raise ValueError('无效音频位置')
        if target.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('音频过大')
        data = target.read_bytes()
        validate_voice_wav(data)
        return data


class TTSService:
    def __init__(self, store, audio, *, client=None, deliver=None, bindings=None):
        self.store, self.audio = store, audio
        self.client = client or GradioTtsClient()
        self.bindings = bindings or PresetBindings(audio.root.parent / 'tts-presets.json', client=self.client)
        self.deliver = deliver
        self._lock = threading.Lock()

    def presets(self, contact=''):
        return {'presets': self.client.presets(), 'default_preset': self.bindings.get(contact)}

    def generate(self, context, text, preset, call_id, *, authorize=None):
        if not call_id:
            raise ValueError('Write tools require a call id')
        chunks = split_text(text)
        if not isinstance(preset, str) or len(preset) > 256:
            raise ValueError('音色预设名称无效')
        requested_preset = preset
        if self.deliver is None:
            raise ValueError('语音投递服务未配置')
        fingerprint = hashlib.sha256(json.dumps(['tts_generate', text, requested_preset], ensure_ascii=False).encode()).hexdigest()
        key = (context['owner'], context['request_id'], str(call_id))
        result = {'status': 'generating', 'operation_id': uuid.uuid4().hex, 'preset': preset}
        with self.store.transaction() as db:
            old = db.execute('SELECT fingerprint,result FROM operations WHERE owner=? AND request_id=? AND call_id=?', key).fetchone()
            if old:
                if old['fingerprint'] != fingerprint:
                    raise ValueError('Tool call id reused with different arguments')
                return json.loads(old['result'])
            duplicate = db.execute('SELECT result FROM operations WHERE owner=? AND request_id=? AND fingerprint=? LIMIT 1',
                                   (*key[:2], fingerprint)).fetchone()
            if duplicate:
                db.execute('INSERT INTO operations VALUES(?,?,?,?,?)',
                           (*key, fingerprint, duplicate['result']))
                return json.loads(duplicate['result'])
            db.execute('INSERT INTO operations VALUES(?,?,?,?,?)', (*key, fingerprint, json.dumps(result)))
        submitting = False
        try:
            started = time.monotonic()
            with self._lock:
                if authorize:
                    authorize()
                preset = requested_preset or self.bindings.get(context['contact'])
                if not preset.strip():
                    raise ValueError('请指定音色预设，或先在联系人配置中选择默认网页预设')
                result['preset'] = preset
                template = self.client.prepare(preset)
                items = []
                for chunk in chunks:
                    if time.monotonic() - started > 600:
                        raise TimeoutError('语音生成超时')
                    for data in prepare_voice_parts(self.client.synthesize(chunk, template)):
                        if len(items) >= 50:
                            raise ValueError('分段后超过 50 条语音，请缩短文字')
                        media_id = self.audio.put(context['owner'], data)
                        items.append({'kind': 'voice', 'media_id': media_id})
                if authorize:
                    authorize()
                submitting = True
                receipt = self.deliver(context['contact'], items, 'tts:' + result['operation_id'])
                if receipt.get('status') not in ('queued', 'failed', 'delivery_unknown'):
                    raise ValueError('语音入队回执无效')
                result.update(receipt, parts=len(items))
        except Exception as exc:
            result.update(status='delivery_unknown' if submitting else 'failed',
                          detail=('语音投递结果未知，请人工核对，勿自动重发' if submitting else
                                  '生成或授权校验失败：' + (str(exc) if isinstance(exc, (ValueError, PermissionError)) else type(exc).__name__)))
        with self.store.transaction() as db:
            db.execute('UPDATE operations SET result=? WHERE owner=? AND request_id=? AND fingerprint=?',
                       (json.dumps(result, ensure_ascii=False), *key[:2], fingerprint))
        return result
