"""
Contact Message Schemas
Pydantic schemas for contact message validation
"""

from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional
from datetime import datetime
from uuid import UUID
from enum import Enum


class MessageStatus(str, Enum):
    """Status of contact message"""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class MessagePriority(str, Enum):
    """Priority level of contact message"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Create(BaseModel):
    """Schema for creating a contact message"""
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    subject: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=10)


class Update(BaseModel):
    """Schema for updating a contact message (admin only)"""
    status: Optional[MessageStatus] = None
    priority: Optional[MessagePriority] = None
    admin_notes: Optional[str] = None
    assigned_to: Optional[UUID] = None


class Response(BaseModel):
    """Schema for contact message response"""
    id: UUID
    name: str
    email: str
    subject: str
    message: str
    status: MessageStatus
    priority: MessagePriority
    admin_notes: Optional[str] = None
    assigned_to: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )


class ListResponse(BaseModel):
    """Schema for paginated contact message list"""
    messages: list[Response]
    total: int
    page: int
    page_size: int
    total_pages: int
