import type { ExtractResponse, IntakeRecord } from '../types';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY ?? '';

// A build-time public key is the honest limit of a frontend-only demo: it stops a
// stray, unauthenticated caller from hitting the backend, but doesn't hide the key
// from someone who reads the shipped JS bundle. A real deployment issues the key
// through an authenticated login instead of shipping it in a static build. Documented
// in SECURITY.md rather than left implicit.
function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  return { ...extra, Authorization: `Bearer ${API_KEY}` };
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    if (!res.ok) return false;
    const body = await res.json();
    return Boolean(body.providers_configured?.gemini || body.providers_configured?.openrouter);
  } catch {
    return false;
  }
}

export async function extractTicket(file: File, lang: 'en' | 'ar'): Promise<ExtractResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/api/extract?lang=${lang}`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `Extraction failed (${res.status})`);
  }
  return res.json();
}

export async function confirmRecord(record: IntakeRecord, runId: number | null, lang: 'en' | 'ar'): Promise<{ record_id: number }> {
  const res = await fetch(`${API_BASE}/api/confirm?lang=${lang}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ record, run_id: runId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(JSON.stringify(body.detail ?? `Confirm failed (${res.status})`));
  }
  return res.json();
}
