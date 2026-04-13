from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status, Query, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from core.db import get_db
from core.dependencies import get_current_auth_user
from core.utils.response import Response
from core.exceptions import APIException
from core.config import settings
from core.logging import get_structured_logger as get_logger
from schemas.accounts.auth import UserCreate, Login, Refresh, ResendVerification, ForgotPassword, ResetPassword, ChangePassword
from schemas.accounts.user import AddressCreate, AddressUpdate, AddressResponse
from services.accounts.auth import AuthService
from services.accounts.user import UserService
from services.accounts.address import AddressService
from models.accounts.user import User
from uuid import UUID
import time

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register/")
async def register(
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
    try:
        auth_service = AuthService(db)
        user = await auth_service.create(user_data, background_tasks)
        return Response.success(data=user, message="User registered successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(e)
        )


@router.post("/login/")
async def login(
    background_tasks: BackgroundTasks,
    user_login: Login,
    db: AsyncSession = Depends(get_db)
):
    """Login user and return access token."""
    try:
        auth_service = AuthService(db)
        token = await auth_service.authenticate(user_login.email, user_login.password, background_tasks)
        logger.info(f"User login successful: {user_login.email}")
        return Response.success(data=token, message="Login successful")
    except HTTPException as e:
        # Re-raise HTTP exceptions (authentication failures) as-is
        raise e
    except Exception as e:
        # Log system errors but return a generic authentication failure
        logger.error(f"System error during login for {user_login.email}: {str(e)}")
        raise APIException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Invalid credentials"
        )


@router.post("/refresh/")
async def refresh(
    request: Refresh,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token."""
    try:
        auth_service = AuthService(db)
        token_data = await auth_service.refresh_token(request.refresh_token)
        return Response.success(data=token_data, message="Token refreshed successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=f"Failed to refresh token - {str(e)}"
        )


@router.post("/revoke/")
async def revoke(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Revoke a refresh token."""
    try:
        auth_service = AuthService(db)
        success = await auth_service.revoke_token(refresh_token)
        if success:
            return Response.success(message="Refresh token revoked successfully")
        else:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Invalid refresh token"
            )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to revoke token - {str(e)}"
        )


@router.post("/logout/")
async def logout(
    current_user: User = Depends(get_current_auth_user)
):
    """Logout user."""
    return Response.success(message="Logged out successfully")


@router.get("/me/")
async def me(
    current_user: User = Depends(get_current_auth_user)
):
    """Get current user profile."""
    try:
        user_data = {
            "id": str(current_user.id),
            "email": current_user.email,
            "firstname": current_user.firstname,
            "lastname": current_user.lastname,
            "full_name": f"{current_user.firstname} {current_user.lastname}",
            "date_of_birth": current_user.date_of_birth.isoformat() if current_user.date_of_birth else None,
            "gender": current_user.gender,
            "country": current_user.country,
            "language": current_user.language,
            "timezone": current_user.timezone,
            "phone": current_user.phone,
            "phone_verified": current_user.phone_verified,
            "avatar_url": current_user.avatar_url,
            "role": current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role),
            "account_status": current_user.account_status,
            "verification_status": current_user.verification_status,
            "verified": current_user.verified,
            "is_active": current_user.is_active,
            "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
            "last_activity_at": current_user.last_activity_at.isoformat() if current_user.last_activity_at else None,
            "failed_login_attempts": current_user.failed_login_attempts,
            "locked_until": current_user.locked_until.isoformat() if current_user.locked_until else None,
            "stripe_customer_id": current_user.stripe_customer_id,
            "created_at": current_user.created_at.isoformat(),
            "updated_at": current_user.updated_at.isoformat() if current_user.updated_at else None
        }
        return Response.success(data=user_data)
    except Exception as e:
        logger.exception("Failed to get user profile")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to get profile: {str(e)}"
        )

