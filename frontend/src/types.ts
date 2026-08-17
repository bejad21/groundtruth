export type Severity = 'blocking' | 'warning';
export type TraceStatus = 'ok' | 'flagged' | 'error';

export interface IntakeRecord {
  material_type: string;
  weight_kg: number | null;
  source_name: string;
  truck_or_driver_id: string;
  delivery_date: string;
  notes: string;
}

export interface FieldConfidence {
  field: string;
  confidence: number;
  reason: string;
}

export interface ValidationFlag {
  field: string;
  severity: Severity;
  message: string;
}

export interface ToolTraceStep {
  step: string;
  detail: string;
  status: TraceStatus;
}

export interface ExtractResponse {
  record: IntakeRecord;
  field_confidences: FieldConfidence[];
  validation_flags: ValidationFlag[];
  needs_review: boolean;
  trace: ToolTraceStep[];
  model: string;
  run_id: number | null;
}

export const RECORD_FIELDS = [
  'material_type',
  'weight_kg',
  'source_name',
  'truck_or_driver_id',
  'delivery_date',
] as const;

export const MATERIAL_OPTIONS = [
  'date_palm_fronds',
  'date_palm_biomass',
  'date_seed_kernels',
  'mixed_agricultural_residue',
  'other_organic_waste',
];
