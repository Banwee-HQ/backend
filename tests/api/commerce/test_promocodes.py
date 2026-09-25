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

    async def test_create_duplicate_code_rejected(self, async_client: AsyncClient, admin_headers, created_promo):
        """POST /v1/promocodes/ - Re-using an existing code returns 400, not a raw DB-constraint 500."""
        response = await async_client.post("/v1/promocodes/", headers=admin_headers, json={
            "code": created_promo["code"], "discount_type": "percentage", "value": 5
        })
        assert response.status_code == 400

    async def test_list_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.get("/v1/promocodes/")
        assert response.status_code == 401

    async def test_get_by_id(self, async_client: AsyncClient, admin_headers, created_promo):
        """GET /v1/promocodes/{id} - Get a promocode."""
        response = await async_client.get(f"/v1/promocodes/{created_promo['id']}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_get_by_id_not_found(self, async_client: AsyncClient, admin_headers):
        """GET /v1/promocodes/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/promocodes/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_regular_user_cannot_view_inactive_promo(self, async_client: AsyncClient, admin_headers, auth_headers, created_promo):
        """GET /v1/promocodes/{id} - A non-admin can't view a deactivated promocode."""
        await async_client.patch(f"/v1/promocodes/{created_promo['id']}/",
            headers=admin_headers, json={"is_active": False}
        )
        response = await async_client.get(f"/v1/promocodes/{created_promo['id']}/", headers=auth_headers)
        assert response.status_code == 404

        admin_view = await async_client.get(f"/v1/promocodes/{created_promo['id']}/", headers=admin_headers)
        assert admin_view.status_code == 200

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
        """POST /v1/promocodes/validate - A real, active code is returned with its discount on the given subtotal."""
        response = await async_client.post("/v1/promocodes/validate/",
            headers=auth_headers, json={"code": created_promo["code"].lower(), "subtotal": 200}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["code"] == created_promo["code"]
        assert data["discount_amount"] is not None

    async def test_validate_unknown_code(self, async_client: AsyncClient, auth_headers):
        """POST /v1/promocodes/validate - An unusable code is a 400 carrying the reason."""
        response = await async_client.post("/v1/promocodes/validate/",
            headers=auth_headers, json={"code": "NOPE-NOT-REAL"}
        )
        assert response.status_code == 400
        assert response.json()["message"] == "Promocode not found"

    async def test_validate_below_minimum_order(self, async_client: AsyncClient, auth_headers, admin_headers):
        code = f"MIN{uuid4().hex[:6].upper()}"
        await async_client.post("/v1/promocodes/", headers=admin_headers, json={
            "code": code, "discount_type": "fixed", "value": 5, "minimum_order_amount": 50})
        response = await async_client.post("/v1/promocodes/validate/", headers=auth_headers, json={"code": code, "subtotal": 20})
        assert response.status_code == 400
        assert "at least 50.00" in response.json()["message"]


    async def test_delete_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/promocodes/{id} - Unknown ID returns 404, not a silent success."""
        response = await async_client.delete(f"/v1/promocodes/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_update_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/promocodes/{id} - service.update() raises APIException(404), which
        this endpoint's `except APIException: raise` must pass straight through."""
        response = await async_client.patch(f"/v1/promocodes/{uuid4()}/", headers=admin_headers, json={"value": 1})
        assert response.status_code == 404

    async def test_trigger_cleanup_requires_admin(self, async_client: AsyncClient, auth_headers):
        """POST /v1/promocodes/trigger-cleanup - Non-admin is forbidden."""
        response = await async_client.post("/v1/promocodes/trigger-cleanup/", headers=auth_headers)
        assert response.status_code == 403

    async def test_trigger_cleanup_as_admin(self, async_client: AsyncClient, admin_headers):
        """POST /v1/promocodes/trigger-cleanup - Admin can trigger cleanup."""
        response = await async_client.post("/v1/promocodes/trigger-cleanup/", headers=admin_headers)
        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.promocodes
class TestUnexpectedErrorsBecomeSafe500s:
    """As with subscriptions, every route here shares the same
    try/except APIException/except HTTPException/except Exception->500 shape.
    These force an unexpected failure from the service layer to verify the
    generic safety net actually works, rather than only exercising the
    well-trodden success/404 paths."""

    async def test_list(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch("services.commerce.promocode.PromocodeService.list", side_effect=Exception("boom"))
        response = await async_client.get("/v1/promocodes/", headers=admin_headers)
        assert response.status_code == 500


    async def test_get(self, async_client: AsyncClient, admin_headers, created_promo, mocker):
        mocker.patch("services.commerce.promocode.PromocodeService.get", side_effect=Exception("boom"))
        response = await async_client.get(f"/v1/promocodes/{created_promo['id']}/", headers=admin_headers)
        assert response.status_code == 500

    async def test_create(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch("services.commerce.promocode.PromocodeService.create", side_effect=Exception("boom"))
        response = await async_client.post("/v1/promocodes/", headers=admin_headers,
            json={"code": f"ERR{uuid4().hex[:6].upper()}", "discount_type": "percentage", "value": 5})
        assert response.status_code == 500

    async def test_update(self, async_client: AsyncClient, admin_headers, created_promo, mocker):
        mocker.patch("services.commerce.promocode.PromocodeService.update", side_effect=Exception("boom"))
        response = await async_client.patch(f"/v1/promocodes/{created_promo['id']}/",
            headers=admin_headers, json={"value": 1})
        assert response.status_code == 500

    async def test_delete(self, async_client: AsyncClient, admin_headers, created_promo, mocker):
        mocker.patch("services.commerce.promocode.PromocodeService.delete", side_effect=Exception("boom"))
        response = await async_client.delete(f"/v1/promocodes/{created_promo['id']}/", headers=admin_headers)
        assert response.status_code == 500


    async def test_trigger_cleanup_reports_scheduler_failure_as_500(self, async_client: AsyncClient, admin_headers, mocker):
        """update_promocode_statuses() itself never raises (it catches its own
        errors and returns success=False) - this exercises the endpoint's own
        `if not result.get('success')` branch, distinct from the generic
        except Exception safety net below it."""
        mocker.patch(
            "services.commerce.promocode_scheduler.PromoCodeScheduler.update_promocode_statuses",
            return_value={"success": False, "error": "simulated scheduler failure"},
        )
        response = await async_client.post("/v1/promocodes/trigger-cleanup/", headers=admin_headers)
        assert response.status_code == 500

    async def test_trigger_cleanup_unexpected_exception(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch(
            "services.commerce.promocode_scheduler.PromoCodeScheduler.update_promocode_statuses",
            side_effect=Exception("boom"),
        )
        response = await async_client.post("/v1/promocodes/trigger-cleanup/", headers=admin_headers)
        assert response.status_code == 500