@router.get("/verify-email/")  # Changed to GET as it's typically a link click
async def verify(
    token: str = Query(..., description="Verification token"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db)
):
    """Verify user email with token."""
    try:
        print(f"🔧 DEBUG: Raw token received: '{token}'")
        print(f"🔧 DEBUG: Token length: {len(token)}")
        print(f"🔧 DEBUG: Token type: {type(token)}")
        
        # Handle case where token might be embedded in HTML (frontend issue)
        if token.startswith('<!DOCTYPE') or token.startswith('<!doctype'):
            # Extract token from HTML - look for token parameter in URL
            import re
            # Look for token=...& or token=..." pattern
            token_match = re.search(r'token=([^&"\s]+)', token)
            if token_match:
                token = token_match.group(1)
                print(f"🔧 Debug: Extracted token from HTML: {token}")
            else:
                raise APIException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    message="Invalid verification token format"
                )
        
        print(f"🔧 Debug: Processing verification token: {token}")
        logger.info(f"Email verification attempt with token: {token[:20]}...")
        
        user_service = UserService(db)
        await user_service.verify(token, background_tasks=background_tasks)
        
        logger.info(f"Email verification successful for token: {token[:20]}...")
        return Response.success(message="Email verified successfully")
    except APIException:
        raise

# Simple in-memory rate limiter (in production, use Redis)
_resend_requests = {}
RATE_LIMIT_WINDOW = 300  # 5 minutes
RATE_LIMIT_COUNT = 3    # Max 3 requests per window

@router.post("/resend-verification/")
async def resend(
    request: ResendVerification,
    x_resend_token: str = Header(None, description="Resend verification token for security"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db)
):
    """Resend verification email. Rate-limited to 3 requests per 5 minutes."""
    try:
        current_time = time.time()
        email_key = request.email.lower()

        # Clean expired entries and enforce rate limit
        existing = _resend_requests.get(email_key, [])
        timestamps = [t for t in existing if current_time - t < RATE_LIMIT_WINDOW]
        if len(timestamps) >= RATE_LIMIT_COUNT:
            raise APIException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                               message="Too many resend requests. Please try again later.")
        timestamps.append(current_time)
        _resend_requests[email_key] = timestamps

        # Allow requests without x-resend-token in test/dev environments
        if x_resend_token and len(x_resend_token) < 16:
            raise APIException(status_code=status.HTTP_400_BAD_REQUEST,
                               message="Invalid request. Please use the resend verification form.")

        result = await db.execute(select(User).where(User.email == email_key))
        user = result.scalar_one_or_none()

        if not user:
            return Response.success(message="If an account exists with this email, a verification email has been sent.")

        if user.verified:
            raise APIException(status_code=status.HTTP_400_BAD_REQUEST, message="Email is already verified")

        import secrets
        from datetime import datetime, timedelta, timezone
        token = secrets.token_urlsafe(32)
        user.verification_token = token
        user.token_expiration = datetime.now(timezone.utc) + timedelta(hours=24)
        await db.commit()

        from services.accounts.email import EmailService
        email_service = EmailService(db)
        email_service.send_verification(background_tasks, request.email, user.firstname, token)

        return Response.success(message="Verification email sent successfully. Please check your inbox.")

    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error resending verification email: {e}")
        return Response.success(message="If an account exists with this email, a verification email has been sent.")


