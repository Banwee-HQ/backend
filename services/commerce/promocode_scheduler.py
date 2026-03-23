"""
Promocode Scheduler Service
Handles automatic activation/deactivation of promocodes based on validity dates
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from datetime import datetime, timezone
from typing import Dict, Any, List
from core.logging import get_structured_logger

from models.promocode import Promocode
from core.db import get_db

logger = get_structured_logger(__name__)


class PromoCodeScheduler:
    """Service for managing promocode lifecycle based on validity dates"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def update_promocode_statuses(self) -> Dict[str, Any]:
        """
        Update promocode statuses based on validity dates:
        - Activate promocodes that have reached their valid_from date
        - Deactivate promocodes that have passed their valid_until date
        - Deactivate promocodes that have reached their usage_limit
        """
        current_time = datetime.now(timezone.utc)
        
        activated_count = 0
        deactivated_count = 0
        results = []
        
        try:
            # ========================================
            # STEP 1: Activate promocodes that should be active now
            # ========================================
            # Find inactive promocodes where:
            # - valid_from is in the past (or null)
            # - valid_until is in the future (or null)
            # - usage_limit not reached (or null)
            result = await self.db.execute(
                select(Promocode).where(
                    and_(
                        Promocode.is_active == False,
                        or_(
                            Promocode.valid_from == None,
                            Promocode.valid_from <= current_time
                        ),
                        or_(
                            Promocode.valid_until == None,
                            Promocode.valid_until > current_time
                        ),
                        or_(
                            Promocode.usage_limit == None,
                            Promocode.used_count < Promocode.usage_limit
                        )
                    )
                )
            )
            
            promocodes_to_activate = result.scalars().all()
            
            for promocode in promocodes_to_activate:
                promocode.is_active = True
                activated_count += 1
                results.append({
                    "code": promocode.code,
                    "action": "activated",
                    "reason": "validity period started",
                    "valid_from": promocode.valid_from.isoformat() if promocode.valid_from else None,
                    "valid_until": promocode.valid_until.isoformat() if promocode.valid_until else None
                })
                logger.info(f"✅ Activated promocode: {promocode.code}")
            
            # ========================================
            # STEP 2: Deactivate expired promocodes
            # ========================================
            # Find active promocodes where valid_until has passed
            result = await self.db.execute(
                select(Promocode).where(
                    and_(
                        Promocode.is_active == True,
                        Promocode.valid_until != None,
                        Promocode.valid_until <= current_time
                    )
                )
            )
            
            expired_promocodes = result.scalars().all()
            
            for promocode in expired_promocodes:
                promocode.is_active = False
                deactivated_count += 1
                results.append({
                    "code": promocode.code,
                    "action": "deactivated",
                    "reason": "expired",
                    "valid_until": promocode.valid_until.isoformat() if promocode.valid_until else None
                })
                logger.info(f"❌ Deactivated expired promocode: {promocode.code}")
            
            # ========================================
            # STEP 3: Deactivate promocodes that reached usage limit
            # ========================================
            result = await self.db.execute(
                select(Promocode).where(
                    and_(
                        Promocode.is_active == True,
                        Promocode.usage_limit != None,
                        Promocode.used_count >= Promocode.usage_limit
                    )
                )
            )
            
            limit_reached_promocodes = result.scalars().all()
            
            for promocode in limit_reached_promocodes:
                promocode.is_active = False
                deactivated_count += 1
                results.append({
                    "code": promocode.code,
                    "action": "deactivated",
                    "reason": "usage_limit_reached",
                    "used_count": promocode.used_count,
                    "usage_limit": promocode.usage_limit
                })
                logger.info(f"❌ Deactivated promocode (limit reached): {promocode.code} ({promocode.used_count}/{promocode.usage_limit})")
            
            # ========================================
            # STEP 4: Deactivate promocodes not yet valid
            # ========================================
            result = await self.db.execute(
                select(Promocode).where(
                    and_(
                        Promocode.is_active == True,
                        Promocode.valid_from != None,
                        Promocode.valid_from > current_time
                    )
                )
            )
            
            not_yet_valid_promocodes = result.scalars().all()
            
            for promocode in not_yet_valid_promocodes:
                promocode.is_active = False
                deactivated_count += 1
                results.append({
                    "code": promocode.code,
                    "action": "deactivated",
                    "reason": "not_yet_valid",
                    "valid_from": promocode.valid_from.isoformat() if promocode.valid_from else None
                })
                logger.info(f"❌ Deactivated promocode (not yet valid): {promocode.code}")
            
            # Commit all changes
            await self.db.commit()
            
            logger.info(f"✅ Promocode status update completed: {activated_count} activated, {deactivated_count} deactivated")
            
            return {
                "success": True,
                "activated_count": activated_count,
                "deactivated_count": deactivated_count,
                "total_updated": activated_count + deactivated_count,
                "timestamp": current_time.isoformat(),
                "results": results
            }
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ Failed to update promocode statuses: {e}")
            return {
                "success": False,
                "error": str(e),
                "activated_count": activated_count,
                "deactivated_count": deactivated_count
            }
    
    async def get_active_promocodes(self) -> List[Promocode]:
        """Get all currently active and valid promocodes"""
        current_time = datetime.now(timezone.utc)
        
        result = await self.db.execute(
            select(Promocode).where(
                and_(
                    Promocode.is_active == True,
                    or_(
                        Promocode.valid_from == None,
                        Promocode.valid_from <= current_time
                    ),
                    or_(
                        Promocode.valid_until == None,
                        Promocode.valid_until > current_time
                    ),
                    or_(
                        Promocode.usage_limit == None,
                        Promocode.used_count < Promocode.usage_limit
                    )
                )
            )
        )
        
        return result.scalars().all()
    
    async def get_expired_promocodes(self) -> List[Promocode]:
        """Get all expired promocodes"""
        current_time = datetime.now(timezone.utc)
        
        result = await self.db.execute(
            select(Promocode).where(
                and_(
                    Promocode.valid_until != None,
                    Promocode.valid_until <= current_time
                )
            )
        )
        
        return result.scalars().all()


# Standalone function for background task
async def update_promocode_statuses_task():
    """Background task function to update promocode statuses"""
    async for db in get_db():
        try:
            scheduler = PromoCodeScheduler(db)
            result = await scheduler.update_promocode_statuses()
            logger.info(f"Promocode status update completed: {result}")
            return result
        except Exception as e:
            logger.error(f"Error updating promocode statuses: {e}")
            raise
        finally:
            await db.close()
