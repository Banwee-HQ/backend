"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
class TestRootAndSystem:
    """Test root and system endpoints."""

    async def test_001_root_endpoint(self, async_client: AsyncClient):
        """GET / - Root endpoint."""
        response = await async_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Banwee API"
        assert data["status"] == "Running"

    async def test_002_health_check(self, async_client: AsyncClient):
        """GET /v1/health/ - Health check."""
        response = await async_client.get("/v1/health/")
        assert response.status_code == 200
        data = response.json()
        # response uses standardized wrapper -> payload under `data`
        assert data["data"]["status"] == "alive"

    async def test_readiness_check_healthy(self, async_client: AsyncClient, mocker):
        """GET /v1/health/ready - Reports ready when the DB is reachable.

        db_manager (checked by get_db_health) is a separate global from the
        get_db dependency the test client overrides, so it's never actually
        initialized in this test process - mock it to exercise the endpoint's
        own "healthy" branch directly.
        """
        mocker.patch("api.system.health.get_db_health", return_value={"status": "healthy", "response_time_ms": 1.2})
        response = await async_client.get("/v1/health/ready")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "ready"
        assert data["database"]["status"] == "healthy"

    async def test_readiness_check_unhealthy(self, async_client: AsyncClient, mocker):
        """GET /v1/health/ready - Reports 503 when the DB is unreachable."""
        mocker.patch("api.system.health.get_db_health", return_value={"status": "unhealthy", "error": "connection refused"})
        response = await async_client.get("/v1/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["success"] is False
        assert data["data"]["status"] == "not_ready"

    async def test_003_api_docs(self, async_client: AsyncClient):
        """GET /docs - API documentation."""
        response = await async_client.get("/docs")
        assert response.status_code == 200

