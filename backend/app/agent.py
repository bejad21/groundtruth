import time

from . import config
from .models import ExtractResponse, FieldConfidence, IntakeRecord, ToolTraceStep
from .providers import gemini_provider, openrouter_provider
from .providers.common import CONFIDENCE_FIELDS, ProviderError
from .validation import validate_record


class AgentError(Exception):
    pass


MAX_ERROR_DETAIL_CHARS = 160


def _summarize_error(exc: Exception) -> str:
    """Providers wrap raw SDK exceptions, which can be many lines of stack/quota detail.
    The trace is a user-facing log, not a debugger, so keep only the first sentence."""
    text = str(exc).replace("\n", " ").strip()
    first_line = text.split(". ")[0].split("\n")[0]
    summary = first_line if first_line else text
    if len(summary) > MAX_ERROR_DETAIL_CHARS:
        summary = summary[: MAX_ERROR_DETAIL_CHARS - 1].rstrip() + "…"
    return summary


PROVIDER_CHAIN = [
    ("gemini", gemini_provider, lambda: config.GEMINI_API_KEY, lambda: config.GEMINI_MODEL),
    ("gemini-lite", gemini_provider, lambda: config.GEMINI_API_KEY, lambda: config.GEMINI_MODEL_FALLBACK),
    ("openrouter", openrouter_provider, lambda: config.OPENROUTER_API_KEY, lambda: config.OPENROUTER_MODEL),
    ("openrouter-vl", openrouter_provider, lambda: config.OPENROUTER_API_KEY, lambda: config.OPENROUTER_MODEL_FALLBACK),
]


class AgentResult:
    def __init__(self, response: ExtractResponse, provider: str, model: str, latency_ms: int):
        self.response = response
        self.provider = provider
        self.model = model
        self.latency_ms = latency_ms


def run_intake_agent(image_bytes: bytes, mime_type: str, lang: str = "en") -> AgentResult:
    run_started = time.monotonic()
    trace: list[ToolTraceStep] = [
        ToolTraceStep(step="document_received", detail=f"Received {len(image_bytes) / 1024:.1f} KB document ({mime_type})."),
    ]

    args: dict | None = None
    used_provider = ""
    used_model = ""
    errors: list[str] = []

    for name, provider, get_key, get_model in PROVIDER_CHAIN:
        key = get_key()
        model = get_model()
        if not key:
            trace.append(ToolTraceStep(step="provider_skip", detail=f"{name}: no API key configured, skipping."))
            continue

        trace.append(ToolTraceStep(step="provider_call", detail=f"Calling {name} ({model}) with a structured extraction request."))
        call_started = time.monotonic()
        try:
            args = provider.extract(image_bytes, mime_type, model, key)
            used_provider, used_model = name, model
            elapsed_ms = int((time.monotonic() - call_started) * 1000)
            trace.append(ToolTraceStep(step="provider_call", detail=f"{name} returned a structured JSON payload ({elapsed_ms}ms)."))
            break
        except ProviderError as exc:
            summary = _summarize_error(exc)
            errors.append(f"{name}: {summary}")
            trace.append(ToolTraceStep(
                step="provider_failover",
                detail=f"{name} failed ({summary}). Falling back to the next provider.",
                status="flagged",
            ))
            continue

    if args is None:
        detail = "; ".join(errors) if errors else "No AI provider is configured (missing API keys)."
        trace.append(ToolTraceStep(step="provider_call", detail=detail, status="error"))
        raise AgentError(detail)

    confidences_raw = args.pop("field_confidences", {})
    record = IntakeRecord(**{k: args.get(k, "") for k in IntakeRecord.model_fields})

    field_confidences = [
        FieldConfidence(field=field, confidence=float(confidences_raw.get(field, 0.5)))
        for field in CONFIDENCE_FIELDS
    ]

    low_confidence_fields = [fc.field for fc in field_confidences if fc.confidence < config.CONFIDENCE_REVIEW_THRESHOLD]
    if low_confidence_fields:
        trace.append(ToolTraceStep(
            step="confidence_gate",
            detail=f"Fields below {config.CONFIDENCE_REVIEW_THRESHOLD:.0%} confidence: {', '.join(low_confidence_fields)}.",
            status="flagged",
        ))
    else:
        trace.append(ToolTraceStep(step="confidence_gate", detail="All fields extracted above the review confidence threshold."))

    rule_flags = validate_record(record, lang)
    for flag in rule_flags:
        trace.append(ToolTraceStep(step="validation", detail=f"[{flag.severity}] {flag.field}: {flag.message}",
                                    status="flagged" if flag.severity == "blocking" else "ok"))
    if not rule_flags:
        trace.append(ToolTraceStep(step="validation", detail="All rule-based validation checks passed."))

    needs_review = bool(low_confidence_fields) or any(f.severity in ("blocking", "warning") for f in rule_flags)
    total_latency_ms = int((time.monotonic() - run_started) * 1000)

    trace.append(ToolTraceStep(
        step="result",
        detail=(f"Record routed to human review (via {used_provider}, {total_latency_ms}ms total)." if needs_review
                else f"Record accepted automatically (via {used_provider}, {total_latency_ms}ms total)."),
        status="flagged" if needs_review else "ok",
    ))

    response = ExtractResponse(
        record=record,
        field_confidences=field_confidences,
        validation_flags=rule_flags,
        needs_review=needs_review,
        trace=trace,
        model=f"{used_provider}:{used_model}",
    )
    return AgentResult(response, used_provider, used_model, total_latency_ms)
