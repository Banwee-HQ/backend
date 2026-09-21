"""Tests for api/commerce/tax.py - /v1/tax endpoints."""

import pytest
import random
import string
from httpx import AsyncClient
from uuid import uuid4


def unique_code() -> str:
    # ISO's user-assigned range ("X?"), never a real country - can't collide with seeded rates.
    return "X" + random.choice(string.ascii_uppercase)


@pytest.fixture
async def created_rate(async_client: AsyncClient, admin_headers):
    """POST /rates/ uses response_model=RateResponse directly - no {data: ...} envelope."""
    response = await async_client.post("/v1/tax/rates/", headers=admin_headers, json={
        "country_code": unique_code(), "country_name": "Testland", "tax_rate": 0.0875, "tax_name": "Test Tax"
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.api
@pytest.mark.tax
class TestTaxCalculate:

    async def test_calculate(self, async_client: AsyncClient):
        response = await async_client.post("/v1/tax/calculate/", json={
            "subtotal": 100.0, "shipping": 10.0, "country_code": "US", "state_code": "CA"
        })
        assert response.status_code == 200
        assert "tax_amount" in response.json()["data"]

    async def test_countries_list(self, async_client: AsyncClient):
        response = await async_client.get("/v1/tax/countries/")
        assert response.status_code == 200

    async def test_tax_types_list(self, async_client: AsyncClient):
        response = await async_client.get("/v1/tax/tax-types/")
        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.tax
class TestTaxRateEndpoints:

    async def test_list_is_public(self, async_client: AsyncClient, created_rate):
        """GET /v1/tax/rates/ - No auth required; rates are reference data for checkout."""
        response = await async_client.get("/v1/tax/rates/")
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()["data"]]
        assert created_rate["id"] in ids

    async def test_create(self, async_client: AsyncClient, created_rate):
        assert created_rate["country_name"] == "Testland"
        assert created_rate["tax_rate"] == 0.0875

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/tax/rates/", headers=auth_headers, json={
            "country_code": unique_code(), "country_name": "Testland", "tax_rate": 0.05
        })
        assert response.status_code == 403

    async def test_create_duplicate_is_rejected(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.post("/v1/tax/rates/", headers=admin_headers, json={
            "country_code": created_rate["country_code"], "country_name": "Testland", "tax_rate": 0.05
        })
        assert response.status_code == 400

    async def test_get_by_id(self, async_client: AsyncClient, admin_headers, created_rate):
        """GET /v1/tax/rates/{id} uses response_model=RateResponse directly - no envelope."""
        response = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["id"] == created_rate["id"]

    async def test_get_by_id_requires_admin(self, async_client: AsyncClient, auth_headers, created_rate):
        response = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_get_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get(f"/v1/tax/rates/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_update(self, async_client: AsyncClient, admin_headers, created_rate):
        """PATCH /v1/tax/rates/{id} uses response_model=RateResponse directly - no envelope."""
        response = await async_client.patch(f"/v1/tax/rates/{created_rate['id']}/",
            headers=admin_headers, json={"tax_rate": 0.09})
        assert response.status_code == 200
        assert response.json()["tax_rate"] == 0.09

    async def test_update_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/tax/rates/{uuid4()}/",
            headers=admin_headers, json={"tax_rate": 0.09})
        assert response.status_code == 404

    async def test_delete(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.delete(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert response.status_code == 200

        get_after = await async_client.get(f"/v1/tax/rates/{created_rate['id']}/", headers=admin_headers)
        assert get_after.status_code == 404

    async def test_delete_unknown_id_returns_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/tax/rates/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_bulk_update(self, async_client: AsyncClient, admin_headers, created_rate):
        response = await async_client.post("/v1/tax/rates/bulk-update/", headers=admin_headers, json=[
            {"id": created_rate["id"], "tax_rate": 0.1}
        ])
        assert response.status_code == 200
        assert response.json()["data"]["updated_count"] == 1
