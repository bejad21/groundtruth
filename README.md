# Groundtruth

A production-style single-agent document intake system: upload a photo or PDF of a
delivery/weighbridge ticket, and an LLM agent reads it, extracts a structured record,
validates it against business rules, and hands back a clean record for human
confirmation. Any field the model isn't confident about gets flagged for a quick fix
before the record ships.

Built as a real, working system rather than a UI mockup: every screen is wired to a
live backend, every number on screen is computed from an actual API response, and the
things that usually get faked in a demo (document previews, agent reasoning, database
writes) are the real thing.

|  |  |
|---|---|
| ![Empty state](docs/screenshots/01-empty-state.png) | ![Flagged review](docs/screenshots/02-review-flagged.png) |
| ![Confirmed receipt](docs/screenshots/03-confirmed-receipt.png) | ![Arabic RTL](docs/screenshots/04-arabic-rtl.png) |

The second screenshot is a real run against a genuinely smudged sample ticket — the
low-confidence field, the validation warning, and the "2 fields need a second look"
count are all computed from the actual model response, not staged.

## What it demonstrates

- **Multi-provider LLM orchestration with real failover.** Not a single hardcoded API
  call — a provider chain that tries multiple vision-capable LLMs in order and falls
  back automatically, with the failover path tested live (forced a provider offline
  and confirmed the next one in the chain picked up the request correctly).
- **Structured extraction + deterministic validation**, not just "ask the model for
  JSON and hope." Every extracted field carries a real confidence score, gated against
  a threshold, and cross-checked against independent business rules (required fields,
  numeric range checks, date sanity, category allow-lists).
- **Human-in-the-loop review**, not blind automation. Low-confidence or rule-failing
  fields are visually flagged with the actual reason, editable inline, before the
  record can be confirmed.
- **Real persistence with tenant isolation.** Every database read and write is scoped
  by a client ID, the same pattern a real multi-tenant system would use, even though
  this build only has one client. Confirmed records and every extraction attempt
  (success or failure, with latency) are both queryable via their own endpoints.
- **Full bilingual support**, not a translated string table bolted on: complete
  layout mirroring for Arabic RTL, tested across every screen and breakpoint.
- **Production hardening that's usually skipped in a demo**: upload content is
  verified by magic bytes (not the trivially-spoofable Content-Type header), a
  per-IP rate limiter guards the LLM endpoint, and a real concurrency bug (a blocking
  LLM call that froze the whole server for other requests) was found and fixed during
  testing, not just claimed as handled.

## Architecture

```
frontend/   React + TypeScript (Vite). Real document preview, live agent trace,
            human-in-the-loop review UI, full English/Arabic RTL support.
backend/    FastAPI. /api/extract runs the agent, /api/confirm re-validates, saves,
            and logs; /api/runs and /api/records expose what got persisted.
  app/agent.py         orchestrates the provider chain + validation + trace + timing
  app/providers/        one module per LLM provider, same extract() interface
  app/validation.py     deterministic business rules (required fields, weight
                         range, category allow-list, date sanity)
  app/db.py              SQLite persistence, every table scoped by client_id
  app/security.py        magic-byte upload verification, per-IP rate limiting
```

### Why a provider chain instead of one hardcoded SDK call

`app/providers/gemini_provider.py` and `app/providers/openrouter_provider.py` both
expose the same `extract(image_bytes, mime_type, model, api_key) -> dict` signature.
`app/agent.py` walks a list of `(name, provider, model)` entries in order and moves to
the next one on any failure, logging each attempt (with per-call latency) into the
visible agent trace. Adding a new provider (Claude, OpenAI, a self-hosted model) is a
new file with the same signature added to the chain, not a rewrite.

