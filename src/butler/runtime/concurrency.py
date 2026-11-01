"""Process-local locks for stable sessions and shared profile files."""
from threading import Lock, RLock


class RuntimeLocks:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint.rstrip('/')
        self._guard = Lock()
        self._locks = {}

    def _get(self, key):
        with self._guard:
            return self._locks.setdefault(key, RLock())

    def session(self, contact, *, session_kind='chat'):
        # 与 HermesClient 的作用域保持一致：提炼独占一把锁，不挡真实回复。
        kind = session_kind if session_kind in ('heartbeat', 'extract') else 'chat'
        return self._get(('session', self.endpoint, contact.profile, contact.key(), kind))

    def profile(self, profile):
        return self._get(('profile', self.endpoint, profile))
