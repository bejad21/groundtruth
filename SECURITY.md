# Security and Data Handling

This document describes how the system handles data today, which gaps remain, and what
would close each one.

## Data flow

1. A user uploads an image or PDF to `POST /api/extract`.
2. The file stays in memory, is never written to disk, and is forwarded to one LLM
   provider in the failover chain (see the README's Architecture section).
3. The provider returns structured JSON. The file bytes are discarded when the request
   completes.
4. A human reviews the extracted record and can submit it to `POST /api/confirm`, which
   writes it to the local SQLite database.

## Third-party subprocessors

Each uploaded document is sent to these providers in order until one succeeds:

| Provider | What it receives | Where |
|---|---|---|
| Google Gemini API | Full document image/PDF and the extraction prompt | Google infrastructure, region not pinned by this app |
| OpenRouter (Nemotron 3 Nano Omni, Gemma) | Full document image/PDF and the extraction prompt | Routed to a backend OpenRouter chooses; not disclosed per request |

**Gap: data residency.** Neither provider's processing region is pinned or verifiable
from this codebase, and OpenRouter routes to an undisclosed backend. A deployment that
needs a residency guarantee must use a provider with a signed data-processing agreement
and a pinned region, or a self-hosted model, so documents stay on infrastructure the
operator controls.

## Access control

Every data endpoint (`/api/extract`, `/api/confirm`, `/api/runs`, `/api/records`)
requires `Authorization: Bearer <key>`. `client_id` is resolved server-side from the
key through `CLIENT_API_KEYS` in `app/config.py`, so callers cannot choose it.

An earlier version trusted a client-supplied `X-Client-Id` header, which let anyone read
another client's records by changing it. Requests with no token, a wrong token, or only
that header now return `401`; only a valid key succeeds.

**Gap: shared demo key.** There is one demo key rather than a key per client, and the
frontend ships it in its JS bundle, where anyone can read it. A production deployment
needs per-client keys issued through an authenticated login flow. Full multi-tenant
auth and RBAC are out of scope for this project.

## Encryption

**At rest.** `source_name`, `truck_or_driver_id` and `notes`, the fields most likely to
identify a person, are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before they are
written to SQLite, and decrypted only when returned through an authenticated API call.
Reading the raw `.db` file shows ciphertext, and the API returns the correct plaintext.
`material_type`, `weight_kg` and `delivery_date` are stored in plaintext because they are
operational data that must stay queryable.

If `ENCRYPTION_KEY` is unset, `save_record` in `app/db.py` raises
`EncryptionNotConfiguredError` and `/api/confirm` returns `503` without writing a row.
An earlier version logged a warning and stored the fields in plaintext.

**In transit.** TLS is terminated by the hosting provider (Render, Vercel and Cloudflare
all do this by default). This codebase does not configure or verify it.

**Key management.** The key is a single environment variable, `ENCRYPTION_KEY`, kept in
the host's secret manager. There is no rotation, and losing the key makes existing
encrypted rows unreadable. Production should use a managed KMS (AWS KMS, GCP KMS or
similar) for rotation and recovery.

## Abuse and reliability controls

- Uploads are capped at 8MB and checked against magic bytes, not the client-supplied
  Content-Type (`sniff_mime` in `app/security.py`).
- The extraction endpoint is rate limited per IP (`RateLimiter` in `app/security.py`,
  10 requests per minute). The limiter is in-memory and per-process, so a distributed
  deployment needs shared state such as Redis.
- Every LLM provider call has a timeout (15s Gemini, 25s OpenRouter). Before the timeouts
  were added, a slow Gemini call blocked one request for 58.6 seconds before failing
  over.

## Retention

There is no retention policy. Confirmed records stay in SQLite until deleted manually,
and there is no automatic expiry, export-and-delete flow, or data subject access
process. Define one when a client contract specifies retention terms.

## Known gaps

- No compliance certification (ISO 27001, SOC 2 or similar).
- No incident response plan or named security contact.
- No audit log of who read or exported a record; the `runs` table logs agent activity,
  not human access.
- No data residency guarantee (see Third-party subprocessors).
- No key rotation or secrets-manager integration.
