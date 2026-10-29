"""OpenAI Responses JSON protocol, with strict terminal-status validation."""
from .openai_compat import OpenAICompatProcessor


class ResponsesProcessor(OpenAICompatProcessor):
    def _request(self, messages, key, request_id):
        headers, body = super()._request(messages, key, request_id)
        body['input'] = body.pop('messages')
        return headers, body

    def _decode(self, data):
        if not isinstance(data, dict) or data.get('status') != 'completed' or data.get('error') or data.get('incomplete_details'):
            raise ValueError('Responses reply is incomplete')
        pieces = []
        for item in data.get('output', []):
            if item.get('type') == 'reasoning':
                continue
            if item.get('type') != 'message' or item.get('status') != 'completed':
                raise ValueError('Responses contains unfinished or unsupported output')
            for part in item.get('content', []):
                if part.get('type') != 'output_text' or not isinstance(part.get('text'), str):
                    raise ValueError('Responses contains unsupported content')
                pieces.append(part['text'])
        reply = '\n'.join(pieces).strip()
        if not reply:
            raise ValueError('Responses has no final text')
        return reply
