"""Pydantic schemas for Admin business analytics."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class UserAnalytics(BaseModel):
    """Aggregate user distribution and activity metrics."""

    total_users: int = Field(..., description="Total registered accounts")
    total_patients: int = Field(..., description="Total registered patient accounts")
    total_doctors: int = Field(..., description="Total registered doctor accounts")
    active_patients: int = Field(..., description="Active patient accounts")
    active_doctors: int = Field(..., description="Active doctors available for booking")


class ConsultationAnalytics(BaseModel):
    """Aggregate consultation lifecycle distribution metrics."""

    total_consultations: int = Field(..., description="Total consultation bookings created")
    scheduled: int = Field(..., description="Consultations in SCHEDULED status")
    confirmed: int = Field(..., description="Consultations in CONFIRMED status")
    in_progress: int = Field(..., description="Consultations in IN_PROGRESS status")
    completed: int = Field(..., description="Consultations in COMPLETED status")
    cancelled: int = Field(..., description="Consultations in CANCELLED status")
    cancellation_rate_percent: float = Field(
        ..., description="Percentage of total consultations that were cancelled"
    )


class PaymentAnalytics(BaseModel):
    """Aggregate transaction and financial revenue metrics."""

    total_payments: int = Field(..., description="Total payment records initiated")
    successful: int = Field(..., description="Successful payment captures")
    failed: int = Field(..., description="Failed payment transactions")
    initiated: int = Field(..., description="Unresolved or in-flight payment transactions")
    refunded: int = Field(..., description="Fully refunded payments")
    gross_revenue: Decimal = Field(..., description="Total gross captured amount in INR")
    refunded_amount: Decimal = Field(..., description="Total refunded amount in INR")
    net_revenue: Decimal = Field(..., description="Net captured revenue after refunds in INR")
    currency: str = Field(default="INR", description="Standard currency code")


class ClinicalAnalytics(BaseModel):
    """Aggregate clinical documentation metrics."""

    total_prescriptions: int = Field(..., description="Total electronic prescriptions issued")


class AdminAnalyticsResponse(BaseModel):
    """Comprehensive administrative business and platform analytics payload."""

    generated_at: datetime = Field(..., description="UTC timestamp of report generation")
    users: UserAnalytics
    consultations: ConsultationAnalytics
    payments: PaymentAnalytics
    clinical: ClinicalAnalytics
