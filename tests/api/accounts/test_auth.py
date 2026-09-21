"""Tests for api/accounts/auth.py - /v1/auth endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.fixture
async def created_variant(async_client: AsyncClient, admin_headers, sample_product_data):
    cat = await async_client.post("/v1/categories/",
        headers=admin_headers, json={"name": "Cat", "slug": f"cat-{uuid4().hex[:8]}"}
    )
    sample_product_data["category_id"] = cat.json()["data"]["id"]
    product = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    variants = await async_client.get(f"/v1/products/{product.json()['data']['id']}/variants/")
    return variants.json()["data"][0]


@pytest.mark.api
@pytest.mark.auth
class TestAuthEndpoints:

    async def test_register(self, async_client: AsyncClient):
        """POST /v1/auth/register - Register new user."""
        user_data = {
            "email": f"test_{uuid4().hex[:8]}@example.com",
            "password": "SecurePass123!",
            "first_name": "Test",
            "last_name": "User",
            "phone": "+1234567890"
        }
        response = await async_client.post("/v1/auth/register/", json=user_data)
        assert response.status_code in [200, 201]

    async def test_register_duplicate_email(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/register - Duplicate email is rejected."""
        response = await async_client.post("/v1/auth/register/", json={
            "email": test_user.email,
            "password": "SecurePass123!",
            "first_name": "Dup",
            "last_name": "User",
        })
        assert response.status_code == 400

    async def test_login(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/login - User login."""
        login_data = {"email": test_user.email, "password": "TestPassword123!"}
        response = await async_client.post("/v1/auth/login/", json=login_data)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]

    async def test_login_invalid(self, async_client: AsyncClient):
        """POST /v1/auth/login - Invalid credentials."""
        login_data = {"email": "invalid@test.com", "password": "wrong"}
        response = await async_client.post("/v1/auth/login/", json=login_data)
        assert response.status_code == 401

    async def test_login_wrong_password(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/login - Wrong password for an existing account."""
        response = await async_client.post("/v1/auth/login/", json={
            "email": test_user.email, "password": "WrongPassword1!"
        })
        assert response.status_code == 401

    async def test_refresh_token(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/refresh - Refresh access token."""
        login_data = {"email": test_user.email, "password": "TestPassword123!"}
        login_resp = await async_client.post("/v1/auth/login/", json=login_data)
        refresh_token = login_resp.json()["data"]["refresh_token"]

        response = await async_client.post("/v1/auth/refresh/", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        assert "access_token" in response.json()["data"]

    async def test_refresh_token_invalid(self, async_client: AsyncClient):
        """POST /v1/auth/refresh - Invalid refresh token is rejected."""
        response = await async_client.post("/v1/auth/refresh/", json={"refresh_token": "not-a-real-token"})
        assert response.status_code == 401

    async def test_revoke_token(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/revoke - Revoke refresh token."""
        login_data = {"email": test_user.email, "password": "TestPassword123!"}
        login_resp = await async_client.post("/v1/auth/login/", json=login_data)
        refresh_token = login_resp.json()["data"]["refresh_token"]

        response = await async_client.post("/v1/auth/revoke/", params={"refresh_token": refresh_token})
        assert response.status_code == 200

    async def test_logout(self, async_client: AsyncClient, auth_headers):
        """POST /v1/auth/logout - Logout user."""
        response = await async_client.post("/v1/auth/logout/", headers=auth_headers)
        assert response.status_code == 200

    async def test_get_profile(self, async_client: AsyncClient, auth_headers, test_user):
        """GET /v1/auth/me - Get user profile."""
        response = await async_client.get("/v1/auth/me/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["email"] == test_user.email

    async def test_get_profile_unauthorized(self, async_client: AsyncClient):
        """GET /v1/auth/me - No token is rejected."""
        response = await async_client.get("/v1/auth/me/")
        assert response.status_code == 401

    async def test_verify_email_invalid(self, async_client: AsyncClient):
        """GET /v1/auth/verify-email - Verify email with invalid token."""
        response = await async_client.get("/v1/auth/verify-email/", params={"token": "invalid"})
        assert response.status_code in [400, 401, 404]

    async def test_forgot_password(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/forgot-password - Request password reset."""
        response = await async_client.post("/v1/auth/forgot-password/", json={"email": test_user.email})
        assert response.status_code == 200

    async def test_forgot_password_unknown_email(self, async_client: AsyncClient):
        """POST /v1/auth/forgot-password - Unknown email still returns 200 (no account enumeration)."""
        response = await async_client.post("/v1/auth/forgot-password/", json={"email": "nobody@example.com"})
        assert response.status_code == 200

    async def test_resend_verification(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/resend-verification - Resend verification email."""
        response = await async_client.post("/v1/auth/resend-verification/",
            json={"email": test_user.email},
            headers={"X-Resend-Token": "test-token-1234567890123456"}
        )
        assert response.status_code in [200, 400]

    async def test_reset_password_invalid(self, async_client: AsyncClient):
        """POST /v1/auth/reset-password - Reset with invalid token."""
        response = await async_client.post("/v1/auth/reset-password/",
            json={"token": "invalid", "new_password": "NewPass123!"}
        )
        assert response.status_code == 400

    async def test_update_profile(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/auth/me - Update profile."""
        response = await async_client.patch("/v1/auth/me/",
            headers=auth_headers,
            json={"first_name": "Updated", "last_name": "Name"}
        )
        assert response.status_code in [200, 400]

    async def test_change_password(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/auth/me/password - Change password."""
        response = await async_client.patch("/v1/auth/me/password/",
            headers=auth_headers,
            json={"current_password": "TestPassword123!", "new_password": "NewPass123!"}
        )
        assert response.status_code in [200, 400, 422]

    async def test_change_password_wrong_current(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/auth/me/password - Wrong current password is rejected."""
        response = await async_client.patch("/v1/auth/me/password/",
            headers=auth_headers,
            json={"current_password": "NotTheRealPassword1!", "new_password": "NewPass123!"}
        )
        assert response.status_code in [400, 401]

    async def test_login_with_variant_adds_item_to_cart(self, async_client: AsyncClient, test_user, created_variant):
        """POST /v1/auth/login - A variant_id attached to login (from an anonymous add-to-cart) lands in the cart."""
        response = await async_client.post("/v1/auth/login/", json={
            "email": test_user.email, "password": "TestPassword123!",
            "variant_id": created_variant["id"], "quantity": 2
        })
        assert response.status_code == 200
        token = response.json()["data"]["access_token"]

        cart = await async_client.get("/v1/cart/", headers={"Authorization": f"Bearer {token}"})
        items = cart.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["variant_id"] == created_variant["id"]
        assert items[0]["quantity"] == 2

    async def test_login_with_out_of_stock_variant_still_succeeds(self, async_client: AsyncClient, test_user, created_variant):
        """POST /v1/auth/login - An add-to-cart failure (e.g. insufficient stock) must not block login."""
        response = await async_client.post("/v1/auth/login/", json={
            "email": test_user.email, "password": "TestPassword123!",
            "variant_id": created_variant["id"], "quantity": 99999
        })
        assert response.status_code == 200
        assert "access_token" in response.json()["data"]

    async def test_register_with_variant_adds_item_to_cart(self, async_client: AsyncClient, created_variant):
        """POST /v1/auth/register - A variant_id attached to signup lands in the new user's cart after login."""
        email = f"test_{uuid4().hex[:8]}@example.com"
        register_resp = await async_client.post("/v1/auth/register/", json={
            "email": email, "password": "SecurePass123!",
            "first_name": "Test", "last_name": "User",
            "variant_id": created_variant["id"], "quantity": 1
        })
        assert register_resp.status_code in [200, 201]

        login_resp = await async_client.post("/v1/auth/login/", json={"email": email, "password": "SecurePass123!"})
        token = login_resp.json()["data"]["access_token"]

        cart = await async_client.get("/v1/cart/", headers={"Authorization": f"Bearer {token}"})
        items = cart.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["variant_id"] == created_variant["id"]

    async def test_account_lockout_after_failed_logins(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/login - Repeated wrong passwords lock the account (see services/accounts/auth.py)."""
        for _ in range(5):
            await async_client.post("/v1/auth/login/", json={
                "email": test_user.email, "password": "WrongPassword1!"
            })
        response = await async_client.post("/v1/auth/login/", json={
            "email": test_user.email, "password": "TestPassword123!"
        })
        assert response.status_code == 423
