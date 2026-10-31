"""Portable, data-only skill catalogue. Skills never select their own authority."""
from pathlib import Path
import re

import yaml


class SkillCatalogue:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def _entries(self):
        entries = {}
        for path in sorted(self.root.rglob('SKILL.md')):
            resolved = path.resolve()
            if not resolved.is_relative_to(self.root):
                continue
            text = path.read_text(encoding='utf-8-sig')
            parts = text.split('---', 2)
            if len(parts) != 3 or parts[0].strip():
                raise ValueError('Invalid skill frontmatter: '+path.parent.name)
            fm = yaml.safe_load(parts[1]) or {}
            name = fm.get('name', path.parent.name)
            meta = fm.get('metadata') or {}
            policy = meta.get('butler') or meta.get('hermes') or {}
            tags = policy.get('tags', fm.get('tags', []))
            if isinstance(tags, str):
                tags = [x.strip() for x in tags.strip('[]').split(',')]
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}',name) or name in entries:
                raise ValueError('Duplicate or invalid skill name')
            tools = policy.get('tools', [])
            if not isinstance(tags, list) or not isinstance(tools, list):
                raise ValueError('Invalid skill metadata')
            group = self.root.name if self.root.name in {'roles', 'tools'} else resolved.relative_to(self.root).parts[0]
            category = 'role' if 'butler-role' in tags else 'tool'
            if group in {'roles', 'tools'}:
                category = 'role' if group == 'roles' else 'tool'
                # Keep tags in catalogue responses for older clients; grouped
                # skills declare their role through their directory, not YAML.
                tags = [tag for tag in tags if tag != 'butler-role']
                if category == 'role':
                    tags.append('butler-role')
            entries[name] = {'name': name, 'description': str(fm.get('description', '')),
                             'tags': list(tags), 'tools': list(tools), 'category': category, '_path': path}
        return entries

    def list(self):
        return [{k: v for k, v in item.items() if not k.startswith('_')}
                for item in self._entries().values() if 'butler-setup' not in item['tags']]

    def validate(self, policy):
        entries = self._entries()
        if not isinstance(policy, dict):
            raise ValueError('Role policy is required')
        role, allowed = policy.get('role_skill'), policy.get('allowed_skills')
        if role not in entries or entries[role]['category'] != 'role':
            raise ValueError('Unknown or invalid role skill')
        if not isinstance(allowed, list) or any(not isinstance(n, str) for n in allowed):
            raise ValueError('Invalid skill allowlist')
        if any(n not in entries or entries[n]['category'] != 'tool' or 'butler-setup' in entries[n]['tags'] for n in allowed):
            raise ValueError('Unknown tool skill or role in tool allowlist')
        return {'role_skill': role, 'allowed_skills': sorted(set(allowed))}

    def read(self, name, file_path='SKILL.md'):
        entries = self._entries()
        if name not in entries:
            raise ValueError('Unknown skill')
        base = entries[name]['_path'].parent.resolve()
        relative = Path(file_path)
        path = (base / relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or not path.is_relative_to(base):
            raise ValueError('Skill file must stay inside its own directory')
        if not path.is_file() or path.stat().st_size > 256_000:
            raise ValueError('Skill file missing or too large')
        return path.read_text(encoding='utf-8-sig')

    def allowed_tools(self, policy):
        policy = self.validate(policy)
        entries = self._entries()
        return {tool for name in policy['allowed_skills'] for tool in entries[name]['tools']}
