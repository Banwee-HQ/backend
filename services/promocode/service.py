from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional
from uuid import UUID
from core.utils.uuid_utils import uuid7
from models.promocode import Promocode
from schemas.promos import PromocodeCreate, PromocodeUpdate
from core.errors import APIException


class PromocodeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_promocode(self, promocode_data: PromocodeCreate) -> Promocode:
        new_promocode = Promocode(
            id=uuid7(),
            **promocode_data.dict(exclude_unset=True)
        )
        self.db.add(new_promocode)
        await self.db.commit()
        await self.db.refresh(new_promocode)
        return new_promocode

    async def get_promocode_by_code(self, code: str) -> Optional[Promocode]:
        result = await self.db.execute(select(Promocode).where(Promocode.code == code, Promocode.is_active == True))
        return result.scalars().first()

    async def get_promocode_by_id(self, promocode_id: UUID) -> Optional[Promocode]:
        result = await self.db.execute(select(Promocode).where(Promocode.id == promocode_id))
        return result.scalars().first()

    async def get_all_promocodes(self) -> List[Promocode]:
        result = await self.db.execute(select(Promocode))
        return result.scalars().all()

    async def update_promocode(self, promocode_id: UUID, promocode_data: PromocodeUpdate) -> Optional[Promocode]:
        promocode = await self.get_promocode_by_id(promocode_id)
        if not promocode:
            raise APIException(status_code=404, message="Promocode not found")

        for key, value in promocode_data.dict(exclude_unset=True).items():
            setattr(promocode, key, value)

        await self.db.commit()
        await self.db.refresh(promocode)
        return promocode

    async def delete_promocode(self, promocode_id: UUID) -> bool:
        promocode = await self.get_promocode_by_id(promocode_id)
        if not promocode:
            return False

        await self.db.delete(promocode)
        await self.db.commit()
        return True

    async def increment_usage(self, promocode_id: UUID) -> Optional[Promocode]:
        """Increment the used_count for a promocode when it's applied"""
        promocode = await self.get_promocode_by_id(promocode_id)
        if not promocode:
            raise APIException(status_code=404, message="Promocode not found")
        
        # Increment usage count
        promocode.used_count = (promocode.used_count or 0) + 1
        
        # Check if usage limit reached and deactivate if needed
        if promocode.usage_limit and promocode.used_count >= promocode.usage_limit:
            promocode.is_active = False
        
        await self.db.commit()
        await self.db.refresh(promocode)
        return promocode
    
    async def validate_promocode(self, code: str) -> tuple[bool, Optional[str], Optional[Promocode]]:
        """
        Validate a promocode and return (is_valid, error_message, promocode)
        """
        from datetime import datetime, timezone
        
        promocode = await self.get_promocode_by_code(code)
        
        if not promocode:
            return False, "Promocode not found", None
        
        if not promocode.is_active:
            return False, "Promocode is not active", None
        
        current_time = datetime.now(timezone.utc)
        
        # Check if promocode has started
        if promocode.valid_from and promocode.valid_from > current_time:
            return False, "Promocode is not yet valid", None
        
        # Check if promocode has expired
        if promocode.valid_until and promocode.valid_until <= current_time:
            return False, "Promocode has expired", None
        
        # Check usage limit
        if promocode.usage_limit and promocode.used_count >= promocode.usage_limit:
            return False, "Promocode usage limit reached", None
        
        return True, None, promocode
