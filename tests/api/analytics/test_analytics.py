"""Tests for api/analytics/analytics.py - /v1/analytics endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.api
@pytest.mark.analytics
class TestTrackEvent:

    async def test_track_event(self, async_client: AsyncClient):
        response = await async_client.post("/v1/analytics/track/", json={
            "session_id": str(uuid4()), "event_type": "page_view", "page": "/test", "metadata": {"test": True}
        })
        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.analytics
class TestSimpleDashboard:

    async def test_requires_auth(self, async_client: AsyncClient):
        response = await async_client.get("/v1/analytics/simple-dashboard/")
        assert response.status_code == 401

    async def test_any_authenticated_user_can_access(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get("/v1/analytics/simple-dashboard/", headers=auth_headers)
        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.analytics
class TestAdminOnlyEndpoints:
    """These all require admin and are backed by real DB queries - a non-admin
    call and a real query error (not just "route exists") are what matter here."""

    ENDPOINTS = [
        "/v1/analytics/dashboard/",
        "/v1/analytics/revenue/",
        "/v1/analytics/orders/",
        "/v1/analytics/products/",
        "/v1/analytics/users/",
        "/v1/analytics/conversion-rates/",
        "/v1/analytics/cart-abandonment/",
        "/v1/analytics/time-to-purchase/",
        "/v1/analytics/refund-rates/",
        "/v1/analytics/repeat-customers/",
        "/v1/analytics/sales-trend/",
        "/v1/analytics/users-growth-trend/",
        "/v1/analytics/kpis/",
        "/v1/analytics/sales/",
        "/v1/analytics/stats/",
        "/v1/analytics/dashboard/admin/",
    ]

    @pytest.mark.parametrize("path", ENDPOINTS)
    async def test_requires_admin(self, async_client: AsyncClient, auth_headers, path):
        response = await async_client.get(path, headers=auth_headers)
        assert response.status_code == 403

    @pytest.mark.parametrize("path", ENDPOINTS)
    async def test_admin_can_access(self, async_client: AsyncClient, admin_headers, path):
        response = await async_client.get(path, headers=admin_headers)
        assert response.status_code == 200


@pytest.mark.api
@pytest.mark.analytics
class TestSalesOverview:
    """/sales-overview/ only requires auth, not admin."""

    async def test_any_authenticated_user_can_access(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get("/v1/analytics/sales-overview/", headers=auth_headers)
        assert response.status_code == 200

    async def test_requires_auth(self, async_client: AsyncClient):
        response = await async_client.get("/v1/analytics/sales-overview/")
        assert response.status_code == 401


@pytest.mark.api
@pytest.mark.analytics
class TestExportOrders:

    async def test_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get("/v1/analytics/export/orders/", headers=auth_headers)
        assert response.status_code == 403

    async def test_admin_can_export_csv(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/export/orders/", headers=admin_headers)
        assert response.status_code == 200
