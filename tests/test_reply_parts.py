import pytest

from butler.reply import split_reply


@pytest.mark.parametrize('text,expected', [
    (None, []), ('  \n ', []), ('尾巴', ['尾巴']),
    ('真的吗？！”下一句。尾巴', ['真的吗？！”', '下一句。', '尾巴']),
    ('链接 https://example.test/a?x=1! 结束。尾巴', ['链接 https://example.test/a?x=1! 结束。', '尾巴']),
    ('试试 `a?!b`。好。', ['试试 `a?!b`。', '好。']),
    ('试试 ``a `b?!c` d``。好。', ['试试 ``a `b?!c` d``。', '好。']),
    ('你好。\n！？\n再见。', ['你好。！？', '再见。']),
    ('！？\n你好。', ['！？你好。']),
    ('版本3.14，见example.test。尾巴', ['版本3.14，见example.test。', '尾巴']),
    ('见 https://example.test/a?x=1。后文。', ['见 https://example.test/a?x=1。', '后文。']),
    ('前\n```python\na?!b\nc。\n```\n后。', ['前', '```python\na?!b\nc。\n```', '后。']),
    ('前\n````md\n```?!\n````\n后。', ['前', '````md\n```?!\n````', '后。']),
    ('前\n~~~~md\n~~~?!\n~~~~\n后。', ['前', '~~~~md\n~~~?!\n~~~~', '后。']),
    ('！？', ['！？']),  # An intentionally punctuation-only whole reply is preserved.
])
def test_split(text, expected):
    assert split_reply(text) == ([text] if text and text.strip() else [])


@pytest.mark.parametrize('text,reply', [('在吗', '你好。再见！'), ('', 'unused'), ('在吗', '[SILENT]'), ('/new', 'unused')])
def test_complete_reply_contract_on_all_handle_paths(make_home, text, reply):
    home = make_home(replies=[reply], pending_items=[])
    result = home.butler.handle('101', text, msg_id='req-1')
    data = result.as_dict()
    assert data['reply_parts'] == split_reply(result.reply)
    assert data['meta']['reply_complete'] is True
    assert data['meta']['msg_id'] == 'req-1'


def test_error_and_reset_contract(make_home):
    from butler.hermes import HermesError
    home = make_home(replies=[HermesError('fail')])
    data = home.butler.handle('101', 'hi', msg_id='err').as_dict()
    assert data['meta']['msg_id'] == 'err'
    assert data['reply_parts'] == split_reply(data['reply'])
    assert home.butler.reset('101').as_dict()['meta']['reply_complete'] is True


def test_parts_computed_after_pending_and_actions(make_home):
    from test_pipeline import act
    h=make_home(replies=['好。'+act(skill='reminder.list')])
    result=h.butler.handle('101','hi').as_dict()
    assert result['reply_parts']==split_reply(result['reply'])
    assert '该喝水' in result['reply'] and '喝水' in result['reply']
    assert all('<<butler:action' not in p for p in result['reply_parts'])
