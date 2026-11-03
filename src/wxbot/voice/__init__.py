"""P1/P2/P3 可插 TTS 语音条：假音频或 IndexTTS + 音色资产绑定 + 虚拟麦 + Right Alt 长按。"""

from .policy import VoicePolicy, normalize_voice_mode, normalize_tts_provider
from .assets import VoiceAssetStore, MAX_UPLOAD_BYTES
from .tts import (
    TtsAudio,
    FixtureTtsSource,
    IndexTtsSource,
    build_tts_source,
    load_wav_file,
    validate_wav_bytes,
)

__all__ = [
    "VoicePolicy",
    "normalize_voice_mode",
    "normalize_tts_provider",
    "VoiceAssetStore",
    "MAX_UPLOAD_BYTES",
    "TtsAudio",
    "FixtureTtsSource",
    "IndexTtsSource",
    "build_tts_source",
    "load_wav_file",
    "validate_wav_bytes",
]
