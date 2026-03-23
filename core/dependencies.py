from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from core.db import get_db
from models.user import User
from services.auth import AuthService
from typing import Optional, Dict, Any, List
from uuid import UUID
from core.utils.uuid_utils import uuid7
from datetime import datetime, timedelta
import asyncio
from core.cache import RedisService, RedisKeyManager
from core.config import settings
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class DistributedLock:
    """
    Individual distributed lock implementation using Redis
    """
    
    def __init__(self, redis_service: RedisService, lock_key: str, timeout: int = 30):
        self.redis_service = redis_service
        self.lock_key = lock_key
        self.timeout = timeout
        self.lock_value = str(uuid7())  # Unique value to identify this lock instance
        self.acquired = False
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.release()
    
    async def acquire(self, blocking: bool = True, timeout: Optional[int] = None) -> bool:
        """
        Acquire the distributed lock
        
        Args:
            blocking: Whether to block until lock is acquired
            timeout: Maximum time to wait for lock (None = use default)
        
        Returns:
            True if lock acquired, False otherwise
        """
        try:
            redis_client = await self.redis_service._get_redis()
            lock_timeout = timeout or self.timeout
            
            if blocking:
                # Blocking acquisition with retry
                start_time = datetime.utcnow()
                while True:
                    # Try to acquire lock with SET NX EX (atomic operation)
                    acquired = await redis_client.set(
                        self.lock_key, 
                        self.lock_value, 
                        nx=True,  # Only set if key doesn't exist
                        ex=lock_timeout  # Expiry time
                    )
                    
                    if acquired:
                        self.acquired = True
                        logger.debug(f"Acquired lock: {self.lock_key}")
                        return True
                    
                    # Check timeout
                    if (datetime.utcnow() - start_time).total_seconds() > lock_timeout:
                        logger.warning(f"Failed to acquire lock within timeout: {self.lock_key}")
                        return False
                    
                    # Wait before retry
                    await asyncio.sleep(0.1)
            else:
                # Non-blocking acquisition
                acquired = await redis_client.set(
                    self.lock_key, 
                    self.lock_value, 
                    nx=True,
                    ex=lock_timeout
                )
                
                if acquired:
                    self.acquired = True
                    logger.debug(f"Acquired lock: {self.lock_key}")
                    return True
                else:
                    logger.debug(f"Failed to acquire lock (non-blocking): {self.lock_key}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error acquiring lock {self.lock_key}: {e}")
            return False
    
    async def release(self) -> bool:
        """
        Release the distributed lock
        Only releases if this instance owns the lock
        """
        try:
            if not self.acquired:
                return True
            
            redis_client = await self.redis_service._get_redis()
            
            # Lua script to ensure we only delete our own lock
            lua_script = """
            if redis.call("GET", KEYS[1]) == ARGV[1] then
                return redis.call("DEL", KEYS[1])
            else
                return 0
            end
            """
            
            result = await redis_client.eval(lua_script, 1, self.lock_key, self.lock_value)
            
            if result:
                self.acquired = False
                logger.debug(f"Released lock: {self.lock_key}")
                return True
            else:
                logger.warning(f"Failed to release lock (not owner): {self.lock_key}")
                return False
                
        except Exception as e:
            logger.error(f"Error releasing lock {self.lock_key}: {e}")
            return False

