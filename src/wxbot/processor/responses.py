"""OpenAI Responses JSON protocol, with strict terminal-status validation."""
from .openai_compat import OpenAICompatProcessor
from common.model_stream import answer,emit,json_frames,TrimmedAnswer


class ResponsesProcessor(OpenAICompatProcessor):
    def _stream_decode(self,response):
        items={};output=TrimmedAnswer()
        for data in json_frames(response.iter_lines()):
            if not isinstance(data,dict):raise ValueError('Invalid Responses stream')
            kind=data.get('type')
            if kind in ('error','response.failed','response.incomplete'):raise ValueError('Responses stream failed')
            if kind=='response.output_item.added':
                item=data.get('item') or {}
                if item.get('type') not in ('message','reasoning'):raise ValueError('Unsupported streaming tool request')
                if item.get('type')=='message':items[item.get('id')]=item.get('phase')
            elif kind=='response.reasoning_summary_text.delta':
                if isinstance(data.get('delta'),str):emit('summary_delta',text=data['delta'])
            elif kind=='response.output_text.delta':
                # Commentary can change across tool loops. Only an assistant
                # message in the final-answer channel (or standard Responses
                # messages without phase) may become delivery text.
                if data.get('item_id') not in items or items[data['item_id']] not in (None,'final_answer'):
                    continue
                text=data.get('delta')
                if not isinstance(text,str):raise ValueError('Invalid Responses text delta')
                output.feed(text)
            elif kind=='response.completed':
                final=self._decode(data.get('response'))
                prefix=output.text
                if not final.startswith(prefix):raise ValueError('Responses final answer changed')
                answer(final[len(prefix):])
                return final
        raise ValueError('Responses stream disconnected before completion')

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
            if item.get('type')=='message' and item.get('phase') not in (None,'final_answer'):
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
