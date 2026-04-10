"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from models.accounts.user import User


@pytest.mark.api
@pytest.mark.auth
@pytest.mark.unit
class TestAuthEndpoints:
    """Test authentication endpoints."""

    async def test_register_user(self, async_client: AsyncClient):
        """Test user registration."""
        user_data = {
            "email": "newuser@test.com",
            "password": "SecurePass123!",
            "first_name": "New",
            "last_name": "User",
            "phone": "+1234567890"
        }
        response = await async_client.post("/v1/auth/register", json=user_data)
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_register_duplicate_email(self, async_client: AsyncClient, test_user: User):
        """Test registering with duplicate email."""
        user_data = {
            "email": test_user.email,
            "password": "SecurePass123!",
            "first_name": "Duplicate",
            "last_name": "User"
        }
        response = await async_client.post("/v1/auth/register", json=user_data)
        assert response.status_code in [400, 409]

    async def test_login_success(self, async_client: AsyncClient, test_user: User):
        """Test successful login."""
        login_data = {
            "email": test_user.email,
            "password": "TestPassword123!"
        }
        response = await async_client.post("/v1/auth/login", json=login_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]

    async def test_login_invalid_credentials(self, async_client: AsyncClient):
        """Test login with invalid credentials."""
        login_data = {
            "email": "nonexistent@test.com",
            "password": "WrongPassword123!"
        }
        response = await async_client.post("/v1/auth/login", json=login_data)
        assert response.status_code == 401

    async def test_login_wrong_password(self, async_client: AsyncClient, test_user: User):
        """Test login with wrong password."""
        login_data = {
            "email": test_user.email,
            "password": "WrongPassword123!"
        }
        response = await async_client.post("/v1/auth/login", json=login_data)
        assert response.status_code == 401

    async def test_refresh_token(self, async_client: AsyncClient, test_user: User):
        """Test refreshing access token."""
        # First login to get refresh token
        login_data = {
            "email": test_user.email,
            "password": "TestPassword123!"
        }
        login_response = await async_client.post("/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        refresh_token = login_response.json()["data"]["refresh_token"]

        # Now refresh the token
        refresh_data = {"refresh_token": refresh_token}
        response = await async_client.post("/v1/auth/refresh", json=refresh_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]

    async def test_refresh_invalid_token(self, async_client: AsyncClient):
        """Test refreshing with invalid token."""
        refresh_data = {"refresh_token": "invalid_token"}
        response = await async_client.post("/v1/auth/refresh", json=refresh_data)
        assert response.status_code == 401

    async def test_revoke_token(self, async_client: AsyncClient, test_user: User):
        """Test revoking a refresh token."""
        # First login to get refresh token
        login_data = {
            "email": test_user.email,
            "password": "TestPassword123!"
        }
        login_response = await async_client.post("/v1/auth/login", json=login_data)
        assert login_response.status_code == 200
        refresh_token = login_response.json()["data"]["refresh_token"]

        # Revoke the token
        response = await async_client.post("/v1/auth/revoke", params={"refresh_token": refresh_token})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_forgot_password(self, async_client: AsyncClient, test_user: User):
        """Test forgot password endpoint."""
        data = {"email": test_user.email}
        response = await async_client.post("/v1/auth/forgot-password", json=data)
        # Should return success even if email doesn't exist (security)
        assert response.status_code in [200, 202]

    async def test_forgot_password_nonexistent(self, async_client: AsyncClient):
        """Test forgot password with non-existent email."""
        data = {"email": "nonexistent@test.com"}
        response = await async_client.post("/v1/auth/forgot-password", json=data)
        # Should return success to prevent email enumeration
        assert response.status_code in [200, 202]

    async def test_verify_email_invalid_token(self, async_client: AsyncClient):
        """Test email verification with invalid token."""
        response = await async_client.get("/v1/auth/verify-email", params={"token": "invalid_token"})
        assert response.status_code in [400, 401, 404]

    async def test_resend_verification(self, async_client: AsyncClient, test_user: User):
        """Test resending verification email."""
        data = {"email": test_user.email}
        response = await async_client.post("/v1/auth/resend-verification", json=data)
        assert response.status_code in [200, 202]


@pytest.mark.api
@pytest.mark.auth
@pytest.mark.unit
class TestOAuthEndpoints:
    """Test OAuth endpoints."""

    async def test_oauth_google_login(self, async_client: AsyncClient):
        """Test Google OAuth login URL."""
        response = await async_client.get("/v1/oauth/google")
        # Should redirect or return auth URL
        assert response.status_code in [200, 307, 302]

    async def test_oauth_facebook_login(self, async_client: AsyncClient):
        """Test Facebook OAuth login URL."""
        response = await async_client.get("/v1/oauth/facebook")
        # Should redirect or return auth URL
        assert response.status_code in [200, 307, 302]

    async def test_oauth_callback_google_invalid(self, async_client: AsyncClient):
        """Test Google OAuth callback with invalid code."""
        response = await async_client.get("/v1/oauth/callback/google", params={"code": "invalid"})
        assert response.status_code in [400, 401]
