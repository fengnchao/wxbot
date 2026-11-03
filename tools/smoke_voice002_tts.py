"""FEAT-VOICE-002 local smokes (no real WeChat, no unauthorized clone)."""
from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wxbot.voice.policy import load_voice_policy
from wxbot.voice.tts import (
    FixtureTtsSource,
    IndexTtsSource,
    build_tts_source,
    validate_wav_bytes,
)


def _tone_bytes(seconds=1.0, rate=16000, freq=440.0) -> bytes:
    import math
    import struct

    n = int(seconds * rate)
    frames = bytearray()
    for i in range(n):
        sample = int(16000 * math.sin(2 * math.pi * freq * (i / rate)))
        frames += struct.pack("<h", max(-32767, min(32767, sample)))
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return buf.getvalue()


def main() -> int:
    failures = []
    fixture = ROOT / "tools" / "voice-fixtures" / "p1-tone.wav"
    # 1) Fixture still works
    try:
        src = FixtureTtsSource(fixture)
        audio = src.prepare("这段正文应被忽略")
        assert audio.sample_rate in (16000, 48000)
        assert audio.channels == 1
        print("PASS fixture prepare", round(audio.duration_seconds, 3), "s")
    except Exception as exc:
        failures.append(f"fixture: {exc}")

    # 2) validate rejects bad rate
    try:
        bad = _tone_bytes(rate=22050)
        try:
            validate_wav_bytes(bad)
            failures.append("validate should reject 22050")
        except ValueError:
            print("PASS validate rejects non-contract rate")
    except Exception as exc:
        failures.append(f"validate bad rate: {exc}")

    # 3) IndexTTS without ref -> ValueError (text fallback path)
    try:
        from wxbot.voice.policy import IndexTtsSettings

        settings = IndexTtsSettings(
            repo_dir=Path(r"D:\work\tools\index-tts"),
            model_dir=Path(r"D:\work\tools\index-tts\checkpoints"),
            cfg_path=Path(r"D:\work\tools\index-tts\checkpoints\config.yaml"),
            uv_bin="uv",
            timeout_seconds=30,
            use_cuda=True,
            use_bf16=True,
            sample_rate=16000,
            default_ref_wav=None,
            default_lang="ZH",
            worker_script=ROOT / "tools" / "indextts_worker.py",
        )
        src = IndexTtsSource(settings, contact_refs={})
        try:
            src.prepare("测试无参考音应回退", contact="nobody")
            failures.append("missing ref should raise")
        except ValueError as exc:
            print("PASS no-ref raises:", str(exc)[:80])
    except Exception as exc:
        failures.append(f"no-ref: {exc}")

    # 4) policy load fixture provider
    try:
        cfg = {
            "voice": {
                "enabled": True,
                "tts_provider": "fixture",
                "fixture_wav": str(fixture),
                "contacts": {"A": "replace"},
            }
        }
        policy = load_voice_policy(cfg, root=ROOT)
        built = build_tts_source(policy)
        assert isinstance(built, FixtureTtsSource)
        print("PASS build_tts_source fixture")
    except Exception as exc:
        failures.append(f"policy fixture: {exc}")

    # 5) policy load indextts + contact_refs asset_id reserved
    try:
        cfg = {
            "voice": {
                "enabled": True,
                "tts_provider": "indextts",
                "fixture_wav": str(fixture),
                "contacts": {"A": "coexist"},
                "indextts": {
                    "repo_dir": r"D:\work\tools\index-tts",
                    "model_dir": r"D:\work\tools\index-tts\checkpoints",
                    "timeout_seconds": 120,
                },
                "contact_refs": {
                    "A": {
                        "ref_wav": "",
                        "asset_id": "future-003-id",
                        "lang": "ZH",
                    }
                },
            }
        }
        policy = load_voice_policy(cfg, root=ROOT)
        assert policy.tts_provider == "indextts"
        assert policy.contact_refs["A"].asset_id == "future-003-id"
        assert policy.contact_refs["A"].ref_wav is None
        print("PASS policy indextts + asset_id reserved")
    except Exception as exc:
        failures.append(f"policy indextts: {exc}")

    # 6) inject bytes path (simulate WAV inject without RALT)
    try:
        data = _tone_bytes(seconds=0.8)
        audio = FixtureTtsSource(fixture).prepare("", data=data)
        assert 0.4 <= audio.duration_seconds <= 60
        print("PASS bytes inject validate")
    except Exception as exc:
        failures.append(f"inject: {exc}")

    if failures:
        print("FAILS:")
        for item in failures:
            print(" -", item)
        return 1
    print("ALL SMOKES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
