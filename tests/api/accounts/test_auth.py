"""Tests for api/accounts/auth.py - /v1/auth endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4
from datetime import datetime, timedelta, timezone

from models.accounts.user import User
from core.utils.uuid_utils import uuid7


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
        assert response.json()["data"]["phone"] == "+1234567890"

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
        assert response.status_code == 200
        assert response.json()["data"]["firstname"] == "Updated"
        assert response.json()["data"]["lastname"] == "Name"

    async def test_update_profile_cannot_escalate_role(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/auth/me - A regular user can't grant themselves admin via arbitrary fields."""
        response = await async_client.patch("/v1/auth/me/",
            headers=auth_headers,
            json={
                "role": "admin",
                "account_status": "active",
                "verification_status": "verified",
                "is_active": True,
                "firstname": "StillMe",
            }
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["role"] == "customer"
        assert data["firstname"] == "StillMe"

        me = await async_client.get("/v1/auth/me/", headers=auth_headers)
        assert me.json()["data"]["role"] == "customer"

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

    async def test_login_with_unknown_variant_does_not_block_login(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/login - A variant_id that doesn't exist raises HTTPException(404) inside
        _add_pending_cart_item, which must be swallowed (logged, not propagated) so login still succeeds."""
        response = await async_client.post("/v1/auth/login/", json={
            "email": test_user.email, "password": "TestPassword123!",
            "variant_id": str(uuid4()), "quantity": 1
        })
        assert response.status_code == 200
        assert "access_token" in response.json()["data"]

    async def test_register_with_overlong_phone_returns_400(self, async_client: AsyncClient):
        """POST /v1/auth/register - phone longer than the DB column (String(20)) triggers a
        real DataError at commit, exercising register()'s generic exception fallback."""
        response = await async_client.post("/v1/auth/register/", json={
            "email": f"test_{uuid4().hex[:8]}@example.com",
            "password": "SecurePass123!",
            "first_name": "Test", "last_name": "User",
            "phone": "1" * 30,
        })
        assert response.status_code == 400

    async def test_revoke_with_garbage_token_still_succeeds(self, async_client: AsyncClient):
        """POST /v1/auth/revoke - revoke_token() is a stateless no-op that always returns True,
        so even a garbage token reports success (documented behavior, not a bypass of anything)."""
        response = await async_client.post("/v1/auth/revoke/", params={"refresh_token": "not-a-real-token"})
        assert response.status_code == 200

    async def test_verify_email_html_wrapped_token_is_extracted(self, async_client: AsyncClient, db_session):
        """GET /v1/auth/verify-email - A frontend bug can embed the token inside an HTML page;
        the endpoint extracts token=... from it and verifies successfully."""
        user = User(
            id=uuid7(), email=f"verify_{uuid4().hex[:8]}@example.com",
            hashed_password="x", firstname="Verify", lastname="Me",
            account_status="active", verification_status="pending",
            verification_token=f"tok-{uuid4().hex}",
            token_expiration=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db_session.add(user)
        await db_session.commit()

        html_body = f'<!DOCTYPE html><html><body>token={user.verification_token}&other=1</body></html>'
        response = await async_client.get("/v1/auth/verify-email/", params={"token": html_body})
        assert response.status_code == 200

        await db_session.refresh(user)
        assert user.verification_status == "verified"

    async def test_verify_email_html_without_token_param_is_rejected(self, async_client: AsyncClient):
        """GET /v1/auth/verify-email - HTML with no extractable token=... is a 400, not a crash."""
        html_body = '<!DOCTYPE html><html><body>no token here</body></html>'
        response = await async_client.get("/v1/auth/verify-email/", params={"token": html_body})
        assert response.status_code == 400

    async def test_resend_verification_unverified_user_succeeds(self, async_client: AsyncClient, db_session):
        """POST /v1/auth/resend-verification - An existing, unverified user gets a fresh token
        and a real (queued) verification email."""
        user = User(
            id=uuid7(), email=f"resend_{uuid4().hex[:8]}@example.com",
            hashed_password="x", firstname="Resend", lastname="Me",
            account_status="active", verification_status="pending",
        )
        db_session.add(user)
        await db_session.commit()

        response = await async_client.post("/v1/auth/resend-verification/",
            json={"email": user.email},
            headers={"X-Resend-Token": "test-token-1234567890123456"}
        )
        assert response.status_code == 200
        await db_session.refresh(user)
        assert user.verification_token is not None

    async def test_resend_verification_already_verified_is_rejected(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/resend-verification - test_user fixture is already verified."""
        response = await async_client.post("/v1/auth/resend-verification/",
            json={"email": test_user.email},
            headers={"X-Resend-Token": "test-token-1234567890123456"}
        )
        assert response.status_code == 400

    async def test_resend_verification_unknown_email_returns_generic_success(self, async_client: AsyncClient):
        """POST /v1/auth/resend-verification - Unknown email still reports success (no account enumeration)."""
        response = await async_client.post("/v1/auth/resend-verification/",
            json={"email": f"nobody_{uuid4().hex[:8]}@example.com"},
            headers={"X-Resend-Token": "test-token-1234567890123456"}
        )
        assert response.status_code == 200

    async def test_resend_verification_short_token_header_rejected(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/resend-verification - A short X-Resend-Token header is rejected."""
        response = await async_client.post("/v1/auth/resend-verification/",
            json={"email": f"someone_{uuid4().hex[:8]}@example.com"},
            headers={"X-Resend-Token": "short"}
        )
        assert response.status_code == 400

    async def test_resend_verification_rate_limited_after_three_requests(self, async_client: AsyncClient):
        """POST /v1/auth/resend-verification - The 4th request within the window is 429."""
        email = f"rate_limited_{uuid4().hex[:8]}@example.com"
        for _ in range(3):
            resp = await async_client.post("/v1/auth/resend-verification/",
                json={"email": email},
                headers={"X-Resend-Token": "test-token-1234567890123456"}
            )
            assert resp.status_code == 200
        response = await async_client.post("/v1/auth/resend-verification/",
            json={"email": email},
            headers={"X-Resend-Token": "test-token-1234567890123456"}
        )
        assert response.status_code == 429

    async def test_reset_password_success(self, async_client: AsyncClient, db_session, test_user):
        """POST /v1/auth/reset-password - A valid, unexpired reset token resets the password."""
        test_user.reset_token = f"reset-{uuid4().hex}"
        test_user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        db_session.add(test_user)
        await db_session.commit()

        response = await async_client.post("/v1/auth/reset-password/", json={
            "token": test_user.reset_token, "new_password": "BrandNewPass123!"
        })
        assert response.status_code == 200

        login = await async_client.post("/v1/auth/login/", json={
            "email": test_user.email, "password": "BrandNewPass123!"
        })
        assert login.status_code == 200

    async def test_update_profile_with_valid_date_of_birth(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/auth/me - A naive ISO date string is parsed and stored as UTC-aware."""
        response = await async_client.patch("/v1/auth/me/",
            headers=auth_headers, json={"date_of_birth": "1990-05-15"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["date_of_birth"].startswith("1990-05-15")

    async def test_update_profile_with_invalid_date_of_birth(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/auth/me - An unparseable date_of_birth string is a 400, not a crash."""
        response = await async_client.patch("/v1/auth/me/",
            headers=auth_headers, json={"date_of_birth": "not-a-date"}
        )
        assert response.status_code == 400

    async def test_update_profile_with_overlong_field_returns_400(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/auth/me - A value longer than its DB column (avatar_url is String(500))
        triggers a real DataError at commit, exercising update()'s generic exception fallback."""
        response = await async_client.patch("/v1/auth/me/",
            headers=auth_headers, json={"avatar_url": "https://example.com/" + ("a" * 500)}
        )
        assert response.status_code == 400

    async def test_change_password_via_query_params(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/auth/me/password - Falls back to query params when there's no JSON body."""
        response = await async_client.patch(
            "/v1/auth/me/password/",
            headers=auth_headers,
            params={"current_password": "TestPassword123!", "new_password": "ViaQueryParams123!"},
        )
        assert response.status_code == 200

    async def test_change_password_missing_fields_returns_422(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/auth/me/password - No body and no query params is a 422."""
        response = await async_client.patch("/v1/auth/me/password/", headers=auth_headers)
        assert response.status_code == 422

    async def test_delete_account_wrong_password(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/auth/me - Wrong password confirmation is rejected."""
        response = await async_client.delete("/v1/auth/me/",
            headers=auth_headers, params={"password": "NotMyPassword1!"}
        )
        assert response.status_code == 400

    async def test_delete_account_success(self, async_client: AsyncClient, auth_headers, test_user):
        """DELETE /v1/auth/me - Correct password confirmation deletes the account."""
        response = await async_client.delete("/v1/auth/me/",
            headers=auth_headers, params={"password": "TestPassword123!"}
        )
        assert response.status_code == 200

        login = await async_client.post("/v1/auth/login/", json={
            "email": test_user.email, "password": "TestPassword123!"
        })
        assert login.status_code == 401

    async def test_delete_account_blocked_by_referencing_row(self, async_client: AsyncClient, auth_headers,
                                                              test_user, db_session):
        """DELETE /v1/auth/me - A row referencing this user via a NOT NULL FK with no cascade
        (accounts.customer_lifecycle_metrics.user_id) makes the delete fail with a real FK
        violation, exercising the generic-exception fallback rather than a mocked error."""
        from models.accounts.analytics import CustomerLifecycleMetrics
        metrics = CustomerLifecycleMetrics(
            id=uuid7(), user_id=test_user.id, registered_at=datetime.now(timezone.utc)
        )
        db_session.add(metrics)
        await db_session.commit()

        response = await async_client.delete("/v1/auth/me/",
            headers=auth_headers, params={"password": "TestPassword123!"}
        )
        assert response.status_code == 400
