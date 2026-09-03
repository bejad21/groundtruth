"""Small, dependency-free hardening helpers for a public demo endpoint.

Not a substitute for a real gateway (rate limiting here is per-process and
resets on restart), but it stops the two cheapest ways to abuse a public demo:
spoofed content-type uploads and naive request flooding.
"""
import time
from collections import defaultdict, deque

MAGIC_BYTES: dict[bytes, str] = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"RIFF": "image/webp",  # followed by size + "WEBP", checked separately
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
    """Fixed-window per-key limiter. In-memory by design: fine for a single demo instance.

    Every key ever queried used to keep a dict entry forever, even once its
    hits had all aged out of the window — a client hit once and never seen
    again left a permanent, empty entry behind. Over a long-running process
    seeing many distinct IPs, that's unbounded memory growth. Every
    `sweep_interval`-th call now sweeps out any key whose most recent hit has
    already expired, so total memory stays bounded by recent traffic rather
    than by every key ever seen.
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
        """Current hit count within the window, without recording a new hit.
        Used to peek ("has this key already used up its budget?") before
        deciding whether an attempt should count against it at all. Also
        removes the key entirely once it has no hits left in the window,
        rather than leaving a permanent empty entry behind."""
        now = self._clock()
        hits = self._hits.get(key)
        if hits is None:
            return 0
        self._purge(hits, now)
        if not hits:
            del self._hits[key]
        return len(hits)

    def tracked_key_count(self) -> int:
        """How many distinct keys currently hold any state. Exposed for tests
        (and operational introspection) to confirm memory stays bounded."""
        return len(self._hits)
