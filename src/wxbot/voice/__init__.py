"""P1/P2 可插 TTS 语音条：假音频或 IndexTTS + 虚拟麦 + Right Alt 长按。"""

from .policy import VoicePolicy, normalize_voice_mode, normalize_tts_provider
from .tts import (
    FixtureTtsSource,
    IndexTtsSource,
    TtsAudio,
    build_tts_source,
    validate_wav_bytes,
)

__all__ = [
    "VoicePolicy",
    "normalize_voice_mode",
    "normalize_tts_provider",
    "FixtureTtsSource",
    "IndexTtsSource",
    "TtsAudio",
    "build_tts_source",
    "validate_wav_bytes",
]
