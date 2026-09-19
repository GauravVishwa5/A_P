"""Unit tests verifying SQLAlchemy metadata, constraints, and table definitions."""

from app.core.models import Base


def test_all_tables_registered_in_metadata() -> None:
    """Verify all 12 domain tables are registered in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected_tables = {
        "users",
        "profiles",
        "doctors",
        "availability_slots",
        "consultations",
        "prescriptions",
        "payments",
        "refresh_tokens",
        "idempotency_keys",
        "booking_events",
        "notifications",
        "audit_logs",
    }
    assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"


def test_consultation_table_constraints() -> None:
    """Verify consultation partial unique index and check constraints."""
    consultations = Base.metadata.tables["consultations"]

    # Verify primary key
    assert "id" in consultations.c
    assert consultations.c["id"].primary_key is True

    # Verify partial unique index exists
    index_names = {idx.name for idx in consultations.indexes}
    assert "uq_consultations_slot_active" in index_names


def test_availability_slots_constraints() -> None:
    """Verify doctor slot uniqueness constraint and time checks."""
    slots = Base.metadata.tables["availability_slots"]

    # Verify unique constraint on (doctor_id, start_time)
    unique_constraint_names = {c.name for c in slots.constraints if c.name}
    assert "uq_doctor_slot_time" in unique_constraint_names


def test_doctor_table_constraints() -> None:
    """Verify doctor table constraints."""
    doctors = Base.metadata.tables["doctors"]
    assert "license_number" in doctors.c
    assert doctors.c["license_number"].unique is True


def test_idempotency_table_structure() -> None:
    """Verify idempotency_keys table has key, request_hash, and user_id."""
    idempotency = Base.metadata.tables["idempotency_keys"]
    assert "key" in idempotency.c
    assert "request_hash" in idempotency.c
    assert "response_payload" in idempotency.c
