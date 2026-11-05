"""聊天窗语音条会话：复用开会话/聚焦路径，长按 Right Alt + 虚拟麦灌音。"""
from __future__ import annotations

import time

import uiautomation as auto

from ..log import log
from ..voice.playback import WaveOutPlayer
from ..voice.tts import TtsAudio
from .locator import wait_until


RALT_CODE = auto.SpecialKeyNames["RALT"]


class VoiceSession:
    """step 驱动的 PTT 会话；不依赖语音气泡 UIA 确认。"""

    def __init__(
        self,
        chat,
        win,
        edit,
        audio: TtsAudio,
        *,
        playback_device: str,
        hold_padding_seconds: float = 0.3,
        clock=time.monotonic,
    ):
        self.chat = chat
        self.win = win
        self.edit = edit
        self.audio = audio
        self.playback_device = playback_device
        self.hold_padding_seconds = float(hold_padding_seconds)
        self.clock = clock
        self.state = "typing"
        self.error = ""
        self.enter_attempted = False
        self.failure_details = {}
        self.submitted_text = ""
        self.before_enter = None
        self.on_verified_draft = None
        self.mention_verified = False
        self._player: WaveOutPlayer | None = None
        self._pressed = False
        self._release_at = 0.0
        self._started = False
        self._play_at = 0.0
        self._playing = False
        self.confirm_evidence = "ptt_release"

    def close(self) -> bool:
        try:
            if self._pressed:
                auto.ReleaseKey(RALT_CODE)
                self._pressed = False
        except Exception as exc:
            self.failure_details["release_error"] = type(exc).__name__
        if self._player is not None:
            try:
                self._player.close()
            except Exception:
                pass
            self._player = None
        return True

    def _arm(self) -> None:
        if self._started:
            return
        self._started = True
        if not self.chat.target_is_current(self.win):
            self.state = "error"
            self.error = "语音发送前目标会话变化"
            self.failure_details = {"error_code": "target_changed"}
            return
        if self.before_enter is not None:
            # Reuse the text-path hook for capture/authorization without Enter.
            try:
                self.before_enter()
            except Exception as exc:
                self.state = "error"
                self.error = f"语音发送准备失败: {type(exc).__name__}"
                self.failure_details = {"error_code": "ui_error"}
                return
        try:
            self._player = WaveOutPlayer(self.audio.data, device_name=self.playback_device)
            self._player.prepare()
            self._pressed = True
            self.enter_attempted = True
            auto.PressKey(RALT_CODE)
            self._play_at = self.clock() + 0.25
            log.info(
                "[%s] 语音条 PTT 已按下 RALT，等待录音就绪（音频 %.2fs）",
                self.chat.title,
                self.audio.duration_seconds,
            )
        except Exception as exc:
            self.close()
            self.state = "error"
            self.error = f"语音条发送失败: {type(exc).__name__}: {exc}"
            self.failure_details = {"error_code": "ui_error", "phase": "voice_ptt"}

    def step(self) -> str:
        if self.state != "typing":
            return self.state
        if not self._started:
            self._arm()
            if self.state != "typing":
                return self.state
            return "typing"
        try:
            current = self.chat.target_is_current(self.win)
        except Exception:
            current = False
        if not current:
            self.close()
            self.state = 'error'
            self.error = '语音录制期间目标会话变化，结果待人工核对'
            self.failure_details = {'error_code': 'target_changed', 'phase': 'voice_ptt'}
            return self.state
        if not self._playing:
            if self.clock() < self._play_at:
                return 'typing'
            try:
                self._player.start()
                self._playing = True
                self._release_at = self.clock() + self.audio.duration_seconds + self.hold_padding_seconds
            except Exception as exc:
                self.close()
                self.state = 'error'
                self.error = f'语音灌音失败: {type(exc).__name__}'
                self.failure_details = {'error_code': 'ui_error', 'phase': 'voice_playback'}
                return self.state
        if self.clock() < self._release_at:
            return "typing"
        try:
            if self._pressed:
                auto.ReleaseKey(RALT_CODE)
                self._pressed = False
            if self._player is not None:
                self._player.wait(timeout=2.0)
                self._player.close()
                self._player = None
            self.state = "submitted"
            return self.state
        except Exception as exc:
            self.close()
            self.state = "error"
            self.error = f"松开 RALT 失败: {type(exc).__name__}"
            self.failure_details = {"error_code": "ui_error", "phase": "voice_release"}
            return self.state
