"""Tests for system endpoints (health, contact messages)."""

import pytest
from httpx import AsyncClient


@pytest.mark.api
@pytest.mark.unit
class TestHealthEndpoints:
    """Test health check endpoints."""

    async def test_root_endpoint(self, async_client: AsyncClient):
        """Test the root endpoint returns API info."""
        response = await async_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Banwee API"
        assert data["status"] == "Running"
        assert "version" in data

    async def test_health_check(self, async_client: AsyncClient):
        """Test the health check endpoint."""
        response = await async_client.get("/v1/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data
        assert data["service"] == "banwee-api"


@pytest.mark.api
@pytest.mark.unit
class TestContactMessageEndpoints:
    """Test contact message endpoints."""

    async def test_create_contact_message(self, async_client: AsyncClient, sample_contact_message):
        """Test creating a contact message."""
        response = await async_client.post("/v1/contact-messages", json=sample_contact_message)
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_create_contact_message_validation_error(self, async_client: AsyncClient):
        """Test creating a contact message with invalid data."""
        invalid_data = {
            "name": "",  # Empty name should fail validation
            "email": "invalid-email",
            "subject": "Test",
            "message": ""
        }
        response = await async_client.post("/v1/contact-messages", json=invalid_data)
        # Should return validation error
        assert response.status_code in [400, 422]

    async def test_get_contact_messages_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting all contact messages as admin."""
        response = await async_client.get("/v1/contact-messages", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    async def test_get_contact_messages_unauthorized(self, async_client: AsyncClient):
        """Test getting contact messages without authentication."""
        response = await async_client.get("/v1/contact-messages")
        assert response.status_code == 401
