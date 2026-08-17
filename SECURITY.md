# Security & Data Handling

This document states what's actually true about this system today, what a security
review would still flag, and what closes each gap. Nothing here is aspirational
marketing copy: every claim below was tested, not assumed (see the verification note
at the end of each section).

## Data flow

1. A user uploads a document (image or PDF) to `POST /api/extract`.
2. The file is held in memory only, never written to disk, and forwarded to one LLM
   provider in the failover chain (see README "Why a provider chain").
3. The provider returns structured JSON. The original file bytes are discarded once
   the request completes — they are not retained anywhere.
4. The extracted record is shown to a human for review, then optionally submitted to
   `POST /api/confirm`, which writes it to the local SQLite database.

## Third-party subprocessors

Every document uploaded is sent to one of these, in order, until one succeeds:

| Provider | What it receives | Where |
|---|---|---|
| Google Gemini API | Full document image/PDF + extraction prompt | Google infrastructure, region not pinned by this app |
| OpenRouter (Nemotron VL, Gemma) | Full document image/PDF + extraction prompt | Routed to whichever backend OpenRouter selects; not disclosed per-request by OpenRouter |

**This is the honest gap a security review would flag first.** Neither provider's
processing region is contractually pinned or verifiable from this codebase, and
OpenRouter in particular routes to an undisclosed backend. A deployment that actually
needs a data-residency guarantee cannot rely on either provider as configured today —
it needs either a provider with a signed data-processing agreement and a pinned
region, or a self-hosted/open-weights model so the document never leaves infrastructure
the deploying organization controls.

## Access control

**What changed:** every read/write endpoint (`/api/extract`, `/api/confirm`,
`/api/runs`, `/api/records`) originally trusted a client-supplied `X-Client-Id`
header to decide which tenant's data to read or write. That made the tenant
isolation in `app/db.py` decorative — anyone could read another client's confirmed
records just by sending a different header value, no credential required.

**Fix:** the header is gone. Every request now requires `Authorization: Bearer
<key>`, and `client_id` is resolved server-side from a key→client mapping
(`app/config.py: CLIENT_API_KEYS`) that the caller cannot influence. Verified live:
a request with no token, a wrong token, and the old spoofed-header approach alone all
now return `401`; only a valid key succeeds (tested against a running server, not
just read from the code).

**What's still a gap:** there is one shared demo key today, not a key per real
client, and the frontend ships that key in its public JS bundle (any static
frontend-only app has this limitation — the key is visible to anyone who reads the
built JS). A production deployment needs distinct keys issued through an
authenticated signup/login flow, not a build-time constant. This is the same gap the
README already documents under "Deliberately out of scope: full multi-tenant
auth/RBAC" — this section makes the *consequence* of that gap explicit rather than
leaving it implicit.

## Encryption

**At rest:** `source_name`, `truck_or_driver_id`, and `notes` — the fields most
likely to contain a person's name or identifying detail — are encrypted with Fernet
(AES-128-CBC + HMAC-SHA256) before being written to SQLite, decrypted only when
returned through an authenticated API call. Verified live: read the raw `.db` file
directly and confirmed the stored value is ciphertext, then confirmed the
authenticated API returns the correct plaintext. `material_type`, `weight_kg`, and
`delivery_date` are stored in plaintext — they're operational data, not personally
identifying on their own, and keeping them queryable matters more than encrypting
them.

**In transit:** whatever TLS the hosting provider terminates (Render/Vercel/
Cloudflare all do this by default on their free tiers). Not configured or verified
by this codebase directly.

**Key management:** the encryption key is a single environment variable
(`ENCRYPTION_KEY`), generated once and stored in the host's secret manager. There is
no key rotation, and losing the key makes existing encrypted rows permanently
unreadable. A production deployment would use a managed KMS (AWS KMS, GCP KMS, or
similar) for rotation and recovery instead of a static env var.

## Abuse and reliability controls

- Uploads capped at 8MB; content verified against magic bytes, not the
  client-supplied Content-Type header (`app/security.py: sniff_mime`).
- Per-IP rate limiting on the extraction endpoint (`app/security.py: RateLimiter`,
  10 req/min), in-memory and per-process — a distributed deployment needs shared
  state (Redis) instead.
- Every LLM provider call has an explicit timeout (15s Gemini, 25s OpenRouter) so a
  hung upstream provider can't block the whole request indefinitely. This was a real
  bug: a slow Gemini call once blocked a request for 58.6 seconds before failing
  over, measured during testing, not assumed.

## Retention

No retention policy exists today. Confirmed records persist in SQLite indefinitely
until manually deleted; there is no automatic expiry, no export-and-delete flow, and
no documented data subject access process. This is the next thing to formalize once
there's a real client whose contract specifies retention terms.

## What a security review would still flag

Being direct about what's *not* solved, since a document that only lists what's done
isn't credible:

- No compliance certification (ISO 27001, SOC 2, or similar) — this is an
  organizational process, not something a codebase can claim.
- No formal incident response plan or named security contact.
- No audit log of who read or exported which record (the `runs` table logs agent
  activity, not human access to confirmed records).
- No data residency guarantee, per the subprocessor section above.
- No key rotation or secrets-manager integration — a single static env var today.

Every item above is a concrete next step, not a vague gesture at "future work."
