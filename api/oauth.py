from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from core.db import get_db
from core.config import settings

router = APIRouter()


@router.get("/auth/facebook/callback")
async def facebook_callback(code: str, db: AsyncSession = Depends(get_db)):
    # Exchange authorization code for an access token
    token_url = "https://graph.facebook.com/v12.0/oauth/access_token"
    params = {
        "client_id": settings.FACEBOOK_APP_ID,
        "client_secret": settings.FACEBOOK_APP_SECRET,
        # This should match the redirect_uri in your Facebook App settings
        "redirect_uri": "http://localhost:5173/auth/facebook/callback",
        "code": code,
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(token_url, params=params)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data["access_token"]

    # Use the access token to get user information
    user_info_url = "https://graph.facebook.com/me"
    user_info_params = {
        "fields": "id,name,email",
        "access_token": access_token,
    }
    async with httpx.AsyncClient() as client:
        user_info_response = await client.get(user_info_url, params=user_info_params)
        user_info_response.raise_for_status()
        user_data = user_info_response.json()

    # Here you would typically create or log in the user in your database
    # and return a JWT token to the frontend.
    # For now, we'll just return the user data.
    return {"message": "Facebook authentication successful", "user": user_data}


@router.get("/auth/tiktok/callback")
async def tiktok_callback(code: str, db: AsyncSession = Depends(get_db)):
    # Exchange authorization code for an access token
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "client_key": settings.TIKTOK_CLIENT_KEY,
        "client_secret": settings.TIKTOK_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        # This should match the redirect_uri in your TikTok App settings
        "redirect_uri": "http://localhost:5173/auth/tiktok/callback",
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data["access_token"]

    # Use the access token to get user information
    user_info_url = "https://open.tiktokapis.com/v2/user/info/"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    user_info_params = {
        "fields": "open_id,union_id,avatar_url,display_name"
    }
    async with httpx.AsyncClient() as client:
        user_info_response = await client.post(user_info_url, headers=headers, json=user_info_params)
        user_info_response.raise_for_status()
        user_data = user_info_response.json()

    # Here you would typically create or log in the user in your database
    # and return a JWT token to the frontend.
    # For now, we'll just return the user data.
    return {"message": "TikTok authentication successful", "user": user_data}
