"""知识模板的读写：页面上改的是一份 Markdown 配置，不是知识数据。

只写 data/knowledge/template.md 这一个目标——浏览器提交内容，永远不提交路径。
写入沿用配置编辑的约定：跨进程锁、版本比对、写前备份、临时文件原子替换。
删掉这份覆盖层就是恢复插件内置模板，vault 里一条知识都不会丢。
"""
from __future__ import annotations

from contextlib import suppress
import hashlib
import os
from pathlib import Path
import tempfile
import time
import uuid

from butler.runtime.knowledge_template import (BUILTIN_TEMPLATE, MAX_TEMPLATE_BYTES,
                                               OVERRIDE_NAME, TemplateError, mtime,
                                               parse_template)
from common.config_lock import config_lock


class TemplateConflict(RuntimeError):
    """页面拿到的版本已经过期：别的窗口先保存了。"""


class KnowledgeTemplateView:
    def __init__(self, data_dir, log=None):
        self.root = Path(data_dir) / 'knowledge'
        self.override = self.root / OVERRIDE_NAME
        self.log = log or (lambda *a, **k: None)

    # ---------- 读 ----------
    def _version(self):
        """版本就是覆盖层内容的指纹；没有覆盖层时空串代表「还没覆盖」。"""
        try:
            body = self.override.read_bytes()
        except OSError:
            return ''
        return hashlib.sha256(body).hexdigest()

    def read(self):
        content, source, state = '', 'builtin', 'absent'
        summary, errors = None, []
        if self.override.is_file():
            content = self.override.read_text('utf-8', 'replace')
            try:
                summary, state = parse_template(content).summary(), 'valid'
                source = 'override'
            except TemplateError as exc:
                # 覆盖层写坏时真正生效的是内置模板，页面要同时看到坏内容和生效来源。
                errors, state, source = list(exc.errors), 'invalid', 'plugin'
                content, summary = content, None
        if source != 'override' and BUILTIN_TEMPLATE.is_file():
            if state == 'absent':
                content = BUILTIN_TEMPLATE.read_text('utf-8', 'replace')
            try:
                summary = summary or parse_template(BUILTIN_TEMPLATE.read_text('utf-8', 'replace')).summary()
            except TemplateError as exc:
                errors = errors or list(exc.errors)
        active = self.override if source == 'override' else (
            BUILTIN_TEMPLATE if BUILTIN_TEMPLATE.is_file() else None)
        return {'available': bool(content), 'source': source, 'override': state,
                'path': str(self.override),
                'active_path': str(active) if active else '',
                'version': self._version(),
                'modified_at': mtime(active) if active else 0,
                'content': content, 'summary': summary, 'errors': errors,
                'limits': {'bytes': MAX_TEMPLATE_BYTES}}

    # ---------- 写 ----------
    def _check_version(self, version):
        if not isinstance(version, str) or version != self._version():
            raise TemplateConflict('模板已被其他窗口修改，请刷新后重新核对')

    def _backup(self):
        if not self.override.is_file():
            return ''
        target = self.override.with_name(
            self.override.name + '.backup-' + str(time.time_ns()) + '-' + uuid.uuid4().hex[:8])
        target.write_bytes(self.override.read_bytes())
        return str(target)

    def _write(self, text):
        """Windows 上文件可能被索引器短暂占用，退避重试几次再报错。"""
        self.override.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix='.' + self.override.name + '-', suffix='.tmp',
                                             dir=self.override.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(text.encode('utf-8'))
                handle.flush()
                os.fsync(handle.fileno())
            for attempt in range(3):
                try:
                    os.replace(temporary, self.override)
                    return
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            if temporary is not None and temporary.exists():
                with suppress(OSError):
                    temporary.unlink()

    def save(self, payload):
        if not isinstance(payload, dict) or payload.get('acknowledge') is not True:
            raise ValueError('请确认模板修改')
        action = payload.get('action')
        if action not in ('validate', 'save', 'reset'):
            raise ValueError('模板操作无效')
        if action == 'reset':
            with config_lock(self.override):
                self._check_version(payload.get('version'))
                backup = self._backup()
                if self.override.is_file():
                    self.override.unlink()
            result = self.read()
            result.update(ok=True, action='reset', backup=backup,
                          message='已恢复内置模板；之后新建或新写入的事实按内置模板走')
            return result
        content = payload.get('content')
        if not isinstance(content, str):
            raise ValueError('模板内容必须是文本')
        if len(content.encode('utf-8')) > MAX_TEMPLATE_BYTES:
            raise ValueError('模板超过 %d KB' % (MAX_TEMPLATE_BYTES // 1024))
        summary = parse_template(content).summary()
        if action == 'validate':
            return {'ok': True, 'action': 'validate', 'summary': summary, 'errors': [],
                    'version': self._version()}
        with config_lock(self.override):
            self._check_version(payload.get('version'))
            backup = self._backup()
            self._write(content)
        return {'ok': True, 'action': 'save', 'summary': summary, 'errors': [],
                'version': self._version(), 'backup': backup,
                'message': '模板已保存，后续写入与提炼立即生效，无需重启服务'}
