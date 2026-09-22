"""Tests for api/accounts/oauth.py - /v1/auth/social endpoints."""

import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.api
@pytest.mark.auth
class TestOAuthEndpoints:

    async def test_google_missing_credential(self, async_client: AsyncClient):
        """POST /v1/auth/social/google - No credential is rejected."""
        response = await async_client.post("/v1/auth/social/google")
        assert response.status_code == 400

    async def test_google_invalid_credential(self, async_client: AsyncClient):
        """POST /v1/auth/social/google - Invalid credential fails verification."""
        response = await async_client.post("/v1/auth/social/google", params={"credential": "not-a-real-jwt"})
        assert response.status_code == 400

    async def test_facebook_missing_token(self, async_client: AsyncClient):
        """POST /v1/auth/social/facebook - No access token is rejected."""
        response = await async_client.post("/v1/auth/social/facebook")
        assert response.status_code == 400

    async def test_facebook_invalid_token(self, async_client: AsyncClient):
        """POST /v1/auth/social/facebook - Invalid access token fails verification."""
        response = await async_client.post("/v1/auth/social/facebook", params={"access_token": "not-a-real-token"})
        assert response.status_code == 400

    async def test_google_creates_new_user(self, async_client: AsyncClient, mocker):
        """Regression test: creating a new user via Google used to crash - the
        provider's avatar_url couldn't be set on the UserResponse auth_service.create()
        returns, and background_tasks=None broke the verification email send."""
        email = f"google_{uuid4().hex[:8]}@example.com"
        mocker.patch("api.accounts.oauth.verify_google_credential", return_value={
            "email": email, "name": "Ada Lovelace", "picture": "https://example.com/pic.jpg",
        })
        response = await async_client.post("/v1/auth/social/google", params={"credential": "fake-jwt"})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["user"]["email"] == email
        assert data["user"]["verified"] is True
        assert data["user"]["avatar_url"] == "https://example.com/pic.jpg"
        assert "access_token" in data

    async def test_google_logs_in_existing_user(self, async_client: AsyncClient, mocker, test_user):
        """A known email logs in rather than creating a duplicate account."""
        mocker.patch("api.accounts.oauth.verify_google_credential", return_value={
            "email": test_user.email, "name": "Test User",
        })
        response = await async_client.post("/v1/auth/social/google", params={"credential": "fake-jwt"})
        assert response.status_code == 200
        assert response.json()["data"]["user"]["id"] == str(test_user.id)

    async def test_facebook_creates_new_user(self, async_client: AsyncClient, mocker):
        email = f"fb_{uuid4().hex[:8]}@example.com"
        mocker.patch("api.accounts.oauth.get_user_info", return_value={
            "id": "fb123", "email": email, "name": "Ada Lovelace",
        })
        response = await async_client.post("/v1/auth/social/facebook", params={"access_token": "fake-token"})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["user"]["email"] == email
        assert data["user"]["avatar_url"] == "https://graph.facebook.com/fb123/picture?type=large"

    async def test_google_missing_email_is_rejected(self, async_client: AsyncClient, mocker):
        mocker.patch("api.accounts.oauth.verify_google_credential", return_value={"name": "No Email"})
        response = await async_client.post("/v1/auth/social/google", params={"credential": "fake-jwt"})
        assert response.status_code == 400
