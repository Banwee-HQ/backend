from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID


class ReviewUser(BaseModel):
    id: UUID
    firstname: Optional[str] = None
    lastname: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ReviewResponse(BaseModel):
    id: UUID
    rating: int
    comment: Optional[str]
    created_at: datetime
    user: Optional[ReviewUser] = None

    model_config = ConfigDict(from_attributes=True)


class ReviewBase(BaseModel):
    product_id: UUID
    user_id: Optional[UUID] = None  # Will be set by the backend
    # based on current user
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class ReviewCreate(ReviewBase):
    pass


class ReviewUpdate(ReviewBase):
    rating: Optional[int] = Field(None, ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=1000)


class ReviewInDB(ReviewBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)