"""管理台：音色资产 CRUD、试听与联系人绑定（写 config.wxbot.toml）。"""
from __future__ import annotations

import base64
import time
from copy import deepcopy
from pathlib import Path

import tomlkit
from tomlkit.items import Table

from common.config_lock import config_lock
from common.paths import REPO_ROOT
from wxbot.voice.assets import MAX_UPLOAD_BYTES, VoiceAssetStore, default_assets_dir
from wxbot.voice.policy import VOICE_MODES, normalize_voice_mode


def _wxbot_config_path() -> Path:
    import os
    return Path(os.environ.get('WXBOT_CONFIG') or REPO_ROOT / 'config.wxbot.toml').resolve()


def _assets_dir_from_doc(doc) -> Path:
    voice = doc.get('voice') if isinstance(doc, dict) or hasattr(doc, 'get') else None
    if voice is None:
        return default_assets_dir(REPO_ROOT)
    raw = voice.get('assets_dir') if hasattr(voice, 'get') else None
    if not raw:
        return default_assets_dir(REPO_ROOT)
    path = Path(str(raw))
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def _ensure_voice_tables(doc) -> Table:
    if 'voice' not in doc or not isinstance(doc.get('voice'), Table):
        # 可能是普通 dict 式缺失
        if 'voice' not in doc:
            doc['voice'] = tomlkit.table()
        elif not isinstance(doc['voice'], Table):
            # 替换为 table 并尽量保留
            old = dict(doc['voice']) if hasattr(doc['voice'], 'items') else {}
            table = tomlkit.table()
            for k, v in old.items():
                table[k] = v
            doc['voice'] = table
    voice = doc['voice']
    if 'contacts' not in voice or not isinstance(voice.get('contacts'), Table):
        if 'contacts' not in voice:
            voice['contacts'] = tomlkit.table()
        elif not isinstance(voice['contacts'], Table):
            old = dict(voice['contacts']) if hasattr(voice['contacts'], 'items') else {}
            table = tomlkit.table()
            for k, v in old.items():
                table[k] = v
            voice['contacts'] = table
    if 'contact_refs' not in voice or not isinstance(voice.get('contact_refs'), Table):
        if 'contact_refs' not in voice:
            voice['contact_refs'] = tomlkit.table()
        elif not isinstance(voice['contact_refs'], Table):
            old = dict(voice['contact_refs']) if hasattr(voice['contact_refs'], 'items') else {}
            table = tomlkit.table()
            for k, v in old.items():
                table[k] = v
            voice['contact_refs'] = table
    return voice


def _load_doc(path: Path):
    if not path.is_file():
        raise ValueError(f'找不到 wxbot 配置: {path}')
    text = path.read_text(encoding='utf-8-sig')
    return tomlkit.parse(text), text


def _write_doc(path: Path, doc, old_text: str) -> None:
    encoded = tomlkit.dumps(doc)
    # 保留原 BOM 习惯
    data = encoded.encode('utf-8-sig' if old_text.startswith('\ufeff') or path.read_bytes()[:3] == b'\xef\xbb\xbf' else 'utf-8')
    tmp = path.with_suffix(path.suffix + '.tmp-voice')
    tmp.write_bytes(data)
    tmp.replace(path)


