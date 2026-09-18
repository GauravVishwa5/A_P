"""Business logic service for doctor directory and profile management."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ConflictException, NotFoundException
from app.common.pagination import PaginatedResponse, PaginationParams
from app.modules.doctors.models import Doctor
from app.modules.doctors.repository import DoctorRepository
from app.modules.doctors.schemas import DoctorCreateRequest, DoctorResponse, DoctorUpdateRequest


class DoctorService:
    """Service managing doctor profiles, search, and schedule configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.doctor_repo = DoctorRepository(session)

    async def get_doctor_by_id(self, doctor_id: UUID) -> Doctor:
        """Retrieve doctor by ID or raise NotFoundException."""
        doctor = await self.doctor_repo.get_by_id(doctor_id)
        if not doctor:
            raise NotFoundException(
                detail="Doctor profile not found",
                error_code="DOCTOR_NOT_FOUND",
            )
        return doctor

    async def create_doctor_profile(self, user_id: UUID, request: DoctorCreateRequest) -> Doctor:
        """Create new doctor professional profile for user."""
        existing = await self.doctor_repo.get_by_user_id(user_id)
        if existing:
            raise ConflictException(
                detail="Doctor profile already initialized for this account",
                error_code="DOCTOR_PROFILE_EXISTS",
            )

        doctor = Doctor(
            user_id=user_id,
            specialization=request.specialization,
            license_number=request.license_number,
            experience_years=request.experience_years,
            consultation_fee=request.consultation_fee,
            bio=request.bio,
            languages=request.languages,
            rating=Decimal("5.00"),
            total_reviews=0,
            is_available=True,
        )
        created_doctor = await self.doctor_repo.create(doctor)
        await self.session.commit()
        await self.session.refresh(created_doctor)
        return created_doctor

    async def update_my_doctor_profile(self, user_id: UUID, request: DoctorUpdateRequest) -> Doctor:
        """Update calling doctor's profile attributes."""
        doctor = await self.doctor_repo.get_by_user_id(user_id)
        if not doctor:
            raise NotFoundException(
                detail="Doctor profile not found",
                error_code="DOCTOR_PROFILE_NOT_FOUND",
            )

        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(doctor, key, value)

        await self.doctor_repo.update(doctor)
        await self.session.commit()
        await self.session.refresh(doctor)
        return doctor

    async def search_doctors(
        self,
        specialization: str | None,
        max_fee: Decimal | None,
        min_rating: Decimal | None,
        pagination: PaginationParams,
    ) -> PaginatedResponse[DoctorResponse]:
        """Search available doctors with multi-criteria filters and pagination."""
        doctors = await self.doctor_repo.search(
            specialization=specialization,
            max_fee=max_fee,
            min_rating=min_rating,
            limit=pagination.page_size,
            offset=pagination.offset,
        )
        # Convert to response schemas
        items = [DoctorResponse.model_validate(d) for d in doctors]
        # Total approximated by items returned + offset for simplicity
        total = pagination.offset + len(items)
        return PaginatedResponse.create(items=items, total=total, params=pagination)
