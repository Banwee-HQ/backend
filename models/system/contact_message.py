"""
Contact Message Model
Stores customer contact form submissions
"""

from sqlalchemy import String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, datetime as dt
import uuid
import enum
from typing import Optional
from core.db import Base


class MessageStatus(str, enum.Enum):
    """Status of contact message"""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class MessagePriority(str, enum.Enum):
    """Priority level of contact message"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ContactMessage(Base):
    """Contact message model for customer inquiries"""
    __tablename__ = "contact_messages"
    __table_args__ = (
        {'schema': 'system'},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(ENUM('new', 'in_progress', 'resolved', 'closed', name='messagestatus', create_type=False), default='new')
    priority: Mapped[str] = mapped_column(ENUM('low', 'medium', 'high', 'urgent', name='messagepriority', create_type=False), default='medium')
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<ContactMessage {self.id} - {self.subject}>"
