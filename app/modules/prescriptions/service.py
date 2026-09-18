"""Service layer for clinical prescription issuance, immutability, and access control."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.constants import ConsultationStatus, UserRole
from app.common.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.modules.auth.models import User
from app.modules.consultations.repository import ConsultationRepository
from app.modules.doctors.repository import DoctorRepository
from app.modules.prescriptions.models import Prescription
from app.modules.prescriptions.repository import PrescriptionRepository
from app.modules.prescriptions.schemas import (
    PrescriptionCreateRequest,
    PrescriptionResponse,
)


class PrescriptionService:
    """Orchestrates prescription generation, authorization, and retrieval."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PrescriptionRepository(session)
        self.consultation_repo = ConsultationRepository(session)
        self.doctor_repo = DoctorRepository(session)

    async def issue_prescription(
        self,
        consultation_id: UUID,
        request: PrescriptionCreateRequest,
        current_user: User,
    ) -> PrescriptionResponse:
        """Issue an immutable prescription for a consultation (Assigned Doctor only)."""
        if current_user.role != UserRole.DOCTOR.value:
            raise ForbiddenException("Only licensed doctors can issue prescriptions")

        doctor = await self.doctor_repo.get_by_user_id(current_user.id)
        if not doctor:
            raise ForbiddenException("Doctor profile required to issue prescriptions")

        consultation = await self.consultation_repo.get_by_id(consultation_id)
        if not consultation:
            raise NotFoundException("Consultation not found", error_code="CONSULTATION_NOT_FOUND")

        # Invariant: Only the assigned doctor can issue a prescription
        if consultation.doctor_id != doctor.id:
            raise ForbiddenException("You are not the assigned doctor for this consultation")

        # Invariant: Consultation must be IN_PROGRESS or COMPLETED
        if consultation.status not in (
            ConsultationStatus.IN_PROGRESS.value,
            ConsultationStatus.COMPLETED.value,
        ):
            raise BadRequestException(
                "Prescriptions can only be issued for consultations IN_PROGRESS or COMPLETED "
                f"(current: {consultation.status})",
                error_code="INVALID_CONSULTATION_STATUS",
            )

        # Invariant: Prescriptions are immutable and 1-to-1
        existing = await self.repo.get_by_consultation_id(consultation_id)
        if existing:
            raise ConflictException(
                "A prescription has already been issued for this consultation and is immutable",
                error_code="PRESCRIPTION_ALREADY_EXISTS",
            )

        medications_data = [item.model_dump(mode="json") for item in request.medications]

        prescription = Prescription(
            consultation_id=consultation.id,
            doctor_id=doctor.id,
            patient_id=consultation.patient_id,
            diagnosis=request.diagnosis,
            medications=medications_data,
            notes=request.notes,
        )

        try:
            created = await self.repo.create(prescription)
            await self.session.commit()
            return PrescriptionResponse.model_validate(created)
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictException(
                "Prescription already exists for this consultation",
                error_code="PRESCRIPTION_ALREADY_EXISTS",
            ) from exc

    async def get_prescription_by_id(
        self,
        prescription_id: UUID,
        current_user: User,
    ) -> PrescriptionResponse:
        """Retrieve prescription by ID enforcing RBAC and IDOR ownership."""
        prescription = await self.repo.get_by_id(prescription_id)
        if not prescription:
            raise NotFoundException("Prescription not found", error_code="PRESCRIPTION_NOT_FOUND")

        await self._verify_prescription_access(prescription, current_user)
        return PrescriptionResponse.model_validate(prescription)

    async def get_prescription_by_consultation(
        self,
        consultation_id: UUID,
        current_user: User,
    ) -> PrescriptionResponse:
        """Retrieve prescription by consultation ID enforcing RBAC and IDOR ownership."""
        prescription = await self.repo.get_by_consultation_id(consultation_id)
        if not prescription:
            raise NotFoundException(
                "No prescription found for this consultation",
                error_code="PRESCRIPTION_NOT_FOUND",
            )

        await self._verify_prescription_access(prescription, current_user)
        return PrescriptionResponse.model_validate(prescription)

    async def _verify_prescription_access(
        self, prescription: Prescription, current_user: User
    ) -> None:
        """Assert calling actor is the patient, assigned doctor, or system admin."""
        if current_user.role == UserRole.ADMIN.value:
            return

        if current_user.role == UserRole.PATIENT.value:
            if prescription.patient_id != current_user.id:
                raise ForbiddenException("Access denied to requested prescription")
            return

        if current_user.role == UserRole.DOCTOR.value:
            doctor = await self.doctor_repo.get_by_user_id(current_user.id)
            if not doctor or prescription.doctor_id != doctor.id:
                raise ForbiddenException("Access denied to requested prescription")
            return

        raise ForbiddenException("Unauthorized role for prescription access")
