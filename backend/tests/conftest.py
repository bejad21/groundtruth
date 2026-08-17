import os
import tempfile

import pytest

# Config reads env vars at import time, so these must be set before `app.*` is
# imported anywhere. A dedicated temp DB keeps tests from touching the real
# dev database or leaving rows behind.
_TEST_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DB_PATH"] = _TEST_DB.name
os.environ.setdefault("DEMO_API_KEY", "test-key-for-pytest-only")
os.environ.setdefault("ENCRYPTION_KEY", "t6A7RRcvRcLFNgE_p7Z0H7PYU-ZAKzbm7CNc418n2dY=")
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("OPENROUTER_API_KEY", "")


@pytest.fixture(autouse=True, scope="session")
def _cleanup_test_db():
    yield
    try:
        os.unlink(_TEST_DB.name)
    except OSError:
        pass
