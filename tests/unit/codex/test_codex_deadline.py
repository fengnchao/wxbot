import threading
import time

import pytest

from butler.backends.codex_runtime import CallDeadline,DeadlineCodex


def test_sdk_initialize_can_be_closed_before_high_level_constructor_returns(monkeypatch):
    released=threading.Event();clients=[]
    class Transport:
        def __init__(self,config):clients.append(self);self.closed=False
        def start(self):pass
        def initialize(self):
            assert released.wait(.5),'initialize remained blocked'
            raise RuntimeError('transport closed')
        def close(self):self.closed=True;released.set()
    monkeypatch.setattr('butler.backends.codex_runtime.CodexClient',Transport)
    deadline=CallDeadline(.03);started=time.monotonic()
    try:
        with pytest.raises(RuntimeError,match='transport closed'):
            DeadlineCodex(None,(deadline,))
        assert deadline.expired and clients[0].closed
        assert time.monotonic()-started<.4
    finally:deadline.cancel();released.set()


def test_finished_startup_cannot_later_close_reused_transport():
    class Client:
        closed=False
        def close(self):self.closed=True
    client=Client();deadline=CallDeadline(10)
    deadline.attach(client);deadline.finish()
    deadline._expire()
    assert not client.closed and not deadline.expired


def test_already_expiring_startup_cannot_be_published():
    class Client:
        closed=False
        def close(self):self.closed=True
    client=Client();deadline=CallDeadline(10)
    try:
        deadline.attach(client);deadline._expire()
        with pytest.raises(TimeoutError):deadline.finish()
        assert client.closed
    finally:deadline.cancel()
