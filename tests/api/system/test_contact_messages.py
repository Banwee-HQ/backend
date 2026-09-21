"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
class TestContactMessageEndpoints:
    """Test contact message endpoints."""

    async def test_064_contact_messages_create(self, async_client: AsyncClient, sample_contact_message):
        """POST /v1/contact-messages/ - Create contact message."""
        response = await async_client.post("/v1/contact-messages/", json=sample_contact_message)
        assert response.status_code in [200, 201]

    async def test_065_contact_messages_list_as_admin(self, async_client: AsyncClient, admin_headers):
        """GET /v1/contact-messages/ - List messages (admin)."""
        response = await async_client.get("/v1/contact-messages/", headers=admin_headers)
        assert response.status_code in [200, 403]

    async def test_065a_contact_messages_get(self, async_client: AsyncClient, admin_headers):
        """GET /v1/contact-messages/{id} - Get single message (admin)."""
        message_id = str(uuid4())
        response = await async_client.get(f"/v1/contact-messages/{message_id}/", headers=admin_headers)
        assert response.status_code in [200, 404, 403]

    async def test_065b_contact_messages_update(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/contact-messages/{id} - Update message (admin)."""
        message_id = str(uuid4())
        response = await async_client.patch(f"/v1/contact-messages/{message_id}/", 
            headers=admin_headers, json={"status": "resolved", "admin_notes": "Test notes"})
        assert response.status_code in [200, 404, 403]

    async def test_065c_contact_messages_delete(self, async_client: AsyncClient, admin_headers):
        """DELETE /v1/contact-messages/{id} - Delete message (admin)."""
        message_id = str(uuid4())
        response = await async_client.delete(f"/v1/contact-messages/{message_id}/", headers=admin_headers)
        assert response.status_code in [200, 404, 403]

