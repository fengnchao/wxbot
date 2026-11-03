"""IndexTTS must not enqueue the P1 fixture WAV.

tts_provider=fixture still stores fixture_wav on the voice outbox row.
Any other provider leaves media_path empty so delivery calls source.prepare.
No usable binding still means text only (FEAT-VOICE-003). No WeChat send.
"""
from __future__ import annotations

import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Offline smoke: delivery imports the WeChat UI stack. Stub it so this
# process never touches a desktop. The assertions call queue + prepare only.
import types


class _LazyModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = type(name, (), {})
        setattr(self, name, value)
        return value


_auto = _LazyModule("uiautomation")
sys.modules["uiautomation"] = _auto
_pil = _LazyModule("PIL")
for _name in ("Image", "ImageChops", "ImageGrab"):
    _sub = _LazyModule(f"PIL.{_name}")
    sys.modules[f"PIL.{_name}"] = _sub
    setattr(_pil, _name, _sub)
sys.modules["PIL"] = _pil

from wxbot.delivery import DeliveryPump
from wxbot.queue_store import Incoming, QueueStore
from wxbot.queue_worker import ModelWorker
from wxbot.reply import Reply
from wxbot.voice.assets import VoiceAssetStore
from wxbot.voice.policy import load_voice_policy, resolve_queued_media_path
from wxbot.voice.tts import FixtureTtsSource


FIXTURE = ROOT / "tools" / "voice-fixtures" / "p1-tone.wav"