@router.post("/forgot-password/")
async def forgot_password(
    request: ForgotPassword,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Send password reset email."""
    try:
        auth_service = AuthService(db)
        await auth_service.send_reset(request.email, background_tasks)
        return Response.success(message="Password reset email sent")
    except Exception as e:
        # Always return success for security
        return Response.success(message="If the email exists, a reset link has been sent")


@router.post("/reset-password/")
async def reset(
    request: ResetPassword,
    db: AsyncSession = Depends(get_db)
):
    """Reset password with token."""
    try:
        auth_service = AuthService(db)
        await auth_service.reset_pwd(request.token, request.new_password)
        return Response.success(message="Password reset successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid or expired reset token"
        )


@router.patch("/me/")
async def update(
    user_data: dict,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user profile."""
    try:
        # Normalize first_name/last_name aliases
        if "first_name" in user_data and "firstname" not in user_data:
            user_data["firstname"] = user_data.pop("first_name")
        if "last_name" in user_data and "lastname" not in user_data:
            user_data["lastname"] = user_data.pop("last_name")

        # Parse date_of_birth string to timezone-aware datetime if needed
        if "date_of_birth" in user_data and isinstance(user_data["date_of_birth"], str):
            from datetime import datetime as dt, timezone
            try:
                parsed = dt.fromisoformat(user_data["date_of_birth"])
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                user_data["date_of_birth"] = parsed
            except ValueError:
                raise APIException(status_code=400, message="Invalid date_of_birth format. Use ISO format: YYYY-MM-DD")

        # Update user fields
        for field, value in user_data.items():
            if hasattr(current_user, field) and field not in ['id', 'hashed_password', 'created_at']:
                setattr(current_user, field, value)
        
        await db.commit()
        await db.refresh(current_user)
        
        # Return user data with both naming conventions
        user_response = {
            "id": str(current_user.id),
            "email": current_user.email,
            "firstname": current_user.firstname,
            "lastname": current_user.lastname,
            "first_name": current_user.firstname,
            "last_name": current_user.lastname,
            "full_name": f"{current_user.firstname} {current_user.lastname}",
            "date_of_birth": current_user.date_of_birth.isoformat() if current_user.date_of_birth else None,
            "gender": current_user.gender,
            "country": current_user.country,
            "language": current_user.language,
            "timezone": current_user.timezone,
            "phone": current_user.phone,
            "phone_verified": current_user.phone_verified,
            "avatar_url": current_user.avatar_url,
            "role": current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role),
            "account_status": current_user.account_status,
            "verification_status": current_user.verification_status,
            "verified": current_user.verified,
            "is_active": current_user.is_active,
            "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
            "last_activity_at": current_user.last_activity_at.isoformat() if current_user.last_activity_at else None,
            "failed_login_attempts": current_user.failed_login_attempts,
            "locked_until": current_user.locked_until.isoformat() if current_user.locked_until else None,
            "stripe_customer_id": current_user.stripe_customer_id,
            "created_at": current_user.created_at.isoformat(),
            "updated_at": current_user.updated_at.isoformat() if current_user.updated_at else None
        }
        
        return Response.success(data=user_response, message="Profile updated successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to update profile - {str(e)}"
        )






@router.patch("/me/password/")
async def password(
    req: Request,
    current_password: str = Query(None),
    new_password: str = Query(None),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password. Accepts JSON body or query params."""
    try:
        # Try to parse JSON body first
        body_curr = None
        body_new = None
        try:
            body = await req.json()
            body_curr = body.get("current_password")
            body_new = body.get("new_password")
        except Exception:
            pass

        curr_pwd = body_curr or current_password or ""
        new_pwd = body_new or new_password or ""

        if not curr_pwd or not new_pwd:
            raise APIException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                message="current_password and new_password are required"
            )

        auth_service = AuthService(db)
        # Verify current password
        if not auth_service.verify_password(curr_pwd, current_user.hashed_password):
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Current password is incorrect"
            )

        # Update password
        user_service = UserService(db)
        hashed_password = auth_service.get_password_hash(new_pwd)
        await user_service.update(current_user.id, {"hashed_password": hashed_password})

        return APIResponse.success(message="Password changed successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to change password - {str(e)}"
        )


@router.delete("/me/")
async def delete(
    password: str,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete user account with password confirmation."""
    try:
        # Verify password before deletion
        auth_service = AuthService(db)
        if not auth_service.verify_password(password, current_user.hashed_password):
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Password is incorrect"
            )

        # Delete user (this will cascade delete related data)
        await db.delete(current_user)
        await db.commit()

        return APIResponse.success(message="Account deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to delete account - {str(e)}"
        )


