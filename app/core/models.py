"""Centralized export of all SQLAlchemy ORM models for Alembic metadata tracking."""

from app.core.database import Base
from app.modules.audit.models import AuditLog
from app.modules.auth.models import RefreshToken, User
from app.modules.availability.models import AvailabilitySlot
from app.modules.consultations.models import BookingEvent, Consultation, IdempotencyKey
from app.modules.doctors.models import Doctor
from app.modules.notifications.models import Notification
from app.modules.payments.models import Payment
from app.modules.prescriptions.models import Prescription
from app.modules.users.models import Profile

__all__ = [
    "Base",
    "User",
    "RefreshToken",
    "Profile",
    "Doctor",
    "AvailabilitySlot",
    "Consultation",
    "IdempotencyKey",
    "BookingEvent",
    "Prescription",
    "Payment",
    "AuditLog",
    "Notification",
]
