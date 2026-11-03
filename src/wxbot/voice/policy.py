"""语音开关与白名单：配置文件驱动（AC-10），无管理台 UI。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


VOICE_MODES = ("off", "replace", "coexist")


def normalize_voice_mode(value) -> str:
    mode = str(value or "off").strip().lower()
    if mode not in VOICE_MODES:
        raise ValueError("voice mode 必须是 off/replace/coexist")
    return mode


@dataclass(frozen=True)
class VoicePolicy:
    enabled: bool
    fixture_wav: Path
    playback_device: str
    hold_padding_seconds: float
    min_seconds: float
    max_seconds: float
    contacts: dict[str, str]

    def mode_for(self, contact: str) -> str:
        if not self.enabled:
            return "off"
        return self.contacts.get(str(contact or "").strip(), "off")

    def allows(self, contact: str) -> bool:
        return self.mode_for(contact) in ("replace", "coexist")


def load_voice_policy(cfg: dict, *, root: Path) -> VoicePolicy:
    section = cfg.get("voice") or {}
    if not isinstance(section, dict):
        raise ValueError("voice 必须是配置表")
    enabled = bool(section.get("enabled", False))
    fixture = section.get("fixture_wav", "tools/voice-fixtures/p1-tone.wav")
    if not isinstance(fixture, str) or not fixture.strip():
        raise ValueError("voice.fixture_wav 必须是路径字符串")
    path = Path(fixture)
    if not path.is_absolute():
        path = (root / path).resolve()
    device = section.get("playback_device", "CABLE Input")
    if not isinstance(device, str) or not device.strip():
        raise ValueError("voice.playback_device 必须是设备名子串")
    padding = float(section.get("hold_padding_seconds", 0.3))
    if not 0 <= padding <= 5:
        raise ValueError("voice.hold_padding_seconds 必须在 0–5")
    min_seconds = float(section.get("min_seconds", 0.4))
    max_seconds = float(section.get("max_seconds", 60))
    if not 0.1 <= min_seconds <= max_seconds <= 120:
        raise ValueError("voice.min/max_seconds 非法")
    raw_contacts = section.get("contacts") or {}
    if not isinstance(raw_contacts, dict):
        raise ValueError("voice.contacts 必须是表")
    contacts = {}
    for name, mode in raw_contacts.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("voice.contacts 键必须是联系人/会话名")
        contacts[name.strip()] = normalize_voice_mode(mode)
    if enabled and not path.is_file():
        raise ValueError(f"voice.enabled 时找不到假音频: {path}")
    return VoicePolicy(
        enabled=enabled,
        fixture_wav=path,
        playback_device=device.strip(),
        hold_padding_seconds=padding,
        min_seconds=min_seconds,
        max_seconds=max_seconds,
        contacts=contacts,
    )
