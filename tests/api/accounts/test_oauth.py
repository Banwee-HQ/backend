"""Tests for api/accounts/oauth.py - /v1/auth/social endpoints."""

import pytest
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
