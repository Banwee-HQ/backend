from fastapi import APIRouter, Depends, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from core.utils.response import Response
from core.exceptions import APIException
from core.db import get_db
from core.logging import get_structured_logger as get_logger
from services.accounts.user import UserService
from schemas.accounts.user import UserCreate, UserUpdate

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/")
async def create(payload: UserCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Create a new user."""
    service = UserService(db)
    user = await service.create(payload, background_tasks)
    return Response.success(data=user, code=status.HTTP_201_CREATED)


@router.get("/{user_id}")
async def get(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a user by ID."""
    service = UserService(db)
    user = await service.get(user_id)
    if not user:
        raise APIException(
            status_code=status.HTTP_404_NOT_FOUND, message="User not found")
    user_data = {
        "id": str(user.id),
        "email": user.email,
        "firstname": user.firstname,
        "lastname": user.lastname,
        "phone": user.phone,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "account_status": user.account_status,
        "verification_status": user.verification_status,
        "verified": user.verified,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }
    return Response.success(data=user_data)


@router.get("/")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    role: Optional[str] = Query(None, description="Filter by user role"),
    q: Optional[str] = Query(None, description="Search query for user name or email"),
    db: AsyncSession = Depends(get_db)
):
    """List users with optional filtering and pagination."""
    try:
        service = UserService(db)
        users = await service.list(page=page, limit=limit, role=role, query=q)
        if isinstance(users, dict) and "users" in users:
            return Response.success(data=users.get("users", []), pagination=users.get("pagination", {}))
        # Fallback
        return Response.success(data=users)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch users: {str(e)}"
        )


@router.patch("/{user_id}")
async def patch(user_id: UUID, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    """Partially update a user."""
    service = UserService(db)
    updated_user = await service.update(user_id, payload)
    if not updated_user:
        raise APIException(
            status_code=status.HTTP_404_NOT_FOUND, message="User not found")
    user_data = {
        "id": str(updated_user.id),
        "email": updated_user.email,
        "firstname": updated_user.firstname,
        "lastname": updated_user.lastname,
        "phone": updated_user.phone,
        "role": updated_user.role.value if hasattr(updated_user.role, "value") else updated_user.role,
        "account_status": updated_user.account_status,
        "verification_status": updated_user.verification_status,
        "verified": updated_user.verified,
        "is_active": updated_user.is_active,
        "created_at": updated_user.created_at.isoformat() if updated_user.created_at else None,
        "updated_at": updated_user.updated_at.isoformat() if updated_user.updated_at else None,
    }
    return Response.success(data=user_data)


@router.delete("/{user_id}")
async def delete(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a user."""
    service = UserService(db)
    deleted = await service.delete(user_id)
    if not deleted:
        raise APIException(
            status_code=status.HTTP_404_NOT_FOUND, message="User not found")
    return Response.success(message="User deleted successfully")
