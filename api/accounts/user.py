from fastapi import APIRouter, Depends, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from core.utils.response import Response
from core.exceptions import APIException
from core.db import get_db
from core.logging import get_structured_logger as get_logger
from services.accounts.user import UserService
from schemas.accounts.user import Create as UserCreate, Update as UserUpdate, AdminUserUpdate, UserStatusUpdate
from core.dependencies import get_current_auth_user, require_admin
from models.accounts.user import User as AuthUser, UserRole

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me")
async def me(current_user: AuthUser = Depends(get_current_auth_user)):
    """Get current authenticated user (compat alias)."""
    try:
        user_data = {
            "id": str(current_user.id),
            "email": current_user.email,
            "firstname": current_user.firstname,
            "lastname": current_user.lastname,
            "full_name": f"{current_user.firstname} {current_user.lastname}",
            "phone": current_user.phone,
            "role": current_user.role.value if hasattr(current_user.role, "value") else current_user.role,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        }
        return Response.success(data=user_data)
    except Exception as e:
        raise APIException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, message=str(e))


@router.get("/profile")
async def profile(current_user: AuthUser = Depends(get_current_auth_user)):
    """Alias for profile under /users for legacy clients."""
    return await me(current_user)


@router.post("/")
async def create(payload: UserCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Create a new user."""
    service = UserService(db)
    user = await service.create(payload, background_tasks)
    return Response.success(data=user, code=status.HTTP_201_CREATED)


@router.get("/{user_id}")
async def get(
    user_id: UUID,
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get a user by ID. Admin can get any user, users can only get themselves."""
    # Check if user is admin or requesting their own data
    if current_user.id != user_id:
        raise APIException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="You can only access your own user data"
        )
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
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List users with optional filtering and pagination (admin only)."""
    try:
        service = UserService(db)
        users = await service.get_all_users(
            page=page, limit=limit, role=role, search=search or q, status=status
        )
        return Response.success(data=users)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch users: {str(e)}"
        )


@router.patch("/{user_id}")
async def patch(
    user_id: UUID,
    payload: UserUpdate,
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Partially update a user. Admin can update any user, users can only update themselves."""
    # Check if user is admin or updating their own data
    if current_user.id != user_id:
        raise APIException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="You can only update your own user data"
        )
    # Regular users cannot change role or sensitive fields
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        # Prevent non-admins from changing role, account_status, etc.
        forbidden_fields = ['role', 'account_status', 'verification_status', 'is_active', 'verified']
        update_dict = payload.model_dump(exclude_unset=True)
        for field in forbidden_fields:
            if field in update_dict:
                raise APIException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    message=f"You cannot modify the '{field}' field"
                )
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
async def delete(
    user_id: UUID,
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a user (admin only)."""
    try:
        # Prevent admin from deleting themselves
        if current_user.id == user_id:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="You cannot delete your own account through this endpoint"
            )
        service = UserService(db)
        deleted = await service.delete(user_id)
        if not deleted:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND, message="User not found")
        return Response.success(message="User deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to delete user: {str(e)}")


@router.put("/{user_id}/status")
async def update_status(
    user_id: UUID,
    payload: UserStatusUpdate,
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update user active status (admin only)."""
    try:
        service = UserService(db)
        result = await service.update_status(user_id, payload.is_active)
        return Response.success(data=result, message="User status updated")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to update user status: {str(e)}")


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: UUID,
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Send password reset email to user (admin only)."""
    try:
        service = UserService(db)
        result = await service.reset_password(user_id)
        return Response.success(data=result, message="Password reset email sent")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to reset password: {str(e)}")


@router.post("/{user_id}/deactivate")
async def deactivate(
    user_id: UUID,
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate user account (admin only)."""
    try:
        service = UserService(db)
        result = await service.deactivate(user_id)
        return Response.success(data=result, message="User deactivated")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to deactivate user: {str(e)}")


@router.post("/{user_id}/activate")
async def activate(
    user_id: UUID,
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Activate user account (admin only)."""
    try:
        service = UserService(db)
        result = await service.activate(user_id)
        return Response.success(data=result, message="User activated")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to activate user: {str(e)}")


@router.put("/{user_id}/verify")
async def verify(
    user_id: UUID,
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Verify user account (admin only)."""
    try:
        service = UserService(db)
        result = await service.verify(user_id)
        return Response.success(data=result, message="User verified")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to verify user: {str(e)}")


@router.get("/{user_id}/activity")
async def activity(
    user_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    current_user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get user activity log (admin only)."""
    try:
        service = UserService(db)
        activity = await service.get_activity_log(user_id, page, limit)
        return Response.success(data=activity)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to get user activity: {str(e)}")
