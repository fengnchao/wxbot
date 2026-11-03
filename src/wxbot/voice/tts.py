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

import os
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from .policy import ContactVoiceRef, IndexTtsSettings, VoicePolicy


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

    def prepare(self, text: str = "", *, data: bytes | None = None, contact: str = "") -> TtsAudio:
        del text, contact
        if data is not None:
            return validate_wav_bytes(
                data, min_seconds=self.min_seconds, max_seconds=self.max_seconds
            )
        return load_wav_file(
            self.fixture_path,
            min_seconds=self.min_seconds,
            max_seconds=self.max_seconds,
        )


class IndexTtsSource:
    """P2 IndexTTS：按正文合成合同 WAV；无参考音/失败抛 ValueError（不得按 RALT）。"""

    def __init__(
        self,
        settings: IndexTtsSettings,
        *,
        contact_refs: dict[str, ContactVoiceRef] | None = None,
        min_seconds: float = DEFAULT_MIN_SECONDS,
        max_seconds: float = DEFAULT_MAX_SECONDS,
    ):
        self.settings = settings
        self.contact_refs = dict(contact_refs or {})
        self.min_seconds = float(min_seconds)
        self.max_seconds = float(max_seconds)

    def _resolve_ref(self, contact: str) -> tuple[Path, str, str]:
        key = str(contact or "").strip()
        ref = self.contact_refs.get(key)
        lang = self.settings.default_lang
        asset_id = ""
        path = None
        if ref is not None:
            path = ref.ref_wav
            lang = ref.lang or lang
            asset_id = ref.asset_id or ""
        if path is None:
            path = self.settings.default_ref_wav
        if path is None or not Path(path).is_file():
            raise ValueError(
                "无可用参考音：请配置 voice.contact_refs.<联系人>.ref_wav "
                "或 voice.indextts.default_ref_wav（禁止未授权克隆他人音色）"
            )
        return Path(path).resolve(), lang, asset_id

    def prepare(self, text: str = "", *, data: bytes | None = None, contact: str = "") -> TtsAudio:
        if data is not None:
            return validate_wav_bytes(
                data, min_seconds=self.min_seconds, max_seconds=self.max_seconds
            )
        body = str(text or "").strip()
        if not body:
            raise ValueError("IndexTTS 需要非空正文才能合成")
        ref_wav, lang, _asset_id = self._resolve_ref(contact)
        settings = self.settings
        if not settings.worker_script.is_file():
            raise ValueError(f"找不到 IndexTTS worker: {settings.worker_script}")
        if not settings.repo_dir.is_dir():
            raise ValueError(f"找不到 IndexTTS 仓外目录: {settings.repo_dir}")
        if not settings.model_dir.is_dir():
            raise ValueError(f"找不到 IndexTTS 权重目录: {settings.model_dir}")
        if not settings.cfg_path.is_file():
            raise ValueError(f"找不到 IndexTTS config: {settings.cfg_path}")

        fd, out_name = tempfile.mkstemp(prefix="wxbot-indextts-", suffix=".wav")
        os.close(fd)
        out_path = Path(out_name)
        try:
            cmd = [
                settings.uv_bin,
                "run",
                "--directory",
                str(settings.repo_dir),
                "python",
                str(settings.worker_script),
                "--cfg-path",
                str(settings.cfg_path),
                "--model-dir",
                str(settings.model_dir),
                "--prompt-wav",
                str(ref_wav),
                "--text",
                body,
                "--lang",
                lang,
                "--output",
                str(out_path),
                "--sample-rate",
                str(settings.sample_rate),
            ]
            if settings.use_cuda:
                cmd.append("--use-cuda")
            else:
                cmd.append("--no-cuda")
            if settings.use_bf16:
                cmd.append("--use-bf16")
            else:
                cmd.append("--no-bf16")
            try:
                completed = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=float(settings.timeout_seconds),
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ValueError(
                    f"IndexTTS 超时（>{settings.timeout_seconds}s）"
                ) from exc
            except FileNotFoundError as exc:
                raise ValueError(f"无法启动 IndexTTS（uv/python）: {exc}") from exc
            if completed.returncode != 0:
                err = (completed.stderr or completed.stdout or "").strip()
                if len(err) > 800:
                    err = err[-800:]
                raise ValueError(f"IndexTTS 进程失败(code={completed.returncode}): {err or '无输出'}")
            if not out_path.is_file():
                raise ValueError("IndexTTS 未写出输出 WAV")
            return load_wav_file(
                out_path,
                min_seconds=self.min_seconds,
                max_seconds=self.max_seconds,
            )
        finally:
            try:
                out_path.unlink(missing_ok=True)
            except OSError:
                pass


def build_tts_source(policy: VoicePolicy):
    """按 voice.tts_provider 构造可插源；fixture 可随时切回排障。"""
    if policy.tts_provider == "indextts":
        if policy.indextts is None:
            raise ValueError("tts_provider=indextts 但未加载 IndexTtsSettings")
        return IndexTtsSource(
            policy.indextts,
            contact_refs=policy.contact_refs,
            min_seconds=policy.min_seconds,
            max_seconds=policy.max_seconds,
        )
    return FixtureTtsSource(
        policy.fixture_wav,
        min_seconds=policy.min_seconds,
        max_seconds=policy.max_seconds,
    )
