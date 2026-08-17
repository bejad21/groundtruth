from typing import Literal
from pydantic import BaseModel, Field

ALLOWED_MATERIALS = [
    "date_palm_fronds",
    "date_palm_biomass",
    "date_seed_kernels",
    "mixed_agricultural_residue",
    "other_organic_waste",
]

Severity = Literal["blocking", "warning"]


class IntakeRecord(BaseModel):
    material_type: str = Field(default="")
    weight_kg: float | None = Field(default=None)
    source_name: str = Field(default="")
    truck_or_driver_id: str = Field(default="")
    delivery_date: str = Field(default="")
    notes: str = Field(default="")


class FieldConfidence(BaseModel):
    field: str
    confidence: float
    reason: str = ""


class ValidationFlag(BaseModel):
    field: str
    severity: Severity
    message: str


class ToolTraceStep(BaseModel):
    step: str
    detail: str
    status: Literal["ok", "flagged", "error"] = "ok"


class ExtractResponse(BaseModel):
    record: IntakeRecord
    field_confidences: list[FieldConfidence]
    validation_flags: list[ValidationFlag]
    needs_review: bool
    trace: list[ToolTraceStep]
    model: str
    run_id: int | None = None


class ConfirmRequest(BaseModel):
    record: IntakeRecord
    run_id: int | None = None
