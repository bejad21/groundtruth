from ..models import ALLOWED_MATERIALS

SYSTEM_PROMPT = (
    "You are an intake clerk agent for a waste-to-worth operations platform. "
    "You are given a photo or scan of a paper delivery/weighbridge ticket for date-palm "
    "agricultural waste. Read the ticket carefully and return the structured record. "
    "If a field is illegible, unclear, or genuinely absent from the document, still "
    "provide your best guess but give it a low confidence score rather than inventing a "
    "clean-looking value with high confidence. Confidence scores must reflect how legible "
    "and unambiguous each field actually was on the source document, not how plausible the "
    "value sounds."
)

CONFIDENCE_FIELDS = ["material_type", "weight_kg", "source_name", "truck_or_driver_id", "delivery_date"]

RECORD_PROPERTIES = {
    "material_type": {"type": "string", "enum": ALLOWED_MATERIALS},
    "weight_kg": {"type": "number"},
    "source_name": {"type": "string"},
    "truck_or_driver_id": {"type": "string"},
    "delivery_date": {"type": "string", "description": "YYYY-MM-DD"},
    "notes": {"type": "string"},
}

FIELD_CONFIDENCE_SCHEMA = {
    "type": "object",
    "properties": {field: {"type": "number"} for field in CONFIDENCE_FIELDS},
    "required": CONFIDENCE_FIELDS,
}


class ProviderError(Exception):
    """Raised when a provider fails to produce a usable structured extraction."""
