"""可插 TTS 输入合同（P1）：只消费已就绪的 WAV，不绑定厂商。

合同（P1 定稿）：
- 容器：RIFF/WAVE
- 编码：PCM（format=1）
- 声道：1（mono）
- 采样率：16000 或 48000
- 位深：16-bit
- 时长：0.4s–60s（可配置上下限）
- 输入：文件路径或原始 bytes；同步准备
- 非法输入：抛 ValueError；调用方不得按 RALT，应回退文字
"""
from __future__ import annotations

import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path


ALLOWED_RATES = (16000, 48000)
DEFAULT_MIN_SECONDS = 0.4
DEFAULT_MAX_SECONDS = 60.0


@dataclass(frozen=True)
class TtsAudio:
    path: Path | None
    data: bytes
    sample_rate: int
    channels: int
    sample_width: int
    duration_seconds: float


def validate_wav_bytes(
    data: bytes,
    *,
    min_seconds: float = DEFAULT_MIN_SECONDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> TtsAudio:
    if not isinstance(data, (bytes, bytearray)) or len(data) < 44:
        raise ValueError("TTS 音频过短或不是字节")
    try:
        with wave.open(BytesIO(data), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frame_count = handle.getnframes()
            comp = handle.getcomptype()
            payload = handle.readframes(frame_count)
    except wave.Error as exc:
        raise ValueError("TTS 音频不是有效 WAV") from exc
    if comp not in ("NONE", "not compressed"):
        raise ValueError("TTS 音频必须是未压缩 PCM WAV")
    if channels != 1:
        raise ValueError("TTS 音频必须是单声道")
    if sample_width != 2:
        raise ValueError("TTS 音频必须是 16-bit PCM")
    if sample_rate not in ALLOWED_RATES:
        raise ValueError("TTS 采样率仅支持 16000 或 48000")
    if sample_rate <= 0 or frame_count <= 0:
        raise ValueError("TTS 音频时长无效")
    duration = frame_count / float(sample_rate)
    if duration < float(min_seconds) or duration > float(max_seconds):
        raise ValueError("TTS 音频时长超出合同上下限")
    out = BytesIO()
    with wave.open(out, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(payload)
    return TtsAudio(None, out.getvalue(), sample_rate, 1, 2, duration)


def load_wav_file(
    path: str | Path,
    *,
    min_seconds=DEFAULT_MIN_SECONDS,
    max_seconds=DEFAULT_MAX_SECONDS,
) -> TtsAudio:
    target = Path(path)
    if not target.is_file():
        raise ValueError("TTS 音频文件不存在")
    data = target.read_bytes()
    audio = validate_wav_bytes(data, min_seconds=min_seconds, max_seconds=max_seconds)
    return TtsAudio(
        target.resolve(),
        audio.data,
        audio.sample_rate,
        audio.channels,
        audio.sample_width,
        audio.duration_seconds,
    )


class FixtureTtsSource:
    """P1 假 TTS：忽略正文，始终返回配置的固定测试 WAV。"""

    def __init__(
        self,
        fixture_path: str | Path,
        *,
        min_seconds=DEFAULT_MIN_SECONDS,
        max_seconds=DEFAULT_MAX_SECONDS,
    ):
        self.fixture_path = Path(fixture_path)
        self.min_seconds = float(min_seconds)
        self.max_seconds = float(max_seconds)

    def prepare(self, text: str = "", *, data: bytes | None = None) -> TtsAudio:
        if data is not None:
            return validate_wav_bytes(
                data, min_seconds=self.min_seconds, max_seconds=self.max_seconds
            )
        return load_wav_file(
            self.fixture_path,
            min_seconds=self.min_seconds,
            max_seconds=self.max_seconds,
        )
