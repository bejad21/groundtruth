from app.models import IntakeRecord
from app.validation import validate_record

VALID = dict(
    material_type="date_palm_fronds",
    weight_kg=8420,
    source_name="Al Ain Date Farms Co.",
    truck_or_driver_id="DXB-44215 / A. Rahman",
    delivery_date="2026-08-12",
    notes="Standard delivery, no damage",
)


def _record(**overrides) -> IntakeRecord:
    return IntakeRecord(**{**VALID, **overrides})


def test_valid_record_has_no_flags():
    assert validate_record(_record()) == []


def test_missing_required_field_is_blocking():
    flags = validate_record(_record(source_name=""))
    assert len(flags) == 1
    assert flags[0].field == "source_name"
    assert flags[0].severity == "blocking"


def test_material_not_on_allow_list_is_blocking():
    flags = validate_record(_record(material_type="plutonium"))
    assert any(f.field == "material_type" and f.severity == "blocking" for f in flags)


def test_zero_or_negative_weight_is_blocking():
    flags = validate_record(_record(weight_kg=0))
    assert any(f.field == "weight_kg" and f.severity == "blocking" for f in flags)


def test_weight_over_ceiling_is_a_warning_not_blocking():
    flags = validate_record(_record(weight_kg=61500))
    assert len(flags) == 1
    assert flags[0].field == "weight_kg"
    assert flags[0].severity == "warning"


def test_unparseable_date_is_blocking():
    flags = validate_record(_record(delivery_date="not-a-date"))
    assert any(f.field == "delivery_date" and f.severity == "blocking" for f in flags)


def test_future_date_is_a_warning():
    flags = validate_record(_record(delivery_date="2099-01-01"))
    assert any(f.field == "delivery_date" and f.severity == "warning" for f in flags)


def test_messages_localize_to_arabic():
    flags_en = validate_record(_record(weight_kg=61500), lang="en")
    flags_ar = validate_record(_record(weight_kg=61500), lang="ar")
    assert flags_en[0].message != flags_ar[0].message
    assert "61500" in flags_ar[0].message  # the number itself isn't translated, the sentence around it is
    assert any("؀" <= ch <= "ۿ" for ch in flags_ar[0].message)  # contains actual Arabic script


def test_unknown_lang_falls_back_to_english():
    flags = validate_record(_record(weight_kg=61500), lang="fr")
    assert flags[0].message == validate_record(_record(weight_kg=61500), lang="en")[0].message
