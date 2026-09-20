"""Tests for api/commerce/promocodes.py - /v1/promocodes endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.fixture
async def created_promo(async_client: AsyncClient, admin_headers):
    response = await async_client.post("/v1/promocodes/", headers=admin_headers, json={
        "code": f"TEST{uuid4().hex[:6].upper()}", "discount_type": "percentage", "value": 20
    })
    return response.json()["data"]


@pytest.mark.api
@pytest.mark.promocodes
class TestPromocodeEndpoints:

    async def test_list_as_admin(self, async_client: AsyncClient, admin_headers, created_promo):
        """GET /v1/promocodes/ - Admin can list promocodes."""
        response = await async_client.get("/v1/promocodes/", headers=admin_headers)
        assert response.status_code == 200

    async def test_list_as_regular_user_only_active(self, async_client: AsyncClient, auth_headers, created_promo):
        """GET /v1/promocodes/ - Regular users see only active promocodes."""
        response = await async_client.get("/v1/promocodes/", headers=auth_headers)
        assert response.status_code == 200

    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers):
        """POST /v1/promocodes/ - Create promocode (admin)."""
        code = f"TEST{uuid4().hex[:6].upper()}"
        response = await async_client.post("/v1/promocodes/", headers=admin_headers, json={
            "code": code, "discount_type": "percentage", "value": 20
        })
        assert response.status_code == 200
        assert response.json()["data"]["code"] == code

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers):
        """POST /v1/promocodes/ - Non-admin is forbidden."""
        response = await async_client.post("/v1/promocodes/", headers=auth_headers, json={
            "code": f"TEST{uuid4().hex[:6].upper()}", "discount_type": "percentage", "value": 20
        })
        assert response.status_code == 403

    async def test_get_by_id(self, async_client: AsyncClient, admin_headers, created_promo):
        """GET /v1/promocodes/{id} - Get a promocode."""
        response = await async_client.get(f"/v1/promocodes/{created_promo['id']}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient, admin_headers):
        """GET /v1/promocodes/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/promocodes/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_update_as_admin(self, async_client: AsyncClient, admin_headers, created_promo):
        """PATCH /v1/promocodes/{id} - Update promocode (admin)."""
        response = await async_client.patch(f"/v1/promocodes/{created_promo['id']}/",
            headers=admin_headers, json={"value": 25}
        )
        assert response.status_code == 200
        assert response.json()["data"]["value"] == 25

    async def test_update_requires_admin(self, async_client: AsyncClient, auth_headers, created_promo):
        """PATCH /v1/promocodes/{id} - Non-admin is forbidden."""
        response = await async_client.patch(f"/v1/promocodes/{created_promo['id']}/",
            headers=auth_headers, json={"value": 25}
        )
        assert response.status_code == 403

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_promo):
        """DELETE /v1/promocodes/{id} - Delete promocode (admin)."""
        response = await async_client.delete(f"/v1/promocodes/{created_promo['id']}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_delete_requires_admin(self, async_client: AsyncClient, auth_headers, created_promo):
        """DELETE /v1/promocodes/{id} - Non-admin is forbidden."""
        response = await async_client.delete(f"/v1/promocodes/{created_promo['id']}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_validate_valid_code(self, async_client: AsyncClient, auth_headers, created_promo):
        """POST /v1/promocodes/validate - A real, active code validates successfully."""
        response = await async_client.post("/v1/promocodes/validate/",
            headers=auth_headers, json={"code": created_promo["code"]}
        )
        assert response.status_code == 200
        assert response.json()["data"]["valid"] is True

    async def test_validate_unknown_code(self, async_client: AsyncClient, auth_headers):
        """POST /v1/promocodes/validate - Unknown code returns valid=False, not an error."""
        response = await async_client.post("/v1/promocodes/validate/",
            headers=auth_headers, json={"code": "NOPE-NOT-REAL"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["valid"] is False

    async def test_trigger_cleanup_requires_admin(self, async_client: AsyncClient, auth_headers):
        """POST /v1/promocodes/trigger-cleanup - Non-admin is forbidden."""
        response = await async_client.post("/v1/promocodes/trigger-cleanup/", headers=auth_headers)
        assert response.status_code == 403

    async def test_trigger_cleanup_as_admin(self, async_client: AsyncClient, admin_headers):
        """POST /v1/promocodes/trigger-cleanup - Admin can trigger cleanup."""
        response = await async_client.post("/v1/promocodes/trigger-cleanup/", headers=admin_headers)
        assert response.status_code == 200