**Current chain: Gemini (flash) → Gemini (flash-lite) → OpenRouter (Nemotron VL,
free) → OpenRouter (Gemma, free).** This project runs on free-tier models only.
Groq was tried as a third provider first, but its free tier turned out to have no
vision-capable model, confirmed by testing it against a real image and watching it
reject the request outright. It was replaced with OpenRouter, which aggregates
several providers' free vision-capable models behind one API — verified live, not
just configured, by forcing Gemini to fail and confirming OpenRouter correctly
extracted every field from a real ticket. The two OpenRouter models trade off
differently in practice: Gemma is the stronger general-purpose model on paper but was
consistently rate-limited on the shared free pool during testing, while Nemotron-VL
succeeded immediately — so Nemotron-VL is the primary and Gemma the fallback, a
reliability-over-theoretical-quality call made from real test data, not guesswork.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate   # .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env            # fill in GEMINI_API_KEY and/or OPENROUTER_API_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"   # -> DEMO_API_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> ENCRYPTION_KEY
python ../scripts/generate_sample_tickets.py   # writes test tickets, no real data needed
uvicorn app.main:app --reload --port 8000
```

Gemini: free key at [aistudio.google.com](https://aistudio.google.com). OpenRouter:
free key at [openrouter.ai](https://openrouter.ai), no credit card required.

Every data endpoint requires a bearer token now (see [SECURITY.md](./SECURITY.md)):
generate `DEMO_API_KEY` and `ENCRYPTION_KEY` as shown above and put both in `.env`.

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, expects backend on :8000
```

Copy `.env.example` to `.env` and set `VITE_API_KEY` to the same value as the
backend's `DEMO_API_KEY` (requests without it get a `401`). Set `VITE_API_BASE` too
if the backend runs somewhere other than `http://localhost:8000`.

### Tests

```bash
cd backend
python -m pytest tests/ -v
```

26 tests, all backend logic that matters if it silently breaks: the validation
rules (including that Arabic messages are genuinely different strings, not the
English ones relabeled), the encryption round-trip (reads the raw `.db` file
directly to confirm ciphertext, not just that the API decrypts correctly), the
magic-byte upload check, the rate limiter, and — the most important set — the
access-control regression tests. Those last ones are written directly against the
real vulnerability described in [SECURITY.md](./SECURITY.md): if the header-spoofing
attack that used to work ever starts working again, `test_auth.py` goes red.

## What the UI actually shows

Every visual element that would normally be faked in a mockup was replaced with the
genuine equivalent:

- **Source document panel**: the real uploaded image, not an illustration or a
  decorative "detected region" overlay with no real data behind it. What you see is
  the actual file the agent processed.
- **Live agent trace**: the agent's real trace array (variable length: provider
  attempts, failovers, confidence gate, validation results), revealed step by step,
  each with its real detail text and elapsed time — not a fixed scripted animation.
- **Checks panel**: lists the actual validation rules the agent runs, not placeholder
  copy.
- **Review panel**: editable extracted fields with real per-field confidence bars, a
  real needs-review-vs-passed status derived from the actual response, and real
  validation messages inline on flagged fields.
- **Confirmation receipt**: reference number, timestamp, and ledger date are the real
  database-assigned record ID and real confirmation time.
- **Agent online/offline indicator**: a real health check on load, not a static dot.

## Design

The visual direction is a "tactile instrument" concept: a light aluminum chassis,
hard 2-4px edges, crisp offset shadows, machined-panel details (screw heads, engraved
labels), with orange as the primary/active accent, yellow for states needing
attention, and olive green for verified/online states. Deliberately not a dark
background with a single neon accent, which is a common enough pattern in AI-product
UIs that it reads as a default rather than a considered choice for this brief.

Every text/background color pair was checked against WCAG AA (4.5:1) programmatically,
not eyeballed. Three pairs failed on the first pass: trace-log detail text at 3.61:1
against its "done" row background, the same text at 4.10:1 against the "current" row's
orange background, and the build-edition tag in the top bar at 3.20:1 against the
header background. All three were darkened to pass (4.55-4.76:1) without changing the
palette itself — a targeted fix, not a redesign.

`app/db.py` is a small SQLite layer, two tables (`runs`, `records`), every query
scoped by `client_id`. There's one client configured today, so this isn't a real
multi-tenant system, but the isolation pattern itself is real: every write and every
read filters on `client_id`, the same shape a real per-client schema would use.

Confirmed records are retrievable at `GET /api/records`; every extraction attempt
(successful or not) is logged at `GET /api/runs` with provider, model, latency, and
outcome — real observability on agent runs, not just a log line.

