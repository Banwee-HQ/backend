"""
Complete OAuth Implementation Example
This is what's missing to make OAuth fully functional
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
from core.db import get_db
from core.config import settings
from services.accounts.auth import AuthService
from models.accounts.user import User
from schemas.accounts.user import Create as UserCreate
import secrets
from datetime import datetime, timezone
from core.utils.response import Response

# Also register social login routes for compatibility
router = APIRouter(prefix="/auth/social", tags=["OAuth"])

# OAuth provider configurations
OAUTH_PROVIDERS = {
    "google": {
        "user_info_url": "https://www.googleapis.com/oauth2/v2/userinfo",
    },
    "facebook": {
        "user_info_url": "https://graph.facebook.com/me",
    }
}

@router.post("/google")
async def google_oauth_credential(
    credential: str = None,
    mode: str = "login",
    db: AsyncSession = Depends(get_db)
):
    """Handle Google OAuth credential from client-side (Google Identity Services)"""
    if not credential:
        raise HTTPException(status_code=400, detail="Google credential is required")

    try:
        # Verify Google credential and get user info
        user_info = await verify_google_credential(credential)

        # Find or create user
        user = await find_or_create_user(db, "google", user_info)

        # Generate JWT tokens
        auth_service = AuthService(db)

        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active
        }

        access_token = auth_service.make_access_token(token_data)
        refresh_token = await auth_service.make_refresh_token(token_data)

        return Response.success(data={
            "access_token": access_token,
            "token_type": "bearer",
            "refresh_token": refresh_token,
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "firstname": user.firstname,
                "lastname": user.lastname,
                "phone": user.phone,
                "role": user.role,
                "verified": user.verified,
                "is_active": user.is_active,
                "avatar_url": user.avatar_url,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
        })

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Google authentication failed: {str(e)}"
        )

@router.post("/facebook")
async def facebook_oauth_credential(
    access_token: str = None,
    user_id: str = None,
    mode: str = "login",
    db: AsyncSession = Depends(get_db)
):
    """Handle Facebook OAuth credential from client-side (Facebook Login SDK)"""
    if not access_token:
        raise HTTPException(status_code=400, detail="Facebook access token is required")

    try:
        # Get user info from Facebook using access token
        user_info = await get_user_info("facebook", access_token)

        # Find or create user
        user = await find_or_create_user(db, "facebook", user_info)

        # Generate JWT tokens
        auth_service = AuthService(db)

        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active
        }

        access_token_jwt = auth_service.make_access_token(token_data)
        refresh_token = await auth_service.make_refresh_token(token_data)

        return Response.success(data={
            "access_token": access_token_jwt,
            "token_type": "bearer",
            "refresh_token": refresh_token,
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "firstname": user.firstname,
                "lastname": user.lastname,
                "phone": user.phone,
                "role": user.role,
                "verified": user.verified,
                "is_active": user.is_active,
                "avatar_url": user.avatar_url,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
        })

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Facebook authentication failed: {str(e)}"
        )

async def verify_google_credential(credential: str) -> dict:
    """Verify Google ID token and get user info"""
    import google.auth.transport.requests
    import google.oauth2.id_token

    try:
        # Verify the ID token
        id_info = google.oauth2.id_token.verify_oauth2_token(
            credential,
            google.auth.transport.requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )

        # Extract user info
        return {
            "email": id_info.get("email"),
            "name": id_info.get("name"),
            "picture": id_info.get("picture"),
            "given_name": id_info.get("given_name"),
            "family_name": id_info.get("family_name")
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to verify Google credential: {str(e)}"
        )

async def get_user_info(provider: str, access_token: str) -> dict:
    """Get user information from OAuth provider"""
    provider_config = OAUTH_PROVIDERS[provider]

    if provider == "google":
        params = {"access_token": access_token}

    elif provider == "facebook":
        params = {
            "fields": "id,name,email,picture",
            "access_token": access_token
        }

    async with httpx.AsyncClient() as client:
        response = await client.get(provider_config["user_info_url"], params=params)
        response.raise_for_status()
        return response.json()

async def find_or_create_user(db: AsyncSession, provider: str, user_info: dict) -> User:
    """Find existing user or create new one from OAuth data"""
    # Extract email from provider-specific response
    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not provided by OAuth provider")
    
    # Check if user exists
    result = await db.execute(select(User).where(User.email == email))
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        # Update OAuth info if user exists
        if provider == "google" and user_info.get("picture"):
            existing_user.avatar_url = user_info["picture"]
        elif provider == "facebook":
            # Facebook profile picture URL format
            existing_user.avatar_url = f"https://graph.facebook.com/{user_info['id']}/picture?type=large"
        
        existing_user.last_login = datetime.now(timezone.utc)
        await db.commit()
        return existing_user
    
    # Create new user from OAuth data
    name_parts = user_info.get("name", "").split()
    firstname = name_parts[0] if name_parts else ""
    lastname = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    
    # Set avatar URL
    avatar_url = None
    if provider == "google" and user_info.get("picture"):
        avatar_url = user_info["picture"]
    elif provider == "facebook":
        avatar_url = f"https://graph.facebook.com/{user_info['id']}/picture?type=large"
    
    user_data = UserCreate(
        email=email,
        firstname=firstname,
        lastname=lastname,
        password="",  # No password for OAuth users
        phone_verified=True,  # OAuth users are considered verified
        verification_status="verified"
    )
    
    auth_service = AuthService(db)
    user = await auth_service.create(user_data, background_tasks=None)
    
    # Set avatar after user creation
    if avatar_url:
        user.avatar_url = avatar_url
        await db.commit()
    
    return user
