"""Tests for api/accounts/addresses.py - /v1/addresses endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.api
class TestAddressEndpoints:

    async def test_list_empty(self, async_client: AsyncClient, auth_headers):
        """GET /v1/addresses/ - List returns 200 even with no addresses."""
        response = await async_client.get("/v1/addresses/", headers=auth_headers)
        assert response.status_code == 200

    async def test_list_unauthorized(self, async_client: AsyncClient):
        """GET /v1/addresses/ - No auth is rejected."""
        response = await async_client.get("/v1/addresses/")
        assert response.status_code == 401

    async def test_create(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """POST /v1/addresses/ - Create address."""
        response = await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        assert response.status_code in [200, 201]
        assert response.json()["data"]["city"] == sample_address_data["city"]

    async def test_get_by_id(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """GET /v1/addresses/{id} - Get a single address."""
        create_resp = await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        address_id = create_resp.json()["data"]["id"]

        response = await async_client.get(f"/v1/addresses/{address_id}/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == address_id

    async def test_get_by_id_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/addresses/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/addresses/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_update(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """PATCH /v1/addresses/{id} - Update address."""
        create_resp = await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        address_id = create_resp.json()["data"]["id"]

        response = await async_client.patch(f"/v1/addresses/{address_id}/",
            headers=auth_headers, json={"city": "Updated City"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["city"] == "Updated City"

    async def test_delete(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """DELETE /v1/addresses/{id} - Delete address."""
        create_resp = await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        address_id = create_resp.json()["data"]["id"]

        response = await async_client.delete(f"/v1/addresses/{address_id}/", headers=auth_headers)
        assert response.status_code == 200

        get_resp = await async_client.get(f"/v1/addresses/{address_id}/", headers=auth_headers)
        assert get_resp.status_code == 404

    async def test_cannot_access_another_users_address(self, async_client: AsyncClient, auth_headers,
                                                          admin_headers, sample_address_data):
        """GET /v1/addresses/{id} - Another user's address is not visible."""
        create_resp = await async_client.post("/v1/addresses/", headers=admin_headers, json=sample_address_data)
        address_id = create_resp.json()["data"]["id"]

        response = await async_client.get(f"/v1/addresses/{address_id}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_cannot_update_another_users_address(self, async_client: AsyncClient, auth_headers,
                                                          admin_headers, sample_address_data):
        create_resp = await async_client.post("/v1/addresses/", headers=admin_headers, json=sample_address_data)
        address_id = create_resp.json()["data"]["id"]

        response = await async_client.patch(f"/v1/addresses/{address_id}/",
            headers=auth_headers, json={"city": "Hacked City"}
        )
        assert response.status_code == 404

    async def test_cannot_delete_another_users_address(self, async_client: AsyncClient, auth_headers,
                                                          admin_headers, sample_address_data):
        create_resp = await async_client.post("/v1/addresses/", headers=admin_headers, json=sample_address_data)
        address_id = create_resp.json()["data"]["id"]

        response = await async_client.delete(f"/v1/addresses/{address_id}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_update_not_found(self, async_client: AsyncClient, auth_headers):
        response = await async_client.patch(f"/v1/addresses/{uuid4()}/",
            headers=auth_headers, json={"city": "Nowhere"}
        )
        assert response.status_code == 404

    async def test_delete_not_found(self, async_client: AsyncClient, auth_headers):
        response = await async_client.delete(f"/v1/addresses/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_create_unauthenticated(self, async_client: AsyncClient, sample_address_data):
        response = await async_client.post("/v1/addresses/", json=sample_address_data)
        assert response.status_code == 401

    async def test_list_search(self, async_client: AsyncClient, auth_headers, sample_address_data):
        await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        response = await async_client.get(f"/v1/addresses/?search={sample_address_data['city']}", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    async def test_create_with_overlong_field_returns_500(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """POST /v1/addresses/ - AddressCreate doesn't validate string length, so a city
        longer than the DB column (String(100)) triggers a real DataError at commit,
        exercising the endpoint's generic exception fallback."""
        payload = dict(sample_address_data)
        payload["city"] = "x" * 150
        response = await async_client.post("/v1/addresses/", headers=auth_headers, json=payload)
        assert response.status_code == 500

    async def test_update_with_overlong_field_returns_500(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """PATCH /v1/addresses/{id} - Same DataError path as create, via AddressService.update()'s
        bulk UPDATE statement."""
        create_resp = await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        address_id = create_resp.json()["data"]["id"]

        response = await async_client.patch(f"/v1/addresses/{address_id}/",
            headers=auth_headers, json={"city": "x" * 150}
        )
        assert response.status_code == 500
