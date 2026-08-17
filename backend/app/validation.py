from datetime import date

from .models import ALLOWED_MATERIALS, IntakeRecord, ValidationFlag

MIN_PLAUSIBLE_KG = 1
MAX_PLAUSIBLE_KG = 40000  # a large flatbed truck's realistic payload ceiling

REQUIRED_FIELDS = ["material_type", "weight_kg", "source_name", "truck_or_driver_id", "delivery_date"]

FIELD_LABELS = {
    "en": {
        "material_type": "Material type",
        "weight_kg": "Net weight",
        "source_name": "Source / farm",
        "truck_or_driver_id": "Truck / driver ID",
        "delivery_date": "Delivery date",
    },
    "ar": {
        "material_type": "نوع المادة",
        "weight_kg": "الوزن الصافي",
        "source_name": "المصدر / المزرعة",
        "truck_or_driver_id": "معرّف الشاحنة / السائق",
        "delivery_date": "تاريخ التسليم",
    },
}

MESSAGES = {
    "en": {
        "required_missing": lambda field: f"{field} is missing and must be provided before this record can ship.",
        "material_invalid": lambda value: f"'{value}' is not on the allowed material list for this waste stream.",
        "weight_nonpositive": lambda: "Weight must be a positive number.",
        "weight_range": lambda weight: f"Weight {weight}kg is outside the plausible range ({MIN_PLAUSIBLE_KG}-{MAX_PLAUSIBLE_KG}kg) for a single delivery. Double-check the reading.",
        "date_invalid": lambda: "Delivery date could not be parsed as a valid date.",
        "date_future": lambda: "Delivery date is in the future. Confirm this isn't a misread digit.",
    },
    "ar": {
        "required_missing": lambda field: f"{field} غير موجود ويجب إدخاله قبل اعتماد هذا السجل.",
        "material_invalid": lambda value: f"'{value}' ليست ضمن قائمة المواد المعتمدة لهذا النوع من المخلفات.",
        "weight_nonpositive": lambda: "يجب أن يكون الوزن رقماً موجباً.",
        "weight_range": lambda weight: f"الوزن {weight} كجم خارج النطاق المعقول ({MIN_PLAUSIBLE_KG}-{MAX_PLAUSIBLE_KG} كجم) لتسليم واحد. تحقق من القراءة.",
        "date_invalid": lambda: "تعذّر قراءة تاريخ التسليم كتاريخ صالح.",
        "date_future": lambda: "تاريخ التسليم في المستقبل. تأكد أن هذا ليس خطأً في الأرقام.",
    },
}


def _msg(lang: str, key: str, *args) -> str:
    table = MESSAGES.get(lang, MESSAGES["en"])
    return table.get(key, MESSAGES["en"][key])(*args)


def _field_label(lang: str, field_name: str) -> str:
    return FIELD_LABELS.get(lang, FIELD_LABELS["en"]).get(field_name, field_name.replace("_", " "))


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def validate_record(record: IntakeRecord, lang: str = "en") -> list[ValidationFlag]:
    lang = lang if lang in MESSAGES else "en"
    flags: list[ValidationFlag] = []

    for field_name in REQUIRED_FIELDS:
        value = getattr(record, field_name)
        if value in (None, "", 0) and not (field_name == "weight_kg" and value == 0):
            if value is None or value == "":
                flags.append(ValidationFlag(
                    field=field_name,
                    severity="blocking",
                    message=_msg(lang, "required_missing", _field_label(lang, field_name)),
                ))

    if record.material_type and record.material_type not in ALLOWED_MATERIALS:
        flags.append(ValidationFlag(
            field="material_type",
            severity="blocking",
            message=_msg(lang, "material_invalid", record.material_type),
        ))

    if record.weight_kg is not None:
        if record.weight_kg <= 0:
            flags.append(ValidationFlag(
                field="weight_kg",
                severity="blocking",
                message=_msg(lang, "weight_nonpositive"),
            ))
        elif record.weight_kg < MIN_PLAUSIBLE_KG or record.weight_kg > MAX_PLAUSIBLE_KG:
            flags.append(ValidationFlag(
                field="weight_kg",
                severity="warning",
                message=_msg(lang, "weight_range", record.weight_kg),
            ))

    if record.delivery_date:
        parsed = _parse_date(record.delivery_date)
        if parsed is None:
            flags.append(ValidationFlag(
                field="delivery_date",
                severity="blocking",
                message=_msg(lang, "date_invalid"),
            ))
        elif parsed > date.today():
            flags.append(ValidationFlag(
                field="delivery_date",
                severity="warning",
                message=_msg(lang, "date_future"),
            ))

    return flags
