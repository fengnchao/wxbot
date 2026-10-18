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
        kind = 'heartbeat' if session_kind == 'heartbeat' else 'chat'
        return self._get(('session', self.endpoint, contact.profile, contact.key(), kind))

    def profile(self, profile):
        return self._get(('profile', self.endpoint, profile))
