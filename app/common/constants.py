"""System-wide enumeration types and constants."""

from enum import StrEnum


class UserRole(StrEnum):
    """User account roles."""

    PATIENT = "PATIENT"
    DOCTOR = "DOCTOR"
    ADMIN = "ADMIN"


class SlotStatus(StrEnum):
    """Doctor availability slot status."""

    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"


class ConsultationStatus(StrEnum):
    """Consultation lifecycle statuses."""

    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    """Financial transaction statuses."""

    INITIATED = "INITIATED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentProvider(StrEnum):
    """Payment gateway provider types."""

    MOCK_PAYMENT = "MOCK_PAYMENT"


class AuditEventType(StrEnum):
    """Compliance and operational audit event types."""

    # Authentication events
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    MFA_CHALLENGE = "MFA_CHALLENGE"
    MFA_VERIFIED = "MFA_VERIFIED"
    LOGOUT = "LOGOUT"
    TOKEN_ROTATED = "TOKEN_ROTATED"
    REFRESH_TOKEN_THEFT_DETECTED = "REFRESH_TOKEN_THEFT_DETECTED"

    # Scheduling & Booking events
    SLOT_CREATED = "SLOT_CREATED"
    SLOT_UPDATED = "SLOT_UPDATED"
    SLOT_DELETED = "SLOT_DELETED"
    CONSULTATION_BOOKED = "CONSULTATION_BOOKED"
    CONSULTATION_CONFIRMED = "CONSULTATION_CONFIRMED"
    CONSULTATION_STARTED = "CONSULTATION_STARTED"
    CONSULTATION_COMPLETED = "CONSULTATION_COMPLETED"
    CONSULTATION_CANCELLED = "CONSULTATION_CANCELLED"

    # Clinical & Financial events
    PRESCRIPTION_ISSUED = "PRESCRIPTION_ISSUED"
    PAYMENT_PROCESSED = "PAYMENT_PROCESSED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED"

    # Security events
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    UNAUTHORIZED_ACCESS_ATTEMPT = "UNAUTHORIZED_ACCESS_ATTEMPT"


class NotificationChannel(StrEnum):
    """Notification delivery channels."""

    EMAIL = "EMAIL"
    SMS = "SMS"
    IN_APP = "IN_APP"


class NotificationStatus(StrEnum):
    """Notification processing status."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
