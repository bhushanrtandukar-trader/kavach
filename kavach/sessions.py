"""Server-side sessions.

A session holds the user's decrypted private key and any vault keys they have
opened.  It exists only in this process's memory; the browser only ever gets an
opaque random token.
"""
import secrets
import threading
import time
from dataclasses import dataclass, field

from .errors import SessionExpired

ABSOLUTE_TIMEOUT_SECS = 12 * 3600


@dataclass
class Session:
    token: str
    user_id: str
    username: str
    private_key: bytes
    ip: str
    created: float
    last_activity: float
    vault_keys: dict = field(default_factory=dict)     # vault_id -> (key_version, key)
    cache: dict = field(default_factory=dict)          # verdict-only analysis results; cleared on any write


class SessionStore:
    def __init__(self, idle_timeout: int = 900):
        self.idle_timeout = idle_timeout
        self._sessions = {}
        self._lock = threading.Lock()

    def create(self, user_id, username, private_key, ip='') -> Session:
        now = time.time()
        s = Session(secrets.token_urlsafe(32), user_id, username, private_key, ip, now, now)
        with self._lock:
            self._sessions[s.token] = s
        return s

    def get(self, token, touch=True) -> Session:
        if not token or not isinstance(token, str):
            raise SessionExpired()
        now = time.time()
        with self._lock:
            s = self._sessions.get(token)
            if s is None:
                raise SessionExpired()
            if now - s.last_activity > self.idle_timeout or now - s.created > ABSOLUTE_TIMEOUT_SECS:
                self._drop(token)
                raise SessionExpired('Signed out after inactivity.')
            if touch:
                s.last_activity = now
            return s

    def touch(self, token):
        """Mark activity without doing anything else (browser says the user is active)."""
        self.get(token, touch=True)

    def is_valid(self, token) -> bool:
        try:
            self.get(token, touch=False)
            return True
        except SessionExpired:
            return False

    def _drop(self, token):
        s = self._sessions.pop(token, None)
        if s:
            s.vault_keys.clear()
            s.cache.clear()
            s.private_key = b''

    def destroy(self, token):
        with self._lock:
            self._drop(token)

    def destroy_user(self, user_id, except_token=None):
        with self._lock:
            for t in [t for t, s in self._sessions.items()
                      if s.user_id == user_id and t != except_token]:
                self._drop(t)

    def destroy_all(self):
        with self._lock:
            for t in list(self._sessions):
                self._drop(t)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)
