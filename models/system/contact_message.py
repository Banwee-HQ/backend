"""
Contact Message Model
Stores customer contact form submissions
"""

from sqlalchemy import String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
import uuid
import enum
from typing import Optional
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7


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
        # Indexes for search and performance
        Index('idx_contact_messages_status', 'status'),
        Index('idx_contact_messages_priority', 'priority'),
        Index('idx_contact_messages_email', 'email'),
        Index('idx_contact_messages_assigned_to', 'assigned_to'),
        Index('idx_contact_messages_created_at', 'created_at'),
        Index('idx_contact_messages_resolved_at', 'resolved_at'),
        # Composite indexes for common queries
        Index('idx_contact_messages_status_priority', 'status', 'priority'),
        Index('idx_contact_messages_status_created', 'status', 'created_at'),
        {'schema': 'system'},
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(ENUM('new', 'in_progress', 'resolved', 'closed', name='messagestatus', create_type=False), default='new')
    priority: Mapped[str] = mapped_column(ENUM('low', 'medium', 'high', 'urgent', name='messagepriority', create_type=False), default='medium')
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    def __repr__(self):
        return f"<ContactMessage {self.id} - {self.subject}>"
