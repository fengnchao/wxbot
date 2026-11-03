"""语音开关与白名单：配置文件驱动；音色资产绑定由管理台维护。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .assets import VoiceAssetStore, default_assets_dir


VOICE_MODES = ("off", "replace", "coexist")
TTS_PROVIDERS = ("fixture", "indextts")


def normalize_voice_mode(value) -> str:
    mode = str(value or "off").strip().lower()
    if mode not in VOICE_MODES:
        raise ValueError("voice mode 必须是 off/replace/coexist")
    return mode


def normalize_tts_provider(value) -> str:
    provider = str(value or "fixture").strip().lower()
    if provider not in TTS_PROVIDERS:
        raise ValueError("voice.tts_provider 必须是 fixture 或 indextts")
    return provider


def _resolve_path(value: str, *, root: Path, field_name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是路径字符串")
    path = Path(value.strip())
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


@dataclass(frozen=True)
class ContactVoiceRef:
    """按联系人参考音；asset_id 指向本地音色资产。"""

    ref_wav: Path | None
    asset_id: str = ""
    lang: str = "ZH"


@dataclass(frozen=True)
class IndexTtsSettings:
    repo_dir: Path
    model_dir: Path
    cfg_path: Path
    uv_bin: str
    timeout_seconds: float
    use_cuda: bool
    use_bf16: bool
    sample_rate: int
    default_ref_wav: Path | None
    default_lang: str
    worker_script: Path


@dataclass(frozen=True)
class VoicePolicy:
    enabled: bool
    fixture_wav: Path
    playback_device: str
    hold_padding_seconds: float
    min_seconds: float
    max_seconds: float
    contacts: dict[str, str]
    tts_provider: str = "fixture"
    indextts: IndexTtsSettings | None = None
    contact_refs: dict[str, ContactVoiceRef] = field(default_factory=dict)
    assets_dir: Path | None = None

    def mode_for(self, contact: str) -> str:
        if not self.enabled:
            return "off"
        return self.contacts.get(str(contact or "").strip(), "off")

    def allows(self, contact: str) -> bool:
        return self.mode_for(contact) in ("replace", "coexist")

    def ref_for(self, contact: str) -> ContactVoiceRef | None:
        key = str(contact or "").strip()
        if key in self.contact_refs:
            return self.contact_refs[key]
        return None

    def binding_path(self, contact: str) -> Path | None:
        """解析联系人可用参考音路径（asset_id 优先，其次显式 ref_wav）。无绑定返回 None。"""
        ref = self.ref_for(contact)
        if ref is None:
            return None
        if ref.asset_id:
            store = VoiceAssetStore(self.assets_dir or default_assets_dir(Path(".")))
            path = store.path_for(ref.asset_id)
            if path is not None and path.is_file():
                return path
        if ref.ref_wav is not None and Path(ref.ref_wav).is_file():
            return Path(ref.ref_wav).resolve()
        return None

    def has_usable_binding(self, contact: str) -> bool:
        return self.binding_path(contact) is not None

    def delivery_mode_for(self, contact: str) -> str:
        """投递用模式：需 enabled + replace/coexist + 可用绑定；否则视为 off（不改配置）。"""
        mode = self.mode_for(contact)
        if mode == "off":
            return "off"
        if not self.has_usable_binding(contact):
            return "off"
        return mode

    def queued_media_path(self) -> str:
        """入队时写入 outbox.media_path 的预置音频。

        fixture 保持 P1：写入 fixture_wav，投递时 load_wav_file。
        indextts 等投递时才合成的提供者留空，让 _prepare_voice_audio 走 prepare。
        """
        if self.tts_provider == "fixture":
            return str(self.fixture_wav)
        return ""


def resolve_queued_media_path(policy) -> str:
    """入队 media_path。有 queued_media_path 时用它；旧替身仅 fixture 写 fixture_wav。"""
    if policy is None:
        return ""
    resolver = getattr(policy, "queued_media_path", None)
    if callable(resolver):
        return str(resolver() or "")
    if getattr(policy, "tts_provider", "fixture") == "fixture":
        return str(getattr(policy, "fixture_wav", "") or "")
    return ""


def _load_indextts(section: dict, *, root: Path) -> IndexTtsSettings:
    raw = section.get("indextts") or {}
    if not isinstance(raw, dict):
        raise ValueError("voice.indextts 必须是配置表")
    repo = _resolve_path(
        str(raw.get("repo_dir", r"D:\work\tools\index-tts")),
        root=root,
        field_name="voice.indextts.repo_dir",
    )
    model = _resolve_path(
        str(raw.get("model_dir", str(repo / "checkpoints"))),
        root=root,
        field_name="voice.indextts.model_dir",
    )
    cfg = raw.get("cfg_path", str(model / "config.yaml"))
    cfg_path = _resolve_path(str(cfg), root=root, field_name="voice.indextts.cfg_path")
    uv_bin = str(raw.get("uv_bin", "uv") or "uv").strip() or "uv"
    timeout_seconds = float(raw.get("timeout_seconds", 180))
    if not 5 <= timeout_seconds <= 1800:
        raise ValueError("voice.indextts.timeout_seconds 必须在 5–1800")
    use_cuda = bool(raw.get("use_cuda", True))
    use_bf16 = bool(raw.get("use_bf16", True))
    sample_rate = int(raw.get("sample_rate", 16000))
    if sample_rate not in (16000, 48000):
        raise ValueError("voice.indextts.sample_rate 必须是 16000 或 48000")
    default_ref = raw.get("default_ref_wav") or ""
    default_ref_wav = None
    if isinstance(default_ref, str) and default_ref.strip():
        default_ref_wav = _resolve_path(
            default_ref, root=root, field_name="voice.indextts.default_ref_wav"
        )
    default_lang = str(raw.get("default_lang", "ZH") or "ZH").strip().upper() or "ZH"
    worker = raw.get("worker_script", "tools/indextts_worker.py")
    worker_script = _resolve_path(
        str(worker), root=root, field_name="voice.indextts.worker_script"
    )
    return IndexTtsSettings(
        repo_dir=repo,
        model_dir=model,
        cfg_path=cfg_path,
        uv_bin=uv_bin,
        timeout_seconds=timeout_seconds,
        use_cuda=use_cuda,
        use_bf16=use_bf16,
        sample_rate=sample_rate,
        default_ref_wav=default_ref_wav,
        default_lang=default_lang,
        worker_script=worker_script,
    )


def _load_contact_refs(section: dict, *, root: Path) -> dict[str, ContactVoiceRef]:
    raw = section.get("contact_refs") or {}
    if not isinstance(raw, dict):
        raise ValueError("voice.contact_refs 必须是表")
    out: dict[str, ContactVoiceRef] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("voice.contact_refs 键必须是联系人/会话名")
        if isinstance(value, str):
            ref_wav = _resolve_path(value, root=root, field_name=f"voice.contact_refs.{name}")
            out[name.strip()] = ContactVoiceRef(ref_wav=ref_wav)
            continue
        if not isinstance(value, dict):
            raise ValueError(f"voice.contact_refs.{name} 必须是路径或表")
        ref_raw = value.get("ref_wav") or ""
        ref_wav = None
        if isinstance(ref_raw, str) and ref_raw.strip():
            ref_wav = _resolve_path(
                ref_raw, root=root, field_name=f"voice.contact_refs.{name}.ref_wav"
            )
        asset_id = str(value.get("asset_id") or "").strip()
        lang = str(value.get("lang") or "ZH").strip().upper() or "ZH"
        out[name.strip()] = ContactVoiceRef(ref_wav=ref_wav, asset_id=asset_id, lang=lang)
    return out


def load_voice_policy(cfg: dict, *, root: Path) -> VoicePolicy:
    section = cfg.get("voice") or {}
    if not isinstance(section, dict):
        raise ValueError("voice 必须是配置表")
    enabled = bool(section.get("enabled", False))
    fixture = section.get("fixture_wav", "tools/voice-fixtures/p1-tone.wav")
    path = _resolve_path(str(fixture), root=root, field_name="voice.fixture_wav")
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
    tts_provider = normalize_tts_provider(section.get("tts_provider", "fixture"))
    indextts = None
    if tts_provider == "indextts":
        indextts = _load_indextts(section, root=root)
    contact_refs = _load_contact_refs(section, root=root)
    assets_raw = section.get("assets_dir") or "data/voice-assets"
    assets_dir = _resolve_path(str(assets_raw), root=root, field_name="voice.assets_dir")
    # 物化 asset_id → 本地文件，供 TTS 直接使用 ref_wav
    store = VoiceAssetStore(assets_dir)
    materialized: dict[str, ContactVoiceRef] = {}
    for name, ref in contact_refs.items():
        path_ref = ref.ref_wav
        if ref.asset_id:
            resolved = store.path_for(ref.asset_id)
            if resolved is not None:
                path_ref = resolved
        materialized[name] = ContactVoiceRef(
            ref_wav=path_ref, asset_id=ref.asset_id, lang=ref.lang
        )
    if enabled and tts_provider == "fixture" and not path.is_file():
        raise ValueError(f"voice.enabled 且 tts_provider=fixture 时找不到假音频: {path}")
    if enabled and tts_provider == "indextts" and indextts is None:
        raise ValueError("tts_provider=indextts 时必须配置 voice.indextts")
    return VoicePolicy(
        enabled=enabled,
        fixture_wav=path,
        playback_device=device.strip(),
        hold_padding_seconds=padding,
        min_seconds=min_seconds,
        max_seconds=max_seconds,
        contacts=contacts,
        tts_provider=tts_provider,
        indextts=indextts,
        contact_refs=materialized,
        assets_dir=assets_dir,
    )