def _tone_bytes(seconds=1.0, rate=16000) -> bytes:
    import io
    import math
    import struct

    frames = bytearray()
    n = int(seconds * rate)
    for i in range(n):
        sample = int(8000 * math.sin(2 * math.pi * 440.0 * (i / rate)))
        frames += struct.pack("<h", max(-32767, min(32767, sample)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return buf.getvalue()


class _Router:
    def __init__(self, reply: Reply):
        self.reply = reply

    def handle_reply(self, contact, text, **kwargs):
        del contact, text, kwargs
        return self.reply


class _Recorder:
    def __init__(self):
        self.calls = []

    def prepare(self, text="", *, data=None, contact=""):
        self.calls.append({"text": text, "contact": contact, "data": data})
        return FixtureTtsSource(FIXTURE).prepare("")


class _Outbound:
    def __init__(self, contact, text):
        self.contact = contact
        self.text = text
        self.kind = "voice"
        self.received_at = None

    def finish(self, ok, detail=""):
        raise AssertionError(f"enqueue failed: {ok} {detail}")


def _policy(provider: str, *, assets_dir: Path, asset_id: str = "", bind: bool = True):
    voice = {
        "enabled": True,
        "tts_provider": provider,
        "fixture_wav": str(FIXTURE),
        "assets_dir": str(assets_dir),
        "contacts": {"Ada": "replace", "Bea": "coexist"},
    }
    if provider == "indextts":
        voice["indextts"] = {
            "repo_dir": str(ROOT / "tools"),
            "model_dir": str(ROOT / "tools"),
            "timeout_seconds": 30,
            "worker_script": str(ROOT / "tools" / "indextts_worker.py"),
        }
    if bind:
        voice["contact_refs"] = {
            "Ada": {"asset_id": asset_id, "lang": "ZH"},
            "Bea": {"asset_id": asset_id, "lang": "ZH"},
        }
    return load_voice_policy({"voice": voice}, root=ROOT)


def _rows(store: QueueStore):
    return [
        dict(row)
        for row in store._db.execute(
            "SELECT kind, media_path, text, contact FROM outbox ORDER BY seq"
        )
    ]


def _run_worker(policy, contact, reply: Reply):
    store = QueueStore(":memory:")
    try:
        store.capture(contact, [], [Incoming(text="你好")], now=1.0)
        worker = ModelWorker(
            store,
            _Router(reply),
            quiet=0,
            max_wait=30,
            reply_delay_min=0,
            reply_delay_max=0,
            clock=lambda: 100.0,
            typing_mode="chunked",
            voice_policy=policy,
        )
        if worker.process_once() is not True:
            raise AssertionError("worker did not finish a batch")
        return store, _rows(store)
    except Exception:
        store.close()
        raise


def _prepare_voices(store, policy, source):
    pump = DeliveryPump(
        store,
        lambda contact: None,
        lambda contact: False,
        lambda: None,
        clock=lambda: 100.0,
        voice_policy=policy,
        tts_source=source,
    )
    prepared = []
    while True:
        delivery = store.claim_delivery(now=100.0)
        if delivery is None:
            break
        if delivery.kind != "voice":
            store.finish_delivery(delivery.id, "skipped", now=100.0)
            continue
        prepared.append((delivery, pump._prepare_voice_audio(delivery)))
    return prepared


def main() -> int:
    failures = []
    if not FIXTURE.is_file():
        print("FAIL missing fixture", FIXTURE)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        assets_dir = Path(tmp) / "voice-assets"
        asset = VoiceAssetStore(assets_dir).register(name="smoke-ref", data=_tone_bytes())
        try:
            bound = {
                "indextts": _policy("indextts", assets_dir=assets_dir, asset_id=asset.id, bind=True),
                "fixture": _policy("fixture", assets_dir=assets_dir, asset_id=asset.id, bind=True),
            }
            unbound = _policy("indextts", assets_dir=assets_dir, bind=False)
        except Exception as exc:
            print("FAIL policy:", exc)
            return 1

        # Direct resolver: fixture path vs empty.
        try:
            assert bound["fixture"].queued_media_path() == str(bound["fixture"].fixture_wav)
            assert bound["indextts"].queued_media_path() == ""
            assert resolve_queued_media_path(bound["indextts"]) == ""
            assert resolve_queued_media_path(bound["fixture"]) == str(bound["fixture"].fixture_wav)
            assert bound["indextts"].has_usable_binding("Ada") is True
            assert unbound.has_usable_binding("Ada") is False
            assert unbound.delivery_mode_for("Ada") == "off"
            print("PASS resolver fixture path / indextts empty / unbound off")
        except Exception as exc:
            failures.append(f"resolver: {exc}")

        # Model queue, replace + usable asset_id.
        for provider, expect_media in (
            ("indextts", ""),
            ("fixture", str(bound["fixture"].fixture_wav)),
        ):
            store = None
            try:
                store, rows = _run_worker(
                    bound[provider], "Ada", Reply.from_text("合成这段话")
                )
                assert len(rows) == 1, rows
                assert rows[0]["kind"] == "voice", rows
                assert rows[0]["media_path"] == expect_media, rows
                recorder = _Recorder()
                prepared = _prepare_voices(store, bound[provider], recorder)
                assert len(prepared) == 1
                delivery, audio = prepared[0]
                if provider == "indextts":
                    assert recorder.calls == [{"text": "合成这段话", "contact": "Ada", "data": None}]
                    assert delivery.media_path == ""
                else:
                    assert recorder.calls == []
                    assert audio.path == bound["fixture"].fixture_wav.resolve()
                print(f"PASS worker replace {provider} media={rows[0]['media_path']!r} prepare_calls={len(recorder.calls)}")
            except Exception as exc:
                failures.append(f"worker {provider}: {exc}")
            finally:
                if store is not None:
                    store.close()

        # coexist uses the same media decision.
        store = None
        try:
            store, rows = _run_worker(
                bound["indextts"], "Bea", Reply("甲乙", ("甲", "乙"))
            )
            kinds = [row["kind"] for row in rows]
            assert kinds == ["text", "text", "voice"], rows
            voice = rows[-1]
            assert voice["media_path"] == ""
            recorder = _Recorder()
            prepared = _prepare_voices(store, bound["indextts"], recorder)
            assert len(prepared) == 1
            assert recorder.calls[0]["contact"] == "Bea"
            assert recorder.calls[0]["text"] == "甲乙"
            print("PASS worker coexist indextts media empty and prepare called")
        except Exception as exc:
            failures.append(f"coexist: {exc}")
        finally:
            if store is not None:
                store.close()

        # Binding gate: replace configured, no usable asset → text only, no prepare.
        store = None
        try:
            store, rows = _run_worker(unbound, "Ada", Reply.from_text("只回文字"))
            assert rows and all(row["kind"] == "text" for row in rows), rows
            assert all(row["media_path"] == "" for row in rows), rows
            recorder = _Recorder()
            prepared = _prepare_voices(store, unbound, recorder)
            assert prepared == []
            assert recorder.calls == []
            print("PASS unbound indextts stays text; prepare not called")
        except Exception as exc:
            failures.append(f"unbound: {exc}")
        finally:
            if store is not None:
                store.close()

        # Outbound /send voice=true goes through DeliveryPump.enqueue.
        for provider, expect_media in (
            ("indextts", ""),
            ("fixture", str(bound["fixture"].fixture_wav)),
        ):
            store = QueueStore(":memory:")
            try:
                pump = DeliveryPump(
                    store,
                    lambda contact: None,
                    lambda contact: False,
                    lambda: None,
                    clock=lambda: 50.0,
                    voice_policy=bound[provider],
                    tts_source=_Recorder(),
                )
                pump.enqueue(_Outbound("Ada", "外发正文"))
                rows = _rows(store)
                assert len(rows) == 1 and rows[0]["kind"] == "voice", rows
                assert rows[0]["media_path"] == expect_media, rows
                delivery = store.claim_delivery(now=50.0)
                audio = pump._prepare_voice_audio(delivery)
                if provider == "indextts":
                    assert pump.tts_source.calls and pump.tts_source.calls[0]["text"] == "外发正文"
                else:
                    assert pump.tts_source.calls == []
                    assert audio.path == bound["fixture"].fixture_wav.resolve()
                print(f"PASS outbound {provider} media={rows[0]['media_path']!r}")
            except Exception as exc:
                failures.append(f"outbound {provider}: {exc}")
            finally:
                store.close()

    if failures:
        print("FAILS:")
        for item in failures:
            print(" -", item)
        return 1
    print("ALL SMOKES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
