from sqlalchemy import String, Boolean, Integer, Text, DateTime, ForeignKey, func, Index
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, CHAR_LENGTH, GUID
from core.utils.uuid_utils import uuid7
from datetime import datetime
from typing import Optional
import uuid


class Category(Base):
    """Product category, supporting a simple parent/child tree."""
    __tablename__ = "categories"
    __table_args__ = (
        Index('idx_categories_slug', 'slug'),
        Index('idx_categories_parent_id', 'parent_id'),
        {'schema': 'catalog'}
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    name: Mapped[str] = mapped_column(String(CHAR_LENGTH))
    slug: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("catalog.categories.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="category", lazy="select")

    def to_dict(self, include_children: bool = False) -> dict:
        data = {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_children:
            data["children"] = [child.to_dict(include_children=True) for child in self.children]
        return data
