from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Query, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from core.db import get_db
from core.utils.response import Response as APIResponse
from core.errors import APIException
from core.config import settings
from core.logging import get_logger
from schemas.auth import UserCreate, UserLogin, RefreshTokenRequest, ResendVerificationRequest, ForgotPasswordRequest, ResetPasswordRequest
from schemas.user import AddressCreate, AddressUpdate, AddressResponse
from services.auth import AuthService
from services.user import UserService, AddressService
from models.user import User
from uuid import UUID
import time

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_auth_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    return await auth_service.get_current_user(token)


@router.post("/register")
async def register(
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
    try:
        auth_service = AuthService(db)
        user = await auth_service.create_user(user_data, background_tasks)
        return APIResponse(success=True, data=user, message="User registered successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(e)
        )


@router.post("/login")
async def login(
    background_tasks: BackgroundTasks,
    user_login: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login user and return access token."""
    try:
        auth_service = AuthService(db)
        token = await auth_service.authenticate_user(user_login.email, user_login.password, background_tasks)
        logger.info(f"User login successful: {user_login.email}")
        return APIResponse(success=True, data=token, message="Login successful")
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


@router.post("/refresh")
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token."""
    try:
        auth_service = AuthService(db)
        token_data = await auth_service.refresh_access_token(request.refresh_token)
        return APIResponse.success(data=token_data, message="Token refreshed successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message=f"Failed to refresh token - {str(e)}"
        )


@router.post("/revoke")
async def revoke_refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Revoke a refresh token."""
    try:
        auth_service = AuthService(db)
        success = await auth_service.revoke_refresh_token(refresh_token)
        if success:
            return APIResponse.success(message="Refresh token revoked successfully")
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


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_auth_user)
):
    """Logout user."""
    return APIResponse(success=True, message="Logged out successfully")


@router.get("/profile")
async def get_profile(
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
            "age": current_user.age,
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
            "login_count": current_user.login_count,
            "failed_login_attempts": current_user.failed_login_attempts,
            "locked_until": current_user.locked_until.isoformat() if current_user.locked_until else None,
            "stripe_customer_id": current_user.stripe_customer_id,
            "created_at": current_user.created_at.isoformat(),
            "updated_at": current_user.updated_at.isoformat() if current_user.updated_at else None
        }
        return APIResponse.success(data=user_data)
    except Exception as e:
        logger.exception("Failed to get user profile")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to get profile: {str(e)}"
        )


@router.get("/addresses")
async def get_addresses(
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all addresses for the current user."""
    try:
        address_service = AddressService(db)
        addresses = await address_service.get_user_addresses(current_user.id)
        return APIResponse.success(data=[AddressResponse.from_orm(address) for address in addresses])
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch addresses - {str(e)}"
        )


@router.post("/addresses")
async def create_address(
    address_data: AddressCreate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new address for the current user."""
    try:
        address_service = AddressService(db)
        address = await address_service.create_address(
            user_id=current_user.id,
            **address_data.dict()
        )
        return APIResponse.success(data=AddressResponse.from_orm(address), message="Address created successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to create address - {str(e)}"
        )


@router.put("/addresses/{address_id}")
async def update_address(
    address_id: UUID,
    address_data: AddressUpdate,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing address for the current user."""
    try:
        address_service = AddressService(db)
        address = await address_service.update_address(
            address_id=address_id,
            user_id=current_user.id,  # Ensure user owns the address
            **address_data.dict(exclude_unset=True)
        )
        if not address:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND,
                               message="Address not found or not owned by user")
        return APIResponse.success(data=AddressResponse.from_orm(address), message="Address updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to update address - {str(e)}"
        )


@router.delete("/addresses/{address_id}")
async def delete_address(
    address_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an address for the current user."""
    try:
        address_service = AddressService(db)
        # Pass user_id for ownership check
        deleted = await address_service.delete_address(address_id, current_user.id)
        if not deleted:
            raise APIException(status_code=status.HTTP_404_NOT_FOUND,
                               message="Address not found or not owned by user")
        return APIResponse.success(message="Address deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to delete address - {str(e)}"
        )


@router.get("/verify-email")  # Changed to GET as it's typically a link click
async def verify_email(
    token: str = Query(..., description="Verification token"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
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
        await user_service.verify_email(token, background_tasks)
        
        logger.info(f"Email verification successful for token: {token[:20]}...")
        return APIResponse(success=True, message="Email verified successfully")
    except APIException:
        raise

# Simple in-memory rate limiter (in production, use Redis)
_resend_requests = {}
RATE_LIMIT_WINDOW = 300  # 5 minutes
RATE_LIMIT_COUNT = 3    # Max 3 requests per window

@router.post("/resend-verification")
async def resend_verification_email(
    request: ResendVerificationRequest,
    x_resend_token: str = Header(None, description="Resend verification token for security"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db)
):
    """
    Resend verification email to user.
    
    SECURITY: This endpoint should only be called from frontend 
    when user clicks "Resend Verification" button after getting 
    an expired token error.
    
    PROTECTION:
    - Requires 'X-Resend-Token' header from frontend
    - Rate limited: 3 requests per 5 minutes
    - Prevents abuse and automated attacks
    
    - Finds user by email
    - Checks if already verified
    - Generates new verification token
    - Sends new verification email
    
    Returns success even if email doesn't exist (security)
    """
    try:
        # Rate limiting check
        current_time = time.time()
        email_key = request.email.lower()
        
        # Clean old requests
        _resend_requests = {
            email: current_time for email, timestamp in _resend_requests.get(email_key, [])
            if current_time - timestamp < RATE_LIMIT_WINDOW
        }
        
        # Check rate limit
        recent_requests = [
            timestamp for timestamp in _resend_requests[email_key]
            if current_time - timestamp < RATE_LIMIT_WINDOW
        ]
        
        if len(recent_requests) >= RATE_LIMIT_COUNT:
            raise APIException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                message="Too many resend requests. Please try again later."
            )
        
        # Add current request
        _resend_requests[email_key].append(current_time)
        
        # Verify resend token header (additional security)
        if not x_resend_token or len(x_resend_token) < 16:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Invalid request. Please use the resend verification form."
            )
        
        user_service = UserService(db)
        
        # Find user by email
        result = await db.execute(
            select(User).where(User.email == email_key)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            # For security, always return success but don't send email
            return APIResponse(
                success=True, 
                message="If an account exists with this email, a verification email has been sent."
            )
        
        if user.verified:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Email is already verified"
            )
        
        # Generate new token
        import secrets
        from datetime import datetime, timedelta, timezone
        verification_token = secrets.token_urlsafe(32)
        token_expiration = datetime.now(timezone.utc) + timedelta(hours=24)
        
        # Update user with new token
        user.verification_token = verification_token
        user.token_expiration = token_expiration
        await db.commit()
        
        # Send verification email
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={verification_token}"
        
        context = {
            "customer_name": user.firstname,
            "verification_link": verification_link,
            "company_name": "Banwee",
            "expiry_time": "24 hours",
            "current_year": datetime.now(timezone.utc).year,
        }
        
        from core.utils.messages.email import send_email_mailjet_legacy
        await send_email_mailjet_legacy(
            to_email=request.email,
            mail_type='activation',
            context=context
        )
        
        return APIResponse(
            success=True, 
            message="Verification email sent successfully. Please check your inbox."
        )
        
    except APIException:
        raise
    try:
        from datetime import datetime, timedelta
        import secrets
        
        # Find user by email
        result = await db.execute(
            select(User).where(User.email == request.email.lower())
        )
        user = result.scalar_one_or_none()
        
        # Always return success for security (don't reveal if email exists)
        if not user:
            return APIResponse(
                success=True,
                message="If the email exists, a new verification link has been sent."
            )
        
        # Check if user is already verified
        if user.verified:
            return APIResponse(
                success=True,
                message="This email is already verified. You can login now."
            )
        
        # Generate new verification token
        new_token = secrets.token_urlsafe(32)
        new_expiration = datetime.now(timezone.utc) + timedelta(hours=24)
        
        # Update user with new token
        user.verification_token = new_token
        user.token_expiration = new_expiration
        await db.commit()
        
        # Send verification email
        verification_link = f"{settings.FRONTEND_URL}/verify-email?token={new_token}"
        
        context = {
            "customer_name": user.firstname,
            "verification_link": verification_link,
            "company_name": "Banwee",
            "expiry_time": "24 hours",
            "current_year": datetime.now(timezone.utc).year,}
        return APIResponse(
            success=True, 
            message="Verification email sent successfully. Please check your inbox."
        )
        
    except APIException:
        raise
    except Exception as e:
        # Log error but return generic success message for security
        logger.error(f"Error resending verification email: {e}")
        return APIResponse(
            success=True,
            message="If an account exists with this email, a verification email has been sent."
        )


@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Send password reset email."""
    try:
        auth_service = AuthService(db)
        await auth_service.send_password_reset(request.email, background_tasks)
        return APIResponse(success=True, message="Password reset email sent")
    except Exception as e:
        # Always return success for security
        return APIResponse(success=True, message="If the email exists, a reset link has been sent")


@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reset password with token."""
    try:
        auth_service = AuthService(db)
        await auth_service.reset_password(request.token, request.new_password)
        return APIResponse(success=True, message="Password reset successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid or expired reset token"
        )


@router.put("/profile")
async def update_profile(
    user_data: dict,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user profile."""
    try:
        # Update user fields
        for field, value in user_data.items():
            if hasattr(current_user, field) and field not in ['id', 'hashed_password', 'created_at']:
                setattr(current_user, field, value)
        
        await db.commit()
        await db.refresh(current_user)
        
        # Return user data
        user_response = {
            "id": str(current_user.id),
            "email": current_user.email,
            "firstname": current_user.firstname,
            "lastname": current_user.lastname,
            "full_name": f"{current_user.firstname} {current_user.lastname}",
            "age": current_user.age,
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
            "login_count": current_user.login_count,
            "failed_login_attempts": current_user.failed_login_attempts,
            "locked_until": current_user.locked_until.isoformat() if current_user.locked_until else None,
            "stripe_customer_id": current_user.stripe_customer_id,
            "created_at": current_user.created_at.isoformat(),
            "updated_at": current_user.updated_at.isoformat() if current_user.updated_at else None
        }
        
        return APIResponse(success=True, data=user_response, message="Profile updated successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to update profile - {str(e)}"
        )






@router.put("/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Change user password."""
    try:
        auth_service = AuthService(db)
        # Verify current password
        if not auth_service.verify_password(current_password, current_user.hashed_password):
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Current password is incorrect"
            )

        # Update password
        user_service = UserService(db)
        hashed_password = auth_service.get_password_hash(new_password)
        await user_service.update_user(current_user.id, {"hashed_password": hashed_password})

        return APIResponse(success=True, message="Password changed successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to change password - {str(e)}"
        )


