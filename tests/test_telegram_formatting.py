from datetime import datetime, timezone


def message(text):
    from butler.channels.telegram.formatting import Message
    return Message(-100123, 15, text, datetime(2026, 10, 22, 10, tzinfo=timezone.utc), 'zaobao.sg 早报', 'zaobaosg')


def test_text_preserves_original_and_has_time_source_and_permalink():
    from butler.channels.telegram.formatting import parts
    result = parts(message('新闻原文。\nhttps://example.com/story'))
    assert len(result) == 1
    assert '新闻原文。\nhttps://example.com/story' in result[0]
    assert '2026-10-22 18:00' in result[0]
    assert 'zaobao.sg 早报' in result[0]
    assert 'https://t.me/zaobaosg/15' in result[0]


def test_long_body_preserves_order_and_does_not_split_url():
    from butler.channels.telegram.formatting import parts
    url = 'https://example.com/' + 'x' * 600
    result = parts(message('甲' * 700 + '\n' + url + '\n' + '乙' * 200))
    assert len(result) > 2
    assert sum(p.count('甲') for p in result) == 700
    assert sum(p.count('乙') for p in result) == 200
    assert sum(url in p for p in result) == 1
    assert all('https://t.me/zaobaosg/15' in p for p in result)
    assert all(len(p) <= 500 or url in p for p in result)
    assert result[0].find('甲') >= 0 and '乙' in result[-1]


def test_blank_text_is_ignored_and_naive_dates_are_rejected():
    import pytest
    from butler.channels.telegram.formatting import Message, parts
    assert parts(message(' \n ')) == []
    with pytest.raises(ValueError):
        Message(-100123, 1, 'x', datetime(2026, 10, 22), 'source', 'source')
