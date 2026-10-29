"""Cursor headless adapter. Chat input is data, never command-line options."""
import json
import os
from pathlib import Path
import subprocess
from .openai_compat import OpenAICompatProcessor


class CursorProcessor(OpenAICompatProcessor):
    def __init__(self, mcfg, *, raise_errors=False):
        super().__init__(mcfg, raise_errors=raise_errors)
        self.executable = mcfg.get('executable') or 'agent'
        if not mcfg.get('work_dir'):
            raise ValueError('Cursor requires a dedicated work_dir')
        self.work_dir = Path(mcfg['work_dir']).expanduser().resolve()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.cursor_model = mcfg.get('model', '')

    def _request(self, messages, key, request_id):
        return {}, {'messages': messages}

    def handle_reply(self, contact, text, *, request_id=None, member_key='', member_name='', **kwargs):
        from ..reply import Reply
        key = self._key(contact, 'group' if member_key or kwargs.get('channel_type') == 'group' else 'dm')
        history = self.histories.get(key, [])
        messages = ([{'role':'system','content':self.system_prompt}] if self.system_prompt else []) + history + [{'role':'user','content':text}]
        args = [self.executable, '--print', '--output-format', 'json', '--mode', 'ask', '--sandbox', 'enabled']
        if self.cursor_model:
            args.extend(['--model', self.cursor_model])
        env = os.environ.copy()
        if self.api_key:
            env['CURSOR_API_KEY'] = self.api_key
        result = subprocess.run(args, input=json.dumps(messages, ensure_ascii=False),
                                cwd=self.work_dir, env=env, text=True, encoding='utf-8',
                                capture_output=True, timeout=self.timeout, shell=False)
        if result.returncode != 0:
            raise ValueError('Cursor failed or requires approval')
        data = json.loads(result.stdout)
        if (not isinstance(data, dict) or data.get('type') != 'result' or
                data.get('subtype') != 'success' or data.get('is_error') is not False or
                data.get('approval_required') or data.get('error') or
                not isinstance(data.get('result'), str) or not data['result'].strip()):
            raise ValueError('Cursor did not return a complete successful result')
        reply = data['result'].strip()
        self.histories[key] = (history + [{'role':'user','content':text}, {'role':'assistant','content':reply}])[-self.max_history*2:]
        return Reply.from_text(reply)
