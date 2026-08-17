import base64
import json

import httpx

from .common import CONFIDENCE_FIELDS, RECORD_PROPERTIES, SYSTEM_PROMPT, ProviderError

API_URL = "https://openrouter.ai/api/v1/chat/completions"

SCHEMA_INSTRUCTIONS = (
    "Respond with ONLY a single JSON object, no markdown fences, no commentary, matching this exact shape:\n"
    "{\n"
    '  "material_type": one of ' + json.dumps(RECORD_PROPERTIES["material_type"]["enum"]) + ",\n"
    '  "weight_kg": number,\n'
    '  "source_name": string,\n'
    '  "truck_or_driver_id": string,\n'
    '  "delivery_date": "YYYY-MM-DD",\n'
    '  "notes": string,\n'
    '  "field_confidences": {"material_type": number, "weight_kg": number, "source_name": number, '
    '"truck_or_driver_id": number, "delivery_date": number}\n'
    "}\n"
    "Confidence values are 0.0-1.0."
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ProviderError("OpenRouter response did not contain a JSON object.")
    return json.loads(text[start : end + 1])


def extract(image_bytes: bytes, mime_type: str, model: str, api_key: str) -> dict:
    if not api_key:
        raise ProviderError("OpenRouter API key is not configured.")

    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + SCHEMA_INSTRUCTIONS},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract the intake record from this ticket."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "Groundtruth",
    }

    try:
        response = httpx.post(API_URL, json=payload, headers=headers, timeout=25)
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPStatusError as exc:
        raise ProviderError(f"OpenRouter request failed: {exc.response.status_code} {exc.response.text}") from exc
    except Exception as exc:  # noqa: BLE001 - normalized into ProviderError for the orchestrator
        raise ProviderError(f"OpenRouter request failed: {exc}") from exc

    choices = body.get("choices") or []
    if not choices:
        raise ProviderError(f"OpenRouter returned no choices: {body}")

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise ProviderError("OpenRouter returned an empty response.")

    try:
        args = _extract_json(content)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"OpenRouter returned malformed JSON: {exc}") from exc

    if not all(field in args.get("field_confidences", {}) for field in CONFIDENCE_FIELDS):
        raise ProviderError("OpenRouter response is missing field confidences.")

    return args
