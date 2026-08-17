import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from . import config, db
from .agent import AgentError, run_intake_agent
from .models import ConfirmRequest, ExtractResponse
from .security import RateLimiter, sniff_mime
from .validation import validate_record

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("intake_agent")

ALLOWED_MIME_TYPES = {"image/png", "image/jpeg", "image/webp", "application/pdf"}
extract_limiter = RateLimiter(max_requests=10, window_seconds=60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if not config.CLIENT_API_KEYS:
        logger.warning("No DEMO_API_KEY configured: /api/extract, /api/confirm, /api/runs and /api/records will reject every request.")
    yield


app = FastAPI(title="Groundtruth", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _authenticated_client_id(request: Request) -> str:
    """Resolve client_id from a possessed credential, never from a client-supplied
    header. Previously this trusted an `X-Client-Id` header the caller could set to
    any value, which made the per-client isolation in db.py decorative: anyone could
    read or write another client's records just by naming a different ID. Now the
    header is gone entirely; the ID is looked up server-side from the API key."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    key = auth.removeprefix("Bearer ").strip()
    client_id = config.CLIENT_API_KEYS.get(key)
    if client_id is None:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return client_id


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "providers_configured": {
            "gemini": bool(config.GEMINI_API_KEY),
            "openrouter": bool(config.OPENROUTER_API_KEY),
        },
    }


@app.post("/api/extract", response_model=ExtractResponse)
async def extract_ticket(request: Request, file: UploadFile = File(...), lang: str = "en") -> ExtractResponse:
    client_id = _authenticated_client_id(request)
    client_key = request.client.host if request.client else "unknown"
    if not extract_limiter.allow(client_key):
        raise HTTPException(status_code=429, detail="Too many requests. Try again in a minute.")

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: {file.content_type}")

    body = await file.read()
    if len(body) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 8MB upload limit.")
    if not body:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    sniffed = sniff_mime(body)
    if sniffed is None or sniffed != file.content_type:
        raise HTTPException(status_code=415, detail="File content does not match its declared type.")

    try:
        result = await run_in_threadpool(run_intake_agent, body, sniffed, lang)
    except AgentError as exc:
        logger.warning("Agent error: %s", exc)
        db.log_run(client_id, provider="", model="", latency_ms=0, needs_review=None, status="error", error=str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    run_id = db.log_run(
        client_id, provider=result.provider, model=result.model,
        latency_ms=result.latency_ms, needs_review=result.response.needs_review, status="ok",
    )
    result.response.run_id = run_id
    return result.response


@app.post("/api/confirm")
async def confirm_record(request: Request, payload: ConfirmRequest, lang: str = "en") -> dict:
    client_id = _authenticated_client_id(request)
    remaining_flags = validate_record(payload.record, lang)
    blocking = [f for f in remaining_flags if f.severity == "blocking"]
    if blocking:
        raise HTTPException(status_code=422, detail=[f.model_dump() for f in blocking])

    record_id = db.save_record(client_id, payload.run_id, payload.record.model_dump())
    logger.info("Record confirmed: id=%s client=%s", record_id, client_id)
    return {"status": "confirmed", "record": payload.record.model_dump(), "record_id": record_id}


@app.get("/api/runs")
async def get_runs(request: Request, limit: int = 20) -> list[dict]:
    return db.list_runs(_authenticated_client_id(request), limit=min(limit, 100))


@app.get("/api/records")
async def get_records(request: Request, limit: int = 50) -> list[dict]:
    return db.list_records(_authenticated_client_id(request), limit=min(limit, 100))