On a free-tier host with an ephemeral filesystem (e.g. Render's free web service),
`intake_agent.db` resets on redeploy; a production deployment would use a managed
Postgres instance instead, which is a one-line swap in `app/db.py`'s connection
function, not a rearchitecture.

## Deployment (free tier)

- **Backend:** `deploy/render.yaml` deploys `backend/` to Render's free web service
  tier. Set `GEMINI_API_KEY` and `OPENROUTER_API_KEY` as secret env vars in the Render
  dashboard (not committed). Update `CORS_ORIGINS` to the deployed frontend URL.
- **Frontend:** `frontend/vercel.json` is ready for Vercel; set `VITE_API_BASE` to the
  Render backend URL as a build-time env var. Cloudflare Pages works the same way with
  its own dashboard env var UI.

A self-hosted deployment (Coolify/Docker on a VPS, matching how a data-residency-
sensitive client platform would actually need to run) is the natural next step; the
free-tier hosting above is a cost substitution, not an architectural ceiling — the
backend is a standard FastAPI app with no platform lock-in.

## Security posture

Full detail, including the honest gaps, lives in [SECURITY.md](./SECURITY.md) —
subprocessor disclosure, the data flow, and what a security review would still
flag. Summary:

- **Access control:** every data endpoint requires `Authorization: Bearer <key>`,
  and `client_id` is resolved server-side from the key, never trusted from a
  client-supplied header. This closed a real isolation gap: the previous version
  trusted an `X-Client-Id` header the caller controlled, so anyone could read another
  client's records by naming a different ID. Verified live — no token, a wrong
  token, and the old header-spoofing approach all now return `401`.
- **Encryption at rest:** `source_name`, `truck_or_driver_id`, and `notes` are
  encrypted with Fernet before being written to SQLite. Verified by reading the raw
  `.db` file directly and confirming the stored value is ciphertext, then confirming
  the authenticated API returns the correct plaintext.
- **Secrets:** API keys live only in `.env` files (gitignored, never committed) or
  the hosting provider's own secret env var store. Never returned in any API response.
- **Input handling:** uploads are capped at 8MB, and the file's actual content is
  checked against its magic bytes (`app/security.py: sniff_mime`) rather than trusting
  the client-supplied Content-Type header, since that header is trivial to spoof.
- **Abuse:** a per-IP rate limiter on `/api/extract` (`app/security.py: RateLimiter`,
  10 req/min). In-memory and per-process — a distributed deployment needs shared
  state (Redis) instead.
- **Data in transit:** TLS terminated by the hosting provider.
- **Concurrency bug caught during testing, not shipped:** the extract route originally
  called the LLM SDK synchronously inside an `async def` handler, which blocked
  FastAPI's whole event loop for every other request while one call was in flight
  (confirmed by watching `/api/health` hang during a real extract call). Fixed by
  running the blocking call through `run_in_threadpool` (`app/main.py`), then
  re-verified the server answers `/api/health` while an extraction is still in flight.
- **Missing-timeout bug caught during testing, not shipped:** the Gemini provider had
  no request timeout, so a slow/unresponsive call could block the entire failover
  chain for close to a minute before giving up and trying the next provider — a real
  measured case took 58.6 seconds total, defeating the point of having a fast
  fallback. Fixed by capping the Gemini call at 15 seconds
  (`app/providers/gemini_provider.py`) and tightening OpenRouter's to 25 seconds,
  then re-verified a normal request still completes in seconds.

## Deliberately out of scope

- **Full multi-tenant auth/RBAC.** API-key authentication is real and closes the
  header-spoofing gap (see Security posture), but it's one shared demo key resolving
  to one client, not per-client keys issued through a real signup/login flow with
  role-based permissions. That's a substantial system of its own, not a natural
  extension of this one.
- **OCR-based text fallback for text-only models.** Would need Tesseract installed on
  the host, which adds deployment fragility disproportionate to what it buys here.

## What's next

- Add Anthropic's Claude API as a provider (same `extract()` interface, new file).
- Move persistence to managed Postgres so records survive redeploys on free hosting.
- Add a lightweight OCR fallback (Tesseract via a Docker build step) so a text-only
  model can serve the extraction path even without a free vision model available.
- Self-host via Coolify/Docker for a deployment with real data-residency guarantees.
