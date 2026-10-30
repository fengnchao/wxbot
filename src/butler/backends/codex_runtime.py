"""Bound the pinned SDK's blocking startup as well as its model stream.

Codex 0.163.0 starts/initializes its transport inside the high-level constructor.
This small subclass preserves that initialization sequence while registering the
transport for cancellation before the first blocking initialize RPC.
"""
import threading
import time

from openai_codex import Codex
from openai_codex.client import CodexClient
from openai_codex._initialize_metadata import validate_initialize_metadata


class CallDeadline:
    def __init__(self, seconds):
        self.ends=time.monotonic()+seconds
        self.expired=False
        self._cancelled=False
        self._client=None
        self._lock=threading.Lock()
        self._timer=threading.Timer(max(0,seconds),self._expire)
        self._timer.daemon=True
        self._timer.start()

    def _expire(self):
        with self._lock:
            if self._cancelled:return
            self.expired=True
            client=self._client
        if client is not None:client.close()

    def attach(self,client):
        with self._lock:
            self._client=client
            expired=self.expired
        if expired:
            client.close()
            self.check()

    def remaining(self):
        return max(0,self.ends-time.monotonic())

    def check(self):
        if self.expired or self.remaining()<=0:
            raise TimeoutError('Codex 请求超过期限（包括初始化），已关闭运行连接')

    def cancel(self):
        with self._lock:self._cancelled=True
        self._timer.cancel()

    def finish(self):
        # Finishing startup must win or lose atomically against cancellation;
        # cancelling a Timer alone cannot stop a callback already in progress.
        with self._lock:
            self.check()
            self._cancelled=True
        self._timer.cancel()


class DeadlineCodex(Codex):
    def __init__(self,config,deadlines):
        self._close_lock=threading.RLock()
        self._client=CodexClient(config=config)
        try:
            self._client.start()
            for deadline in deadlines:deadline.attach(self)
            self._init=validate_initialize_metadata(self._client.initialize())
        except BaseException:
            self.close()
            raise

    def close(self):
        with self._close_lock:super().close()
