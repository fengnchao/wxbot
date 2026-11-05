"""Automatic reply synthesis; the delivery queue remains owned by wxbot.

Administrator voice settings authorize this path. It does not execute model
tools, register tool operations, or submit another delivery package.
"""
from io import BytesIO
import os
from pathlib import Path
import tomllib
import wave

from common.voice_audio import prepare_voice_parts, split_text
from .gradio_tts import GradioTtsClient
from .tts_presets import PresetBindings


def preset_bindings_path(config_dir):
    """Resolve this installation's Butler data directory without opening a DB."""
    config_path = Path(os.environ.get('BUTLER_CONFIG') or Path(config_dir) / 'config.butler.toml').resolve()
    raw = {}
    if config_path.is_file():
        with config_path.open('rb') as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError('Butler 配置超过大小上限')
        raw = tomllib.loads(data.decode('utf-8-sig'))
    directory = Path(raw.get('agent', {}).get('data_dir') or 'data')
    if not directory.is_absolute():
        directory = config_path.parent / directory
    return directory.resolve() / 'tts-presets.json'


class AutomaticReplyTts:
    def __init__(self, bindings_path, *, client=None):
        self.client = client or GradioTtsClient()
        self.bindings = PresetBindings(bindings_path, client=self.client)

    def synthesize(self, text, contact, *, max_seconds=60, expected_preset=None):
        chunks = split_text(text)
        preset = self.bindings.get(contact)
        if not preset:
            raise ValueError('当前会话未绑定网页音色预设')
        if expected_preset is not None and preset != expected_preset:
            raise PermissionError('当前会话网页音色预设已更改，停止本次语音')
        template = self.client.prepare(preset)
        pcm = bytearray()
        for chunk in chunks:
            for part in prepare_voice_parts(self.client.synthesize(chunk, template)):
                with wave.open(BytesIO(part), 'rb') as stream:
                    pcm.extend(stream.readframes(stream.getnframes()))
                if len(pcm) > max_seconds * 16000 * 2:
                    raise ValueError('自动回复语音超过单条时长上限')
        if self.bindings.get(contact) != preset:
            raise PermissionError('当前会话网页音色预设已更改，停止本次语音')
        output = BytesIO()
        with wave.open(output, 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(pcm)
        return output.getvalue()
