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
