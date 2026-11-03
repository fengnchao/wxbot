"""本地音色资产库：参考音文件 + manifest（不进 git）。

注册 = 保存参考 WAV 并记入清单（zero-shot 参考，不是训练/微调）。
"""
from __future__ import annotations

import json
import re
import secrets
import time
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

ASSET_ID_RE = re.compile(r"^va_[a-f0-9]{12}$")
DEFAULT_REL_DIR = Path("data") / "voice-assets"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MiB raw WAV
ALLOWED_SUFFIXES = (".wav",)
MIN_REF_SECONDS = 0.5
MAX_REF_SECONDS = 60.0


@dataclass(frozen=True)
class VoiceAsset:
    id: str
    name: str
    filename: str
    created_at: float
    updated_at: float
    size: int
    sample_rate: int = 0
    duration_seconds: float = 0.0

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "filename": self.filename,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "size": self.size,
            "sample_rate": self.sample_rate,
            "duration_seconds": self.duration_seconds,
        }


def _new_id() -> str:
    return "va_" + secrets.token_hex(6)


def _validate_wav(data: bytes) -> tuple[int, float]:
    if not isinstance(data, (bytes, bytearray)) or len(data) < 44:
        raise ValueError("参考音过短或不是有效文件")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"参考音不能超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB")
    try:
        with wave.open(BytesIO(data), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frames = handle.getnframes()
            comp = handle.getcomptype()
    except wave.Error as exc:
        raise ValueError("参考音必须是有效 WAV") from exc
    if comp not in ("NONE", "not compressed"):
        raise ValueError("参考音必须是未压缩 PCM WAV")
    if channels not in (1, 2):
        raise ValueError("参考音声道数无效")
    if sample_width != 2:
        raise ValueError("参考音必须是 16-bit PCM")
    if sample_rate <= 0 or frames <= 0:
        raise ValueError("参考音时长无效")
    duration = frames / float(sample_rate)
    if duration < MIN_REF_SECONDS or duration > MAX_REF_SECONDS:
        raise ValueError(f"参考音时长须在 {MIN_REF_SECONDS}–{MAX_REF_SECONDS} 秒")
    return int(sample_rate), float(duration)


class VoiceAssetStore:
    """data/voice-assets 下的清单 + 文件。"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.files_dir = self.root / "files"
        self.manifest_path = self.root / "manifest.json"

    def ensure(self) -> None:
        self.files_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.is_file():
            payload = {"version": 1, "assets": []}
            text = __import__('json').dumps(payload, ensure_ascii=False, indent=2) + "\n"
            self.manifest_path.write_text(text, encoding='utf-8')

    def _read_manifest(self) -> list[VoiceAsset]:
        self.ensure()
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        items = raw.get("assets") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return []
        out: list[VoiceAsset] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            aid = str(item.get("id") or "").strip()
            if not ASSET_ID_RE.match(aid):
                continue
            name = str(item.get("name") or "").strip() or aid
            filename = str(item.get("filename") or f"{aid}.wav").strip()
            out.append(
                VoiceAsset(
                    id=aid,
                    name=name,
                    filename=filename,
                    created_at=float(item.get("created_at") or 0),
                    updated_at=float(item.get("updated_at") or 0),
                    size=int(item.get("size") or 0),
                    sample_rate=int(item.get("sample_rate") or 0),
                    duration_seconds=float(item.get("duration_seconds") or 0),
                )
            )
        return out

    def _write_manifest(self, assets: list[VoiceAsset]) -> None:
        self.ensure()
        payload = {
            "version": 1,
            "assets": [a.as_dict() for a in assets],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        tmp = self.manifest_path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.manifest_path)

    def list(self) -> list[VoiceAsset]:
        assets = self._read_manifest()
        assets.sort(key=lambda a: (-a.created_at, a.name.lower()))
        return assets

    def get(self, asset_id: str) -> VoiceAsset | None:
        aid = str(asset_id or "").strip()
        for asset in self._read_manifest():
            if asset.id == aid:
                return asset
        return None

    def path_for(self, asset_id: str) -> Path | None:
        asset = self.get(asset_id)
        if asset is None:
            return None
        path = self.files_dir / asset.filename
        if not path.is_file():
            # 兼容旧文件名 {id}.wav
            alt = self.files_dir / f"{asset.id}.wav"
            if alt.is_file():
                return alt.resolve()
            return None
        return path.resolve()

    def register(self, *, name: str, data: bytes) -> VoiceAsset:
        label = str(name or "").strip()
        if not label or len(label) > 80:
            raise ValueError("音色名称必填且不超过 80 字")
        sample_rate, duration = _validate_wav(data)
        self.ensure()
        now = time.time()
        asset_id = _new_id()
        while self.get(asset_id) is not None:
            asset_id = _new_id()
        filename = f"{asset_id}.wav"
        target = self.files_dir / filename
        # 先写临时文件，成功后再入清单，避免半成品资产
        tmp = target.with_suffix(".wav.tmp")
        try:
            tmp.write_bytes(bytes(data))
            asset = VoiceAsset(
                id=asset_id,
                name=label,
                filename=filename,
                created_at=now,
                updated_at=now,
                size=len(data),
                sample_rate=sample_rate,
                duration_seconds=round(duration, 3),
            )
            assets = self._read_manifest()
            assets.append(asset)
            self._write_manifest(assets)
            tmp.replace(target)
            return asset
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            # 回滚清单中刚写入的条目
            assets = [a for a in self._read_manifest() if a.id != asset_id]
            self._write_manifest(assets)
            raise

    def rename(self, asset_id: str, name: str) -> VoiceAsset:
        label = str(name or "").strip()
        if not label or len(label) > 80:
            raise ValueError("音色名称必填且不超过 80 字")
        assets = self._read_manifest()
        found = None
        out: list[VoiceAsset] = []
        now = time.time()
        for asset in assets:
            if asset.id == asset_id:
                found = VoiceAsset(
                    id=asset.id,
                    name=label,
                    filename=asset.filename,
                    created_at=asset.created_at,
                    updated_at=now,
                    size=asset.size,
                    sample_rate=asset.sample_rate,
                    duration_seconds=asset.duration_seconds,
                )
                out.append(found)
            else:
                out.append(asset)
        if found is None:
            raise ValueError("音色资产不存在")
        self._write_manifest(out)
        return found

    def delete(self, asset_id: str) -> VoiceAsset:
        assets = self._read_manifest()
        found = None
        kept: list[VoiceAsset] = []
        for asset in assets:
            if asset.id == asset_id:
                found = asset
            else:
                kept.append(asset)
        if found is None:
            raise ValueError("音色资产不存在")
        self._write_manifest(kept)
        for candidate in (
            self.files_dir / found.filename,
            self.files_dir / f"{found.id}.wav",
        ):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                pass
        return found


def default_assets_dir(root: Path) -> Path:
    return (root / DEFAULT_REL_DIR).resolve()
