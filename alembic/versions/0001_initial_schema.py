"""0001_initial_schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="PATIENT"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_secret", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("role IN ('PATIENT', 'DOCTOR', 'ADMIN')", name="chk_user_role"),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=True)

    # 2. profiles
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("phone_number", sa.String(length=32), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(length=32), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_profiles_user_id", "profiles", ["user_id"], unique=True)

    # 3. doctors
    op.create_table(
        "doctors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("specialization", sa.String(length=100), nullable=False),
        sa.Column("license_number", sa.String(length=100), nullable=False),
        sa.Column("experience_years", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consultation_fee", sa.Numeric(10, 2), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("languages", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("rating", sa.Numeric(3, 2), nullable=False, server_default="5.00"),
        sa.Column("total_reviews", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("consultation_fee >= 0", name="chk_doctor_fee"),
        sa.CheckConstraint("experience_years >= 0", name="chk_doctor_experience"),
    )
    op.create_index("idx_doctors_user_id", "doctors", ["user_id"], unique=True)
    op.create_index("idx_doctors_license", "doctors", ["license_number"], unique=True)
    op.create_index("idx_doctors_specialization", "doctors", ["specialization"])
    op.create_index("idx_doctors_fee", "doctors", ["consultation_fee"])
    op.create_index("idx_doctors_rating", "doctors", ["rating"])

    # 4. availability_slots
    op.create_table(
        "availability_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "doctor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("doctors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="AVAILABLE"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("end_time > start_time", name="chk_slot_time"),
        sa.CheckConstraint(
            "status IN ('AVAILABLE', 'HELD', 'BOOKED', 'CANCELLED')", name="chk_slot_status"
        ),
        sa.UniqueConstraint("doctor_id", "start_time", name="uq_doctor_slot_time"),
    )
    op.create_index("idx_slots_doctor_start", "availability_slots", ["doctor_id", "start_time"])
    op.create_index("idx_slots_status", "availability_slots", ["status"])

    # 5. consultations
    op.create_table(
        "consultations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=False
        ),
        sa.Column(
            "availability_slot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("availability_slots.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="SCHEDULED"),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("meeting_reference", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("scheduled_end > scheduled_start", name="chk_consultation_time"),
        sa.CheckConstraint(
            "status IN ('SCHEDULED', 'CONFIRMED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="chk_consultation_status",
        ),
    )
    # Partial unique index ensuring strictly one active consultation per slot
    op.create_index(
        "uq_consultations_slot_active",
        "consultations",
        ["availability_slot_id"],
        unique=True,
        postgresql_where=sa.text("status != 'CANCELLED'"),
    )
    op.create_index("idx_consultations_patient", "consultations", ["patient_id", "scheduled_start"])
    op.create_index("idx_consultations_doctor", "consultations", ["doctor_id", "scheduled_start"])
    op.create_index("idx_consultations_status", "consultations", ["status"])

    # 6. prescriptions
    op.create_table(
        "prescriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consultation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consultations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id"), nullable=False
        ),
        sa.Column(
            "patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("diagnosis", sa.Text(), nullable=False),
        sa.Column("medications", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "idx_prescriptions_consultation", "prescriptions", ["consultation_id"], unique=True
    )
    op.create_index("idx_prescriptions_patient", "prescriptions", ["patient_id", "created_at"])

    # 7. payments
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consultation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consultations.id"),
            nullable=False,
        ),
        sa.Column(
            "patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="INITIATED"),
        sa.Column("provider", sa.String(length=64), nullable=False, server_default="MOCK_PAYMENT"),
        sa.Column("transaction_reference", sa.String(length=128), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("amount > 0", name="chk_payment_amount"),
        sa.CheckConstraint(
            "status IN ('INITIATED', 'SUCCESS', 'FAILED', 'REFUNDED')", name="chk_payment_status"
        ),
    )
    op.create_index("idx_payments_consultation", "payments", ["consultation_id", "status"])
    op.create_index("idx_payments_tx_ref", "payments", ["transaction_reference"], unique=True)

    # 8. refresh_tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_refresh_tokens_lookup", "refresh_tokens", ["token_hash", "is_revoked"])
    op.create_index("idx_refresh_tokens_family", "refresh_tokens", ["family_id"])

    # 9. idempotency_keys
    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_idempotency_key_unique", "idempotency_keys", ["key"], unique=True)
    op.create_index("idx_idempotency_lookup", "idempotency_keys", ["key", "user_id"])

    # 10. booking_events
    op.create_table(
        "booking_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "consultation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("consultations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_booking_events_consultation", "booking_events", ["consultation_id"])

    # 11. notifications
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "recipient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="EMAIL"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_notifications_recipient_status", "notifications", ["recipient_id", "status"]
    )

    # 12. audit_logs
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("idx_audit_actor_created", "audit_logs", ["actor_id", "created_at"])
    op.create_index("idx_audit_action_created", "audit_logs", ["action", "created_at"])
    op.create_index("idx_audit_resource", "audit_logs", ["resource_type", "resource_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("notifications")
    op.drop_table("booking_events")
    op.drop_table("idempotency_keys")
    op.drop_table("refresh_tokens")
    op.drop_table("payments")
    op.drop_table("prescriptions")
    op.drop_table("consultations")
    op.drop_table("availability_slots")
    op.drop_table("doctors")
    op.drop_table("profiles")
    op.drop_table("users")
