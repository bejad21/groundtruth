from app.security import RateLimiter, sniff_mime


def test_sniff_mime_detects_png():
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    assert sniff_mime(png_bytes) == "image/png"


def test_sniff_mime_detects_jpeg():
    jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 20
    assert sniff_mime(jpeg_bytes) == "image/jpeg"


def test_sniff_mime_detects_pdf():
    pdf_bytes = b"%PDF-1.4\n" + b"\x00" * 20
    assert sniff_mime(pdf_bytes) == "application/pdf"


def test_sniff_mime_detects_webp():
    webp_bytes = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 20
    assert sniff_mime(webp_bytes) == "image/webp"


def test_sniff_mime_rejects_spoofed_content():
    # A .txt file renamed to look like a PDF via Content-Type doesn't change its bytes.
    assert sniff_mime(b"just some plain text pretending to be a pdf") is None


def test_rate_limiter_allows_up_to_the_limit():
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    results = [limiter.allow("1.2.3.4") for _ in range(5)]
    assert all(results)


def test_rate_limiter_blocks_beyond_the_limit():
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        limiter.allow("1.2.3.4")
    assert limiter.allow("1.2.3.4") is False


def test_rate_limiter_scopes_by_key():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("client-a") is True
    assert limiter.allow("client-b") is True  # different key, independent budget
    assert limiter.allow("client-a") is False


def test_count_reflects_hits_recorded_by_allow():
    limiter = RateLimiter(max_requests=10, window_seconds=60)
    assert limiter.count("k") == 0
    limiter.allow("k")
    limiter.allow("k")
    assert limiter.count("k") == 2


def test_count_does_not_itself_consume_budget():
    """count() is a peek — calling it repeatedly must not use up the window."""
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.count("k")
    limiter.count("k")
    limiter.count("k")
    assert limiter.count("k") == 0
    assert limiter.allow("k") is True  # budget untouched by the peeks above


def test_count_is_scoped_by_key():
    limiter = RateLimiter(max_requests=10, window_seconds=60)
    limiter.allow("client-a")
    limiter.allow("client-a")
    limiter.allow("client-b")
    assert limiter.count("client-a") == 2
    assert limiter.count("client-b") == 1


# ---------------------------------------------------------------------------
# Memory: RateLimiter used to keep a dict entry forever for every distinct key
# it had ever seen, even once that key's hits had all expired out of the
# window — a key queried exactly once (a one-off visitor's IP) left a
# permanent, never-cleaned-up entry. Over a long-running process hit by many
# distinct IPs, that's unbounded growth. A `clock` callable is injectable so
# these tests can fast-forward time deterministically instead of sleeping.
# ---------------------------------------------------------------------------


def test_tracked_key_count_does_not_grow_without_bound_as_keys_expire():
    fake_now = [0.0]
    limiter = RateLimiter(max_requests=5, window_seconds=10, sweep_interval=20, clock=lambda: fake_now[0])

    for i in range(200):
        fake_now[0] += 1  # each key's single hit is 200s apart in the end, far outside the 10s window
        limiter.allow(f"one-off-visitor-{i}")

    # However this is implemented internally, memory must not scale with the
    # 200 distinct one-off keys that have all long since expired.
    assert limiter.tracked_key_count() < 25


def test_sweep_does_not_evict_a_key_still_inside_its_window():
    """Regression guard: sweeping must never discard an active client's
    budget early — that would let them burst past their real limit."""
    fake_now = [0.0]
    limiter = RateLimiter(max_requests=3, window_seconds=100, sweep_interval=5, clock=lambda: fake_now[0])

    limiter.allow("active-client")
    limiter.allow("active-client")
    # Enough other traffic to trigger several sweeps while "active-client" is
    # still well inside its 100s window.
    for i in range(20):
        fake_now[0] += 1
        limiter.allow(f"other-{i}")

    assert limiter.count("active-client") == 2
    assert limiter.allow("active-client") is True  # 3rd request still allowed
    assert limiter.allow("active-client") is False  # budget (3) is genuinely exhausted, not silently reset


def test_default_sweep_interval_does_not_change_default_behavior():
    """Regression guard: the existing constructor signature (positional
    max_requests, window_seconds) must keep working unchanged."""
    limiter = RateLimiter(5, 60)
    assert limiter.allow("k") is True
    assert limiter.count("k") == 1
