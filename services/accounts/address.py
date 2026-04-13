from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, func, text
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from uuid import UUID
from core.utils.uuid_utils import uuid7
from models.accounts.user import Address, User
from models.commerce.orders import Order
from core.exceptions import APIException
from schemas.accounts.user import Create as UserCreate, Update as UserUpdate
from datetime import datetime, timedelta, timezone
import secrets
from core.utils.messages.email import send_email
import httpx
from core.config import settings
from core.utils.encryption import PasswordManager
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class AddressService:
    """Service layer for managing user addresses."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # -----------------------------------------------------------
    # CRUD OPERATIONS
    # -----------------------------------------------------------

    async def create(
        self,
        user_id: UUID,
        street: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        post_code: Optional[str] = None,
        **kwargs
    ) -> Address:
        """Create a new address for a user."""
        address = Address(
            id=uuid7(),
            user_id=user_id,
            street=street or "",
            city=city or "",
            state=state or "",
            country=country or "",
            post_code=post_code or "",
        )
        self.db.add(address)
        await self.db.commit()
        await self.db.refresh(address)
        return address

    async def get(self, address_id: UUID) -> Optional[Address]:
        """Retrieve an address by ID."""
        query = select(Address).where(Address.id == address_id)
        result = await self.db.execute(query)
        return result.scalars().first()

    async def list(self, user_id: UUID, page: int = 1, limit: int = 10) -> Dict[str, Any]:
        """Fetch addresses for a given user with pagination. First = default."""
        offset = (page - 1) * limit
        count_query = select(func.count()).select_from(Address).where(Address.user_id == user_id)
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        query = (
            select(Address)
            .where(Address.user_id == user_id)
            .order_by(Address.created_at.asc())  # oldest first = default
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        addresses = result.scalars().all()
        return {
            "data": addresses,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit if limit else 1
            }
        }

    async def update(self, address_id: UUID, user_id: UUID, **kwargs) -> Optional[Address]:
        """Update address fields dynamically."""
        query = update(Address)
        query = query.where(and_(Address.id == address_id, Address.user_id == user_id))
        query = query.values(**kwargs)
        query = query.execution_options(synchronize_session="fetch")

        await self.db.execute(query)
        await self.db.commit()

        return await self.get(address_id)

    async def delete(self, address_id: UUID, user_id: UUID = None) -> bool:
        """Delete an address by ID."""
        if user_id:
            result = await self.db.execute(delete(Address).where(and_(Address.id == address_id, Address.user_id == user_id)))
        else:
            result = await self.db.execute(delete(Address).where(Address.id == address_id))

        await self.db.commit()
        return result.rowcount > 0

    # -----------------------------------------------------------
    # CUSTOM LOGIC
    # -----------------------------------------------------------

    async def default(self, user_id: UUID) -> Optional[Address]:
        """Get a user's first (default) address."""
        query = select(Address).where(
            Address.user_id == user_id
        ).order_by(Address.created_at.asc())
        result = await self.db.execute(query)
        return result.scalars().first()
