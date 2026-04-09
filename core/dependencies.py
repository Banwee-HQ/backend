"""
Shared FastAPI dependencies used across multiple routers.
"""
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_db
from core.exceptions import APIException
from models.accounts.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


async def get_current_auth_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    from services.accounts.auth import AuthService
    auth_service = AuthService(db)
    return await auth_service.current_user(token)


# Alias used by some routers
async def current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    from services.accounts.auth import AuthService
    auth_service = AuthService(db)
    return await auth_service.current_user(token)


def require_admin(current_user: User = Depends(get_current_auth_user)) -> User:
    from models.accounts.user import UserRole
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise APIException(status_code=403, message="Admin access required")
    return current_user


async def get_current_admin_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    from services.accounts.auth import AuthService
    from models.accounts.user import UserRole
    auth_service = AuthService(db)
    user = await auth_service.current_user(token)
    if user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise APIException(status_code=403, message="Admin access required")
    return user


def get_order_service(db: AsyncSession = Depends(get_db)):
    from services.commerce.orders import OrderService
    return OrderService(db)

# Alias — some routers use get_current_user instead of get_current_auth_user
get_current_user = get_current_auth_user
