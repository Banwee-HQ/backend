"""Tests for api/system/contact_messages.py - /v1/contact-messages endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.fixture
async def created_message(async_client: AsyncClient, sample_contact_message):
    response = await async_client.post("/v1/contact-messages/", json=sample_contact_message)
    return response.json()["data"]


@pytest.mark.api
class TestContactMessageEndpoints:

    async def test_create(self, async_client: AsyncClient, sample_contact_message):
        """POST /v1/contact-messages/ - Public endpoint, no auth required."""
        response = await async_client.post("/v1/contact-messages/", json=sample_contact_message)
        assert response.status_code == 201
        assert response.json()["data"]["email"] == sample_contact_message["email"]
        assert response.json()["data"]["status"] is not None

    async def test_list_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get("/v1/contact-messages/", headers=auth_headers)
        assert response.status_code == 403

    async def test_list_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.get("/v1/contact-messages/")
        assert response.status_code == 401

    async def test_list_as_admin(self, async_client: AsyncClient, admin_headers, created_message):
        response = await async_client.get("/v1/contact-messages/", headers=admin_headers)
        assert response.status_code == 200
        ids = [m["id"] for m in response.json()["data"]["messages"]]
        assert created_message["id"] in ids

    async def test_list_filters_by_search(self, async_client: AsyncClient, admin_headers, created_message):
        response = await async_client.get(
            f"/v1/contact-messages/?search={created_message['subject']}", headers=admin_headers
        )
        assert response.status_code == 200
        ids = [m["id"] for m in response.json()["data"]["messages"]]
        assert created_message["id"] in ids

    async def test_get_by_id(self, async_client: AsyncClient, admin_headers, created_message):
        response = await async_client.get(f"/v1/contact-messages/{created_message['id']}/", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == created_message["id"]

    async def test_get_by_id_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get(f"/v1/contact-messages/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_get_requires_admin(self, async_client: AsyncClient, auth_headers, created_message):
        response = await async_client.get(f"/v1/contact-messages/{created_message['id']}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_update(self, async_client: AsyncClient, admin_headers, created_message):
        response = await async_client.patch(f"/v1/contact-messages/{created_message['id']}/",
            headers=admin_headers, json={"status": "resolved", "admin_notes": "Handled"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "resolved"
        assert response.json()["data"]["admin_notes"] == "Handled"

    async def test_update_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/contact-messages/{uuid4()}/",
            headers=admin_headers, json={"status": "resolved"}
        )
        assert response.status_code == 404

    async def test_update_requires_admin(self, async_client: AsyncClient, auth_headers, created_message):
        response = await async_client.patch(f"/v1/contact-messages/{created_message['id']}/",
            headers=auth_headers, json={"status": "resolved"}
        )
        assert response.status_code == 403

    async def test_delete(self, async_client: AsyncClient, admin_headers, created_message):
        response = await async_client.delete(f"/v1/contact-messages/{created_message['id']}/", headers=admin_headers)
        assert response.status_code == 200

        get_after = await async_client.get(f"/v1/contact-messages/{created_message['id']}/", headers=admin_headers)
        assert get_after.status_code == 404

    async def test_delete_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/contact-messages/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_delete_requires_admin(self, async_client: AsyncClient, auth_headers, created_message):
        response = await async_client.delete(f"/v1/contact-messages/{created_message['id']}/", headers=auth_headers)
        assert response.status_code == 403
