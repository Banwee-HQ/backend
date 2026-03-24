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
from services.auth.auth import AuthService
from models.auth.user import User
from schemas.auth import UserCreate
import secrets
from datetime import datetime, timezone

router = APIRouter(prefix="/auth/social", tags=["OAuth"])

# OAuth provider configurations
OAUTH_PROVIDERS = {
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "user_info_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scope": "openid email profile"
    },
    "facebook": {
        "auth_url": "https://www.facebook.com/v18.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token", 
        "user_info_url": "https://graph.facebook.com/me",
        "scope": "email,public_profile"
    }
}

@router.get("/{provider}/login")
async def oauth_login(provider: str):
    """Initiate OAuth flow by redirecting to provider"""
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider")
    
    provider_config = OAUTH_PROVIDERS[provider]
    
    if provider == "google":
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": f"{settings.FRONTEND_URL}/auth/oauth/{provider}/callback",
            "response_type": "code",
            "scope": provider_config["scope"],
            "access_type": "offline",
            "state": secrets.token_urlsafe(16)
        }
        auth_url = f"{provider_config['auth_url']}?{httpx.QueryParams(params)}"
        
    elif provider == "facebook":
        params = {
            "client_id": settings.FACEBOOK_APP_ID,
            "redirect_uri": f"{settings.FRONTEND_URL}/auth/oauth/{provider}/callback",
            "response_type": "code",
            "scope": provider_config["scope"],
            "state": secrets.token_urlsafe(16)
        }
        auth_url = f"{provider_config['auth_url']}?{httpx.QueryParams(params)}"
    
    return {"auth_url": auth_url}

@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str, 
    code: str, 
    state: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Handle OAuth callback from provider"""
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider")
    
    try:
        # Exchange authorization code for access token
        access_token = await get_access_token(provider, code)
        
        # Get user info from provider
        user_info = await get_user_info(provider, access_token)
        
        # Find or create user
        user = await find_or_create_user(db, provider, user_info)
        
        # Generate JWT tokens (same as regular auth)
        auth_service = AuthService(db)
        
        # Create token data
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active
        }

        # Create access and refresh tokens
        access_token = auth_service.create_access_token(token_data)
        refresh_token = await auth_service.create_refresh_token(token_data)
        
        return {
            "success": True,
            "data": {
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
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"OAuth authentication failed: {str(e)}"
        )

async def get_access_token(provider: str, code: str) -> str:
    """Exchange authorization code for access token"""
    provider_config = OAUTH_PROVIDERS[provider]
    
    if provider == "google":
        data = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": f"{settings.FRONTEND_URL}/auth/oauth/{provider}/callback"
        }
        
    elif provider == "facebook":
        data = {
            "client_id": settings.FACEBOOK_APP_ID,
            "client_secret": settings.FACEBOOK_APP_SECRET,
            "code": code,
            "redirect_uri": f"{settings.FRONTEND_URL}/auth/oauth/{provider}/callback"
        }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(provider_config["token_url"], data=data)
        response.raise_for_status()
        return response.json()["access_token"]

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
    user = await auth_service.create_user(user_data, background_tasks=None)
    
    # Set avatar after user creation
    if avatar_url:
        user.avatar_url = avatar_url
        await db.commit()
    
    return user
