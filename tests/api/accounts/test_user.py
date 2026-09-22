"""Tests for api/accounts/user.py - /v1/users endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.api
class TestUserEndpoints:

    async def test_get_me(self, async_client: AsyncClient, auth_headers, test_user):
        """GET /v1/users/me - Get current user."""
        response = await async_client.get("/v1/users/me/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["email"] == test_user.email

    async def test_get_me_unauthorized(self, async_client: AsyncClient):
        """GET /v1/users/me - No auth is rejected."""
        response = await async_client.get("/v1/users/me/")
        assert response.status_code == 401

    async def test_get_profile_alias(self, async_client: AsyncClient, auth_headers, test_user):
        """GET /v1/users/profile - the route the frontend actually calls."""
        response = await async_client.get("/v1/users/profile/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["email"] == test_user.email

    async def test_list_requires_admin(self, async_client: AsyncClient, auth_headers):
        """GET /v1/users/ - Non-admin is forbidden."""
        response = await async_client.get("/v1/users/", headers=auth_headers)
        assert response.status_code == 403

    async def test_list_as_admin(self, async_client: AsyncClient, admin_headers):
        """GET /v1/users/ - Admin can list users."""
        response = await async_client.get("/v1/users/", headers=admin_headers)
        assert response.status_code == 200

    async def test_list_search(self, async_client: AsyncClient, admin_headers):
        """GET /v1/users/?q= - Search users by query."""
        response = await async_client.get("/v1/users/?q=test", headers=admin_headers)
        assert response.status_code == 200

    async def test_get_by_id_requires_admin(self, async_client: AsyncClient, auth_headers, test_user):
        """GET /v1/users/{id} - Non-admin is forbidden, even for their own ID."""
        response = await async_client.get(f"/v1/users/{test_user.id}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_get_by_id_as_admin(self, async_client: AsyncClient, admin_headers, test_user):
        """GET /v1/users/{id} - Admin can fetch any user."""
        response = await async_client.get(f"/v1/users/{test_user.id}/", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == str(test_user.id)

    async def test_get_by_id_not_found(self, async_client: AsyncClient, admin_headers):
        """GET /v1/users/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/users/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers):
        """POST /v1/users/ - Create user (admin)."""
        user_data = {
            "email": f"newuser_{uuid4().hex[:8]}@example.com",
            "password": "SecurePass123!",
            "firstname": "New",
            "lastname": "User"
        }
        response = await async_client.post("/v1/users/", headers=admin_headers, json=user_data)
        assert response.status_code == 201
        assert "hashed_password" not in response.json()["data"]

    async def test_create_requires_admin(self, async_client: AsyncClient):
        """POST /v1/users/ - Regression test: this endpoint had no auth dependency
        at all, so anyone could create an account - including one with role=admin,
        a full unauthenticated privilege-escalation path."""
        response = await async_client.post("/v1/users/", json={
            "email": f"attacker_{uuid4().hex[:8]}@example.com",
            "password": "SecurePass123!",
            "firstname": "Attacker",
            "lastname": "User",
            "role": "admin",
        })
        assert response.status_code == 401

    async def test_create_by_non_admin_is_forbidden(self, async_client: AsyncClient, auth_headers):
        """POST /v1/users/ - A regular authenticated user still can't use this route."""
        response = await async_client.post("/v1/users/", headers=auth_headers, json={
            "email": f"newuser_{uuid4().hex[:8]}@example.com",
            "password": "SecurePass123!",
            "firstname": "New",
            "lastname": "User",
        })
        assert response.status_code == 403

    async def test_patch_self_forbidden_for_non_admin(self, async_client: AsyncClient, auth_headers, test_user):
        """PATCH /v1/users/{id} - Blocked for non-admins by require_admin, even on their own ID."""
        response = await async_client.patch(f"/v1/users/{test_user.id}/",
            headers=auth_headers, json={"firstname": "Updated"}
        )
        assert response.status_code == 403

    async def test_patch_as_admin(self, async_client: AsyncClient, admin_headers, admin_user):
        """PATCH /v1/users/{id} - Admin updates their own record."""
        response = await async_client.patch(f"/v1/users/{admin_user.id}/",
            headers=admin_headers, json={"firstname": "Updated"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["firstname"] == "Updated"

    async def test_patch_other_user_forbidden(self, async_client: AsyncClient, admin_headers, test_user):
        """PATCH /v1/users/{id} - Even an admin can only update their own record here."""
        response = await async_client.patch(f"/v1/users/{test_user.id}/",
            headers=admin_headers, json={"firstname": "Updated"}
        )
        assert response.status_code == 403

    async def test_delete_requires_admin(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/users/{id} - Non-admin is forbidden."""
        response = await async_client.delete(f"/v1/users/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_delete_self_forbidden(self, async_client: AsyncClient, admin_headers, admin_user):
        """DELETE /v1/users/{id} - Admin cannot delete their own account here."""
        response = await async_client.delete(f"/v1/users/{admin_user.id}/", headers=admin_headers)
        assert response.status_code == 400

    async def test_delete_not_found(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/users/{id} - Unknown ID returns 404."""
        response = await async_client.delete(f"/v1/users/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_update_status(self, async_client: AsyncClient, admin_headers, test_user):
        """PUT /v1/users/{id}/status - Update active status (admin)."""
        response = await async_client.put(f"/v1/users/{test_user.id}/status/",
            headers=admin_headers, json={"is_active": False}
        )
        assert response.status_code == 200

    async def test_reset_password(self, async_client: AsyncClient, admin_headers, test_user, mocker):
        """POST /v1/users/{id}/reset-password - Trigger password reset email (admin)."""
        mocker.patch("services.accounts.email.EmailService.send_password_reset_email", return_value=None)
        response = await async_client.post(f"/v1/users/{test_user.id}/reset-password/", headers=admin_headers)
        assert response.status_code == 200

    async def test_deactivate(self, async_client: AsyncClient, admin_headers, test_user):
        """POST /v1/users/{id}/deactivate - Deactivate user (admin)."""
        response = await async_client.post(f"/v1/users/{test_user.id}/deactivate/", headers=admin_headers)
        assert response.status_code == 200

    async def test_activate(self, async_client: AsyncClient, admin_headers, test_user):
        """POST /v1/users/{id}/activate - Activate user (admin)."""
        response = await async_client.post(f"/v1/users/{test_user.id}/activate/", headers=admin_headers)
        assert response.status_code == 200

    async def test_verify(self, async_client: AsyncClient, admin_headers, test_user):
        """PUT /v1/users/{id}/verify - Verify user account (admin)."""
        response = await async_client.put(f"/v1/users/{test_user.id}/verify/", headers=admin_headers)
        assert response.status_code == 200

    async def test_activity(self, async_client: AsyncClient, admin_headers, test_user):
        """GET /v1/users/{id}/activity - Get user activity log (admin)."""
        response = await async_client.get(f"/v1/users/{test_user.id}/activity/", headers=admin_headers)
        assert response.status_code == 200