class VoiceAdmin:
    def __init__(self, config_path: Path | None = None):
        self.config_path = Path(config_path) if config_path else _wxbot_config_path()

    def store(self) -> VoiceAssetStore:
        with config_lock(self.config_path):
            doc, _ = _load_doc(self.config_path)
        return VoiceAssetStore(_assets_dir_from_doc(doc))

    def list_assets(self) -> dict:
        store = self.store()
        assets = [a.as_dict() for a in store.list()]
        return {
            'ok': True,
            'assets': assets,
            'assets_dir': str(store.root),
            'limits': {
                'max_bytes': MAX_UPLOAD_BYTES,
                'formats': ['wav'],
                'preview': 'registered_reference',
                'note': '试听播放已注册的参考 WAV，不触发 IndexTTS 试合成',
            },
        }

    def register(self, payload: dict) -> dict:
        name = str((payload or {}).get('name') or '').strip()
        b64 = (payload or {}).get('data_base64') or (payload or {}).get('wav_base64') or ''
        if not isinstance(b64, str) or not b64.strip():
            raise ValueError('缺少参考音 data_base64')
        try:
            raw = base64.b64decode(b64, validate=False)
        except Exception as exc:
            raise ValueError('参考音 Base64 无效') from exc
        store = self.store()
        asset = store.register(name=name, data=raw)
        return {'ok': True, 'asset': asset.as_dict()}

    def rename(self, payload: dict) -> dict:
        asset_id = str((payload or {}).get('id') or '').strip()
        name = str((payload or {}).get('name') or '').strip()
        store = self.store()
        asset = store.rename(asset_id, name)
        return {'ok': True, 'asset': asset.as_dict()}

    def delete(self, payload: dict) -> dict:
        asset_id = str((payload or {}).get('id') or '').strip()
        if not asset_id:
            raise ValueError('缺少资产 id')
        store = self.store()
        asset = store.delete(asset_id)
        cleared = self._clear_bindings_for_asset(asset_id)
        return {'ok': True, 'asset': asset.as_dict(), 'cleared_contacts': cleared}

    def preview(self, asset_id: str) -> dict:
        store = self.store()
        asset = store.get(asset_id)
        if asset is None:
            raise ValueError('音色资产不存在')
        path = store.path_for(asset_id)
        if path is None or not path.is_file():
            raise ValueError('参考音文件不存在')
        data = path.read_bytes()
        return {
            '__binary__': True,
            'data': data,
            'content_type': 'audio/wav',
            'filename': asset.filename,
        }

    def bindings(self) -> dict:
        with config_lock(self.config_path):
            doc, _ = _load_doc(self.config_path)
            voice = doc.get('voice') or {}
            contacts = {}
            raw_contacts = voice.get('contacts') or {}
            if hasattr(raw_contacts, 'items'):
                for k, v in raw_contacts.items():
                    contacts[str(k)] = normalize_voice_mode(v)
            refs = {}
            raw_refs = voice.get('contact_refs') or {}
            if hasattr(raw_refs, 'items'):
                for k, v in raw_refs.items():
                    if isinstance(v, str):
                        refs[str(k)] = {'ref_wav': v, 'asset_id': '', 'lang': 'ZH'}
                    elif hasattr(v, 'items') or isinstance(v, dict):
                        refs[str(k)] = {
                            'ref_wav': str(v.get('ref_wav') or ''),
                            'asset_id': str(v.get('asset_id') or ''),
                            'lang': str(v.get('lang') or 'ZH'),
                        }
            enabled = bool(voice.get('enabled', False)) if hasattr(voice, 'get') else False
            tts_provider = str(voice.get('tts_provider') or 'fixture') if hasattr(voice, 'get') else 'fixture'
        assets = [a.as_dict() for a in self.store().list()]
        return {
            'ok': True,
            'enabled': enabled,
            'tts_provider': tts_provider,
            'contacts': contacts,
            'contact_refs': refs,
            'assets': assets,
            'modes': list(VOICE_MODES),
        }

    def bind(self, payload: dict) -> dict:
        """更新单个会话的 mode 与/或 asset_id；互不自动改写。"""
        contact = str((payload or {}).get('contact') or '').strip()
        if not contact:
            raise ValueError('contact 必填（微信会话名）')
        has_mode = 'mode' in (payload or {})
        has_asset = 'asset_id' in (payload or {})
        if not has_mode and not has_asset:
            raise ValueError('请提供 mode 和/或 asset_id')
        mode = None
        if has_mode:
            mode = normalize_voice_mode(payload.get('mode'))
        asset_id = None
        if has_asset:
            asset_id = str(payload.get('asset_id') or '').strip()
            if asset_id:
                store = self.store()
                if store.get(asset_id) is None or store.path_for(asset_id) is None:
                    raise ValueError('音色资产不存在或文件缺失')
        with config_lock(self.config_path):
            doc, old = _load_doc(self.config_path)
            voice = _ensure_voice_tables(doc)
            if has_mode:
                if mode == 'off':
                    # 保留键为 off，便于 UI 回显；不连带清绑定
                    voice['contacts'][contact] = 'off'
                else:
                    voice['contacts'][contact] = mode
            if has_asset:
                refs = voice['contact_refs']
                if not asset_id:
                    if contact in refs:
                        del refs[contact]
                else:
                    existing = refs.get(contact)
                    lang = 'ZH'
                    if isinstance(existing, dict) or (existing is not None and hasattr(existing, 'get')):
                        lang = str(existing.get('lang') or 'ZH')
                    table = tomlkit.table()
                    table['asset_id'] = asset_id
                    table['lang'] = lang
                    # 绑定资产时不保留旧 ref_wav，避免双源歧义
                    refs[contact] = table
            _write_doc(self.config_path, doc, old)
        return {'ok': True, **self.bindings()}

    def _clear_bindings_for_asset(self, asset_id: str) -> list[str]:
        cleared: list[str] = []
        with config_lock(self.config_path):
            doc, old = _load_doc(self.config_path)
            voice = _ensure_voice_tables(doc)
            refs = voice['contact_refs']
            for key in list(refs.keys()):
                value = refs[key]
                current = ''
                if isinstance(value, str):
                    continue
                if hasattr(value, 'get'):
                    current = str(value.get('asset_id') or '').strip()
                if current == asset_id:
                    del refs[key]
                    cleared.append(str(key))
            if cleared:
                _write_doc(self.config_path, doc, old)
        return cleared
