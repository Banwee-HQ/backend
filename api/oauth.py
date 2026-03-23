from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from core.db import get_db
from core.config import settings

router = APIRouter()


@router.get("/auth/facebook/callback")
async def facebook_callback(code: str, db: AsyncSession = Depends(get_db)):
    token_url = "https://graph.facebook.com/v12.0/oauth/access_token"
    params = {
        "client_id": settings.FACEBOOK_APP_ID,
        "client_secret": settings.FACEBOOK_APP_SECRET,
        "redirect_uri": f"{settings.FRONTEND_URL}/auth/facebook/callback",
        "code": code,
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(token_url, params=params)
        response.raise_for_status()
        access_token = response.json()["access_token"]

    async with httpx.AsyncClient() as client:
        user_info_response = await client.get(
            "https://graph.facebook.com/me",
            params={"fields": "id,name,email", "access_token": access_token}
        )
        user_info_response.raise_for_status()
        user_data = user_info_response.json()

    return {"message": "Facebook authentication successful", "user": user_data}
