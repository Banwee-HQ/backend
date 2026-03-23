from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from core.db import get_db
from models.user import User
from services.auth import AuthService
from typing import Optional
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# No-op lock service — Redis removed
class NoOpLockService:
    def get_inventory_lock(self, variant_id, timeout=30):
        return _NoOpLock()

    def get_custom_lock(self, lock_name, timeout=30):
        return _NoOpLock()


class _NoOpLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def get_lock_service() -> NoOpLockService:
    return NoOpLockService()


async def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)


async def get_inventory_service(
    db: AsyncSession = Depends(get_db),
    lock_service: NoOpLockService = Depends(get_lock_service)
):
    from services.inventory import InventoryService
    return InventoryService(db, lock_service)


async def get_order_service(
    db: AsyncSession = Depends(get_db),
    lock_service: NoOpLockService = Depends(get_lock_service)
):
    from services.orders import OrderService
    return OrderService(db, lock_service)


async def get_current_auth_user(
    auth_service: AuthService = Depends(get_auth_service),
    token: str = Depends(oauth2_scheme)
) -> User:
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
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
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
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    user_role = (current_user.role or "").lower()
    if user_role not in ["admin", "superadmin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def verify_user_or_admin_access(current_user: User = Depends(get_current_active_user)) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active")
    return current_user


async def require_supplier(current_user: User = Depends(get_current_active_user)) -> User:
    user_role = (current_user.role or "").lower()
    if user_role not in ["supplier", "admin", "superadmin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Supplier access required")
    return current_user


async def require_admin_or_supplier(current_user: User = Depends(get_current_active_user)) -> User:
    user_role = (current_user.role or "").lower()
    if user_role not in ["admin", "supplier", "superadmin", "manager"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or Supplier access required")
    return current_user
