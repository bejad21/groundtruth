"""Upload sniffing and in-memory rate limiting for the public demo endpoint."""
import time
from collections import defaultdict, deque

MAGIC_BYTES: dict[bytes, str] = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"RIFF": "image/webp",
    b"%PDF-": "application/pdf",
}


def sniff_mime(body: bytes) -> str | None:
    """Identify a file by its magic bytes, ignoring whatever Content-Type the client sent."""
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if body.startswith(b"RIFF") and body[8:12] == b"WEBP":
        return "image/webp"
    if body.startswith(b"%PDF-"):
        return "application/pdf"
    return None


class RateLimiter:
    """Fixed-window per-key limiter, in-memory for a single instance.

    Every `sweep_interval` calls, keys whose hits have all expired are dropped
    so memory stays bounded by recent traffic.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        sweep_interval: int = 1000,
        clock=time.monotonic,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.sweep_interval = sweep_interval
        self._clock = clock
        self._hits: dict[str, deque] = defaultdict(deque)
        self._calls_since_sweep = 0

    def _purge(self, hits: deque, now: float) -> None:
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()

    def _maybe_sweep(self, now: float) -> None:
        self._calls_since_sweep += 1
        if self._calls_since_sweep < self.sweep_interval:
            return
        self._calls_since_sweep = 0
        stale_keys = [key for key, hits in self._hits.items() if not hits or now - hits[-1] > self.window_seconds]
        for key in stale_keys:
            del self._hits[key]

    def allow(self, key: str) -> bool:
        now = self._clock()
        hits = self._hits[key]
        self._purge(hits, now)
        allowed = len(hits) < self.max_requests
        if allowed:
            hits.append(now)
        self._maybe_sweep(now)
        return allowed

    def count(self, key: str) -> int:
        """Hit count within the window, without recording a hit. Drops the key once empty."""
        now = self._clock()
        hits = self._hits.get(key)
        if hits is None:
            return 0
        self._purge(hits, now)
        if not hits:
            del self._hits[key]
        return len(hits)

    def tracked_key_count(self) -> int:
        """Number of keys currently tracked; used to check memory stays bounded."""
        return len(self._hits)
