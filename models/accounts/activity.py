from sqlalchemy import String, DateTime, ForeignKey, func, JSON, Index
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from datetime import datetime
from typing import Optional, Dict, Any
import uuid


class UserActivityLog(Base):
    """Audit trail of significant actions taken on or by a user account."""
    __tablename__ = "user_activity_logs"
    __table_args__ = (
        Index('idx_user_activity_user_id', 'user_id'),
        Index('idx_user_activity_created_at', 'created_at'),
        {'schema': 'accounts'}
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey('accounts.users.id'), nullable=False)
    action: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    performed_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey('accounts.users.id'), nullable=True)
    activity_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    actor = relationship("User", foreign_keys=[performed_by])

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "action": self.action,
            "description": self.description,
            "performed_by": str(self.performed_by) if self.performed_by else None,
            "metadata": self.activity_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
