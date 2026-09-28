"""A tiny in-process sliding-window rate limiter for the few unauthenticated endpoints."""
import threading
import time
from collections import defaultdict, deque

from ..errors import RateLimited


class RateLimiter:
    def __init__(self, max_calls: int, window_secs: float):
        self.max_calls, self.window = max_calls, window_secs
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str):
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.max_calls:
                raise RateLimited(int(self.window - (now - q[0])) + 1)
            q.append(now)
            if len(self._hits) > 10_000:                     # forget idle addresses
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]
