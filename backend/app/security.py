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
    """Fixed-window per-key limiter. In-memory by design: fine for a single demo instance."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self.window_seconds:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True