class RedisDistributedLockService(RedisService):
    """
    Service for managing distributed locks using Redis
    """
    
    def __init__(self):
        super().__init__()
        self.default_timeout = 30  # 30 seconds default lock timeout
    
    def get_inventory_lock(self, variant_id: UUID, timeout: int = 30) -> DistributedLock:
        """Get a distributed lock for inventory operations on a specific variant"""
        lock_key = RedisKeyManager.inventory_lock_key(str(variant_id))
        return DistributedLock(self, lock_key, timeout)
    
    def get_custom_lock(self, lock_name: str, timeout: int = 30) -> DistributedLock:
        """Get a custom distributed lock"""
        lock_key = f"lock:{lock_name}"
        return DistributedLock(self, lock_key, timeout)
    
    async def get_active_locks(self) -> List[Dict[str, Any]]:
        """Get list of all active locks"""
        try:
            redis_client = await self._get_redis()
            locks = []
            
            # Scan for all lock keys
            async for key in redis_client.scan_iter(match="lock:*"):
                key_str = key.decode('utf-8')
                ttl = await redis_client.ttl(key)
                value = await redis_client.get(key)
                
                locks.append({
                    "key": key_str,
                    "value": value.decode('utf-8') if value else None,
                    "ttl": ttl,
                    "expires_at": (datetime.utcnow() + timedelta(seconds=ttl)).isoformat() if ttl > 0 else None
                })
            
            # Also check inventory locks
            async for key in redis_client.scan_iter(match=f"{RedisKeyManager.INVENTORY_LOCK_PREFIX}:*"):
                key_str = key.decode('utf-8')
                ttl = await redis_client.ttl(key)
                value = await redis_client.get(key)
                
                locks.append({
                    "key": key_str,
                    "value": value.decode('utf-8') if value else None,
                    "ttl": ttl,
                    "expires_at": (datetime.utcnow() + timedelta(seconds=ttl)).isoformat() if ttl > 0 else None,
                    "type": "inventory_lock"
                })
            
            return locks
            
        except Exception as e:
            logger.error(f"Error getting active locks: {e}")
            return []
    
    async def force_release_lock(self, lock_key: str) -> bool:
        """Force release a lock (admin function)"""
        try:
            return await self.delete_key(lock_key)
            
        except Exception as e:
            logger.error(f"Error force releasing lock {lock_key}: {e}")
            return False
    
    async def get_lock_stats(self) -> Dict[str, Any]:
        """Get statistics about distributed locks"""
        try:
            active_locks = await self.get_active_locks()
            
            inventory_locks = [lock for lock in active_locks if lock.get("type") == "inventory_lock"]
            custom_locks = [lock for lock in active_locks if lock.get("type") != "inventory_lock"]
            
            return {
                "total_active_locks": len(active_locks),
                "inventory_locks": len(inventory_locks),
                "custom_locks": len(custom_locks),
                "locks": active_locks,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting lock stats: {e}")
            return {
                "total_active_locks": 0,
                "inventory_locks": 0,
                "custom_locks": 0,
                "error": str(e)
            }

async def get_redis_lock_service() -> Optional[RedisDistributedLockService]:
    """Get Redis distributed lock service instance (returns None if Redis unavailable)"""
    try:
        service = RedisDistributedLockService()
        # Test Redis connection
        redis_client = await service._get_redis()
        await redis_client.ping()
        return service
    except Exception as e:
        logger.warning(f"Redis not available, distributed locking disabled: {e}")
        return None

async def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """Get AuthService instance with database session."""
    return AuthService(db)


async def get_inventory_service(
    db: AsyncSession = Depends(get_db),
    lock_service: Optional[RedisDistributedLockService] = Depends(get_redis_lock_service)
):
    """Get inventory service with optional Redis distributed lock service"""
    from services.inventory import InventoryService
    return InventoryService(db, lock_service)


async def get_order_service(
    db: AsyncSession = Depends(get_db),
    lock_service: Optional[RedisDistributedLockService] = Depends(get_redis_lock_service)
):
    """Get order service with optional Redis distributed lock service"""
    from services.orders import OrderService
    return OrderService(db, lock_service)


async def get_current_auth_user(
    auth_service: AuthService = Depends(get_auth_service),
    token: str = Depends(oauth2_scheme)
) -> User:
    """Get current authenticated user with proper error handling"""
    try:
        user = await auth_service.get_current_user(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    """Get current authenticated user"""
    try:
        auth_service = AuthService(db)
        user = await auth_service.get_current_user(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """Get current active user"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require admin role"""
    # Case-insensitive role check
    user_role = (current_user.role or "admin" or "superadmin").lower()
    if user_role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def verify_user_or_admin_access(current_user: User = Depends(get_current_active_user)) -> User:
    """Verify user has access (user or admin)"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active"
        )
    return current_user


async def require_supplier(current_user: User = Depends(get_current_active_user)) -> User:
    """Require supplier role"""
    # Case-insensitive role check
    user_role = (current_user.role or "").lower()
    if user_role not in ["supplier", "admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supplier access required"
        )
    return current_user


async def require_admin_or_supplier(current_user: User = Depends(get_current_active_user)) -> User:
    """Require Admin or Supplier role"""
    # Case-insensitive role check
    user_role = (current_user.role or "").lower()
    if user_role not in ["admin", "supplier", "superadmin", "manager"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Supplier access required"
        )
    return current_user
