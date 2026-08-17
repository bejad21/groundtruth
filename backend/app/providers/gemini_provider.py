import json

from .common import CONFIDENCE_FIELDS, FIELD_CONFIDENCE_SCHEMA, RECORD_PROPERTIES, SYSTEM_PROMPT, ProviderError

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        **RECORD_PROPERTIES,
        "field_confidences": FIELD_CONFIDENCE_SCHEMA,
    },
    "required": [*RECORD_PROPERTIES.keys(), "field_confidences"],
}


def extract(image_bytes: bytes, mime_type: str, model: str, api_key: str) -> dict:
    import google.generativeai as genai  # local import so a missing/broken SDK only breaks this provider

    if not api_key:
        raise ProviderError("Gemini API key is not configured.")

    try:
        genai.configure(api_key=api_key)
        gen_model = genai.GenerativeModel(model_name=model, system_instruction=SYSTEM_PROMPT)
        response = gen_model.generate_content(
            [
                {"mime_type": mime_type, "data": image_bytes},
                "Extract the intake record from this ticket and call submit with the structured fields.",
            ],
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA,
                "temperature": 0.1,
            },
            request_options={"timeout": 15},
        )
    except Exception as exc:  # noqa: BLE001 - normalized into ProviderError for the orchestrator
        raise ProviderError(f"Gemini request failed: {exc}") from exc

    text = getattr(response, "text", None)
    if not text:
        raise ProviderError("Gemini returned an empty response.")

    try:
        args = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Gemini returned malformed JSON: {exc}") from exc

    if not all(field in args.get("field_confidences", {}) for field in CONFIDENCE_FIELDS):
        raise ProviderError("Gemini response is missing field confidences.")

    return args
