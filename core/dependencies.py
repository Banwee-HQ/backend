"""
Shared FastAPI dependencies used across multiple routers.
"""
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from core.db import get_db
from core.exceptions import APIException
from models.accounts.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


async def get_current_auth_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Authentication - returns None if not authenticated"""
    if not token:
        return None
    try:
        from services.accounts.auth import AuthService
        auth_service = AuthService(db)
        return await auth_service.current_user(token)
    except Exception:
        return None


async def require_auth(
    current_user: Optional[User] = Depends(get_current_auth_user),
) -> User:
    """Raises 401 if user is not authenticated."""
    if current_user is None:
        raise APIException(status_code=401, message="Authentication required")
    return current_user


def require_admin(current_user: User = Depends(get_current_auth_user)) -> User:
    from models.accounts.user import UserRole
    # Convert role to string for comparison since database stores it as string
    user_role_str = str(current_user.role).lower() if current_user.role else ""
    # Get the actual enum values, not the string representation
    allowed_roles_str = [UserRole.ADMIN.value.lower(), UserRole.MANAGER.value.lower()]
    if user_role_str not in allowed_roles_str:
        raise APIException(status_code=403, message="Admin access required")
    return current_user

