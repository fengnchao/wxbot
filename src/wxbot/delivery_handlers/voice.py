"""Voice preparation, authorization, PTT confirmation and one-time text fallback."""
from .base import ActiveDelivery, DeliveryHandler
from ..log import log


class VoiceDeliveryHandler(DeliveryHandler):
    def __init__(self, pump):
        super().__init__(pump)
        self._voice_preparing = None
        self._webui_deliveries = set()

    @property
    def preparing(self):
        return self._voice_preparing is not None

    def close(self):
        if self._voice_preparing is not None:
            self._voice_preparing[1].cancel()
            self._voice_preparing = None
        self._webui_deliveries.clear()

    def current_policy(self):
        return self.pump.voice_policy_loader() if self.pump.voice_policy_loader else self.pump.voice_policy

    def mode_for(self, contact):
        policy = self.current_policy()
        if policy is None:
            return "off"
        return policy.mode_for(contact)

    def _queued_voice_mode(self, delivery):
        # Automatic coexist rows follow their text parts. Preserve the queued
        # decision when settings change before recording or before a failure.
        if delivery.batch_id:
            return 'coexist' if delivery.part_count > 1 else 'replace'
        return self.mode_for(delivery.contact)

    def _voice_allowed(self, delivery):
        policy = self.current_policy()
        if policy is None or policy.mode_for(delivery.contact) == 'off':
            return False
        if getattr(delivery, 'package_id', None) and getattr(delivery, 'media_id', ''):
            return True
        has_binding = getattr(policy, 'has_usable_binding', None)
        return not callable(has_binding) or has_binding(delivery.contact)

    def _voice_audio_allowed(self, delivery, audio):
        if not self._voice_allowed(delivery):
            return False
        preset = getattr(audio, 'source_preset', '')
        if not preset:
            return True
        policy = self.current_policy()
        if getattr(policy, 'tts_provider', '') != 'webui' or policy.webui_presets_path is None:
            return False
        from butler.delivery.tts_presets import PresetBindings
        try:
            return PresetBindings(policy.webui_presets_path).get(delivery.contact) == preset
        except (OSError, ValueError):
            return False

    def _voice_text_fallback(self, delivery, state, error):
        """replace 失败回退文字一次；coexist 不因语音失败重发已有文字。"""
        if getattr(delivery, 'package_id', None):
            return  # Explicit preset voice packages stop as a unit, without duplicate text.
        mode = self._queued_voice_mode(delivery)
        if mode != "replace":
            return
        text = (delivery.text or "").strip()
        if not text:
            log.warning("[语音回退][%s][%s] replace 失败但无正文可回退: %s", delivery.contact, delivery.id, error or state)
            return
        try:
            record_id = self.pump.store.enqueue_delivery(delivery.contact, text, now=self.pump.clock())
            log.warning("[语音回退][%s][%s] 语音失败(%s)→已回退文字 %s", delivery.contact, delivery.id, state, record_id)
        except Exception as exc:
            log.error("[语音回退][%s][%s] 回退文字入库失败: %s", delivery.contact, delivery.id, type(exc).__name__)

    def _prepare_voice_audio(self, delivery, policy=None):
        from ..voice.tts import build_tts_source, load_wav_file

        policy = policy if policy is not None else self.current_policy()
        media_path = getattr(delivery, "media_path", "") or ""
        if self._webui_needs_synthesis(delivery, policy):
            media_path = ''
        if media_path:
            return load_wav_file(media_path,
                min_seconds=getattr(policy, "min_seconds", 0.4),
                max_seconds=getattr(policy, "max_seconds", 60))
        source = self.pump.tts_source
        if source is None and policy is not None:
            source = build_tts_source(policy)
        if source is None:
            raise ValueError("未配置 TTS/假音频源")
        return source.prepare(
            delivery.text or "",
            contact=getattr(delivery, "contact", "") or "",
        )

    @staticmethod
    def _webui_needs_synthesis(delivery, policy):
        if getattr(policy, 'tts_provider', '') != 'webui' or getattr(delivery, 'package_id', None):
            return False
        media = getattr(delivery, 'media_path', '')
        if not media:
            return True
        # Old automatically queued test tones must not survive an implicit
        # migration to real speech. Explicit authenticated packages are exempt.
        from pathlib import Path
        return Path(media).resolve() == Path(policy.fixture_wav).resolve()

    def _prepare_voice_in_background(self, delivery, policy):
        from concurrent.futures import Future
        import threading
        future = Future()
        self._webui_deliveries.add(delivery.id)
        self._voice_preparing = (delivery, future)
        def prepare():
            if not future.set_running_or_notify_cancel():
                return
            try:
                audio = self._prepare_voice_audio(delivery, policy)
            except BaseException as exc:
                future.set_exception(exc)
            else:
                future.set_result(audio)
        threading.Thread(target=prepare, name='wxbot-webui-tts', daemon=True).start()

    def _fail_voice_preparation(self, delivery, exc):
        # No PTT occurred. Finish this original row before queuing the one-time
        # fallback, so the generic blocked-delivery recovery cannot synthesize
        # again or duplicate the fallback after an unknown WebUI result.
        error = f'TTS/音频准备失败: {type(exc).__name__}: {exc}'
        self.pump._finish(delivery, 'blocked', error,
                     {'error_code': 'ui_error', 'phase': 'voice_audio', 'retry_safe': False})

    def start(self, delivery, prepared_audio=None):
        chat = None
        try:
            policy = self.current_policy()
            if not self._voice_allowed(delivery):
                # 非白名单/关开关/无绑定：不按 RALT，直接回退文字路径。
                text = (delivery.text or "").strip()
                if text and self._queued_voice_mode(delivery) != 'coexist':
                    self.pump.store.enqueue_delivery(delivery.contact, text, now=self.pump.clock())
                    self.pump._finish(delivery, "skipped", "语音开关关闭，已改走文字")
                elif text:
                    self.pump._finish(delivery, 'skipped', '语音开关关闭，保留已有文字')
                else:
                    self.pump._finish(delivery, "blocked", "语音开关关闭且无文字可回退",
                                 {"error_code": "ui_error", "phase": "voice_disabled"})
                return
            if prepared_audio is None and self._webui_needs_synthesis(delivery, policy):
                self._prepare_voice_in_background(delivery, policy)
                return
            self.pump.discover()
            chat = self.pump.get_chat(delivery.contact)
            if delivery.group_mode is not None:
                chat.expected_group = delivery.group_mode
            if not self.pump.capture_target(delivery.contact):
                self.pump._finish(delivery, "blocked", "目标会话尚不可用，未发语音条",
                             self.pump._diagnostics(chat, "prepare_target", "target_unavailable"))
                return
            try:
                audio = prepared_audio if prepared_audio is not None else self._prepare_voice_audio(delivery, policy)
            except Exception as exc:
                self.pump._finish(delivery, "blocked", f"TTS/音频准备失败: {type(exc).__name__}: {exc}",
                             {"error_code": "ui_error", "phase": "voice_audio"})
                return
            if not self._voice_audio_allowed(delivery, audio):
                self.pump._finish(delivery, 'blocked', '语音设置已更改，停止录音',
                             {'error_code': 'ui_error', 'phase': 'voice_disabled'})
                return
            policy = self.current_policy()
            device = getattr(policy, "playback_device", "CABLE Input") if policy else "CABLE Input"
            padding = getattr(policy, "hold_padding_seconds", 0.3) if policy else 0.3
            typing = chat.start_voice(
                audio,
                playback_device=device,
                hold_padding_seconds=padding,
                clock=self.pump.monotonic,
            )
            if typing is None:
                code = "draft_conflict" if getattr(chat, "draft_conflict", False) else "target_unavailable"
                details = self.pump._diagnostics(chat, "prepare_input", code)
                self.pump._finish(delivery, "blocked", "无法聚焦会话输入区，未按 RALT", details)
                return
            # 语音条确认不依赖默认 UIA 气泡；不做 baseline 气泡核验。
            active = ActiveDelivery(delivery, chat, typing, [])
            typing.before_enter = lambda: self.before_enter(active, audio)
            self.pump.active = active
            log.info("[队列][%s][%s][%d/%d] 开始语音条 PTT（Right Alt）", delivery.contact, delivery.id,
                     delivery.part_seq, delivery.part_count)
        except Exception as exc:
            self.pump._finish(delivery, "blocked", f"语音发送准备失败: {type(exc).__name__}",
                         self.pump._diagnostics(chat, "prepare", "ui_error"))

    def before_enter(self, active, audio=None):
        if self.pump._closed or not self._voice_audio_allowed(active.delivery, audio):
            raise PermissionError('语音开关或当前会话音色绑定已撤销')
        if not active.chat.target_is_current(active.typing.win):
            raise RuntimeError("语音发送前目标会话变化")

    def poll(self):
        if self._voice_preparing is None:
            return False
        delivery, future = self._voice_preparing
        if not future.done():
            return True
        self._voice_preparing = None
        row = self.pump.store.get_delivery(delivery.id)
        if row is None or row['state'] != 'sending':
            self._webui_deliveries.discard(delivery.id)
            return True  # Deleted/skipped work never records after synthesis.
        try:
            audio = future.result()
        except Exception as exc:
            self._fail_voice_preparation(delivery, exc)
            return True
        self.start(delivery, prepared_audio=audio)
        return True

    def complete(self, active, state):
        if state == "submitted":
            details = {
                "bubble_verified": False,
                "confirm_evidence": getattr(active.typing, "confirm_evidence", "ptt_release"),
                "human_confirm_required": True,
                "voice_mode": self.mode_for(active.delivery.contact),
            }
            self.pump._finish(active.delivery, "sent", details=details)
        else:
            details = dict(getattr(active.typing, "failure_details", {}) or {})
            details.setdefault("error_code", "ui_error")
            details["phase"] = details.get("phase") or "voice_ptt"
            self.pump._finish(active.delivery, "uncertain" if active.typing.enter_attempted else "blocked",
                         active.typing.error or state, details)
        return

    def prepare_finish(self, delivery, state, details):
        if (state == 'blocked' and not details.get('enter_attempted')
                and not getattr(delivery, 'package_id', None)
                and (delivery.id in self._webui_deliveries
                     or getattr(self.current_policy(), 'tts_provider', '') == 'webui')):
            # Never synthesize an automatic reply again after queuing its fallback.
            details.update(retry_safe=False, retry='never')
            return 'skipped'
        return state

    def after_finish(self, delivery, state, error, original_state):
        if original_state in {'blocked', 'uncertain'}:
            self._voice_text_fallback(delivery, state, error)
        self._webui_deliveries.discard(delivery.id)
