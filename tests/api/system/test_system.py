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

    async def test_003_api_docs(self, async_client: AsyncClient):
        """GET /docs - API documentation."""
        response = await async_client.get("/docs")
        assert response.status_code == 200

