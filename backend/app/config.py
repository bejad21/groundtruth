import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_MODEL_FALLBACK = os.environ.get("GEMINI_MODEL_FALLBACK", "gemini-flash-lite-latest")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
# nvidia/nemotron-nano-12b-v2-vl:free was the original default here; OpenRouter
# removed it from its free-tier catalog entirely (confirmed live: 404 "No
# endpoints found", not a rate limit) sometime after this project was built.
# Swapped for its NVIDIA-lineage successor, verified live against a real
# ticket image through this exact provider's structured-extraction prompt
# before being made the default. Run scripts/check_openrouter_models.py
# periodically so a future catalog change like this doesn't go unnoticed again.
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free")
OPENROUTER_MODEL_FALLBACK = os.environ.get("OPENROUTER_MODEL_FALLBACK", "google/gemma-4-31b-it:free")
# OpenRouter uses this purely for its own attribution/leaderboard, not auth — set it
# to this deployment's real public URL if you have one. Left unset by default rather
# than a fake domain that doesn't resolve to this project.
OPENROUTER_HTTP_REFERER = os.environ.get("OPENROUTER_HTTP_REFERER", "")

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
CONFIDENCE_REVIEW_THRESHOLD = float(os.environ.get("CONFIDENCE_REVIEW_THRESHOLD", "0.75"))
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "intake_agent.db"))
DEMO_CLIENT_ID = "demo-client"

# API-key -> client_id. The client_id used for every DB read/write is resolved
# server-side from this mapping, never taken from a client-supplied header, so a
# caller can no longer read or write another client's records just by naming a
# different client_id. One shared demo key today; a real deployment issues a
# distinct key per client instead of adding entries to a shared secret.
_DEMO_API_KEY = os.environ.get("DEMO_API_KEY", "")
CLIENT_API_KEYS: dict[str, str] = {_DEMO_API_KEY: DEMO_CLIENT_ID} if _DEMO_API_KEY else {}

# Fernet key for encrypting sensitive text fields at rest (source name, truck/driver
# ID, notes). Generate one with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
