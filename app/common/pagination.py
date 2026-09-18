"""Standardized pagination schemas and utility helpers."""

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination query parameter extraction."""

    page: int = Field(default=1, ge=1, description="Page number starting at 1")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page (max 100)")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def get_pagination_params(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> PaginationParams:
    """Dependency provider for pagination parameters."""
    return PaginationParams(page=page, page_size=page_size)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic envelope for paginated results."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(cls, items: list[T], total: int, params: PaginationParams) -> "PaginatedResponse[T]":
        total_pages = (
            (total + params.page_size - 1) // params.page_size if params.page_size > 0 else 0
        )
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            total_pages=total_pages,
        )
