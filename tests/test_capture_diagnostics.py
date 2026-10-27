"""Bounded sender-read diagnostics using synthetic pixels; no live desktop."""
from types import SimpleNamespace

from PIL import Image

from wxbot.wechat.chat_window import ChatWindow


def rect(left=0,top=0,right=400,bottom=80):
    return SimpleNamespace(left=left,top=top,right=right,bottom=bottom)


def test_clipped_row_reports_safe_geometry_and_no_message_text(caplog):
    chat=ChatWindow('101',{})
    item=SimpleNamespace(BoundingRectangle=rect(top=-10))
    assert chat._classify(item,'PRIVATE_MESSAGE',rect())=='system'
    assert 'row_clipped' in caplog.text and 'PRIVATE_MESSAGE' not in caplog.text
    chat._classify(item,'PRIVATE_MESSAGE',rect())
    assert len(caplog.records)==1


def test_sender_diagnostics_distinguish_uniform_pixels_and_gutter_conflict(monkeypatch,caplog):
    import wxbot.wechat.chat_window as module
    chat=ChatWindow('101',{})
    item=SimpleNamespace(BoundingRectangle=rect())
    image=Image.new('RGB',(400,56),(31,31,31))
    monkeypatch.setattr(module.ImageGrab,'grab',lambda **kwargs:image)
    assert chat._classify(item,'PRIVATE_MESSAGE',rect())=='system'
    assert 'ambiguous_side_pixels' in caplog.text
    caplog.clear()
    chat=ChatWindow('101',{})
    image.paste((255,255,255),(397,0,400,56))
    assert chat._classify(item,'PRIVATE_MESSAGE',rect())=='system'
    assert 'gutter_mismatch' in caplog.text and 'PRIVATE_MESSAGE' not in caplog.text


def test_capture_retry_exposes_known_reason_without_raw_exception_payload(caplog):
    from wxbot.inbox import MainInbox
    from wxbot.wechat.main_window import Session
    from wxbot.wechat.chat_window import ReadDeferred
    inbox=MainInbox.__new__(MainInbox)
    inbox._connected=True
    inbox.monotonic=lambda:0
    inbox.pending={'101':Session('101',1)}
    inbox._receive_retry={}
    inbox._poll_interval=lambda:1
    def deferred(session):
        raise ReadDeferred('unknown_unread_sender','PRIVATE_MESSAGE')
    inbox._receive=deferred
    assert inbox._receive_one()
    assert 'unknown_unread_sender' in caplog.text and 'PRIVATE_MESSAGE' not in caplog.text
