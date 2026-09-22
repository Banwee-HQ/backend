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

    async def test_invalid_event_type_returns_400(self, async_client: AsyncClient):
        """EventType(...) raises ValueError for an unrecognized event_type - the route
        maps that to a 400, not a 500."""
        response = await async_client.post("/v1/analytics/track/", json={
            "session_id": str(uuid4()), "event_type": "not_a_real_event_type"
        })
        assert response.status_code == 400
        assert "Invalid event data" in response.json()["message"]

    async def test_nonexistent_order_id_returns_500(self, async_client: AsyncClient):
        """order_id has a real FK to commerce.orders.id - a random UUID that isn't a
        real order fails at the DB level with a real ForeignKeyViolation, which is a
        generic Exception (not ValueError), hitting the route's 500 fallback branch."""
        response = await async_client.post("/v1/analytics/track/", json={
            "session_id": str(uuid4()), "event_type": "page_view", "order_id": str(uuid4())
        })
        assert response.status_code == 500
        assert "Failed to track event" in response.json()["message"]


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
        "/v1/analytics/sales-overview/",
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
class TestAdminEndpointsServiceErrorHandling:
    """Force AnalyticsService methods to fail so the route's `except Exception` ->
    APIException(500) mapping is actually exercised (not just its happy path)."""

    ENDPOINT_TO_SERVICE_METHOD = [
        ("/v1/analytics/conversion-rates/", "get_conversion_metrics"),
        ("/v1/analytics/cart-abandonment/", "get_cart_abandonment_metrics"),
        ("/v1/analytics/time-to-purchase/", "get_time_to_purchase_metrics"),
        ("/v1/analytics/refund-rates/", "get_refund_rate_metrics"),
        ("/v1/analytics/repeat-customers/", "get_repeat_customer_metrics"),
        ("/v1/analytics/sales-trend/", "get_sales_trend_data"),
        ("/v1/analytics/users-growth-trend/", "get_users_growth_trend"),
        ("/v1/analytics/sales-overview/", "get_sales_overview_data"),
        ("/v1/analytics/revenue/", "get_revenue_metrics"),
    ]

    @pytest.mark.parametrize("path, service_method", ENDPOINT_TO_SERVICE_METHOD)
    async def test_returns_500_when_service_raises(self, async_client: AsyncClient, admin_headers, mocker, path, service_method):
        mocker.patch(f"services.analytics.analytics.AnalyticsService.{service_method}", side_effect=RuntimeError("boom"))
        response = await async_client.get(path, headers=admin_headers)
        assert response.status_code == 500

    async def test_dashboard_falls_back_gracefully_when_service_raises(self, async_client: AsyncClient, admin_headers, mocker):
        """dashboard/ is special-cased: unlike every other analytics endpoint, a failure
        here degrades to a 200 with fallback data instead of a 500."""
        mocker.patch(
            "services.analytics.analytics.AnalyticsService.get_comprehensive_dashboard_data",
            side_effect=RuntimeError("boom"),
        )
        response = await async_client.get("/v1/analytics/dashboard/", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["message"] == "Dashboard data (fallback)"
        assert "error" in data
        assert data["metrics"]["total_users"] == 1


@pytest.mark.api
@pytest.mark.analytics
class TestKpisComparison:

    async def test_compare_previous_true_includes_changes(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/kpis/?compare_previous=true", headers=admin_headers)
        assert response.status_code == 200
        assert "comparison" in response.json()["data"]
        assert "changes" in response.json()["data"]["comparison"]

    async def test_compare_previous_false_skips_comparison(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/kpis/?compare_previous=false", headers=admin_headers)
        assert response.status_code == 200
        assert "comparison" not in response.json()["data"]

    async def test_comparison_failure_is_reported_but_does_not_fail_the_request(self, async_client: AsyncClient, admin_headers, mocker):
        """Only the *previous*-period lookup fails (the comparison-only inner
        try/except) - the current period still succeeds and the request still
        returns 200, just without usable comparison data."""
        from services.analytics.analytics import AnalyticsService

        original = AnalyticsService.get_comprehensive_dashboard_data
        call_count = {"n": 0}

        async def flaky(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return await original(self, *args, **kwargs)
            raise RuntimeError("boom")

        mocker.patch.object(AnalyticsService, "get_comprehensive_dashboard_data", new=flaky)
        response = await async_client.get("/v1/analytics/kpis/", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["comparison"] == {"error": "Comparison data unavailable"}

    async def test_extreme_date_range_overflow_returns_500(self, async_client: AsyncClient, admin_headers):
        """An extreme start_date pushes the previous-period window before year 1,
        raising OverflowError computing prev_start_date - this happens *outside* the
        comparison-only inner try/except, so it's the outer handler (a plain 500)
        that actually fires, not the graceful "comparison data unavailable" path."""
        response = await async_client.get(
            "/v1/analytics/kpis/?start_date=0001-01-01T00:00:00&end_date=2026-01-01T00:00:00",
            headers=admin_headers,
        )
        assert response.status_code == 500
        assert "Failed to retrieve KPIs" in response.json()["message"]


@pytest.mark.api
@pytest.mark.analytics
class TestSalesDateParsing:

    async def test_explicit_date_range_is_parsed(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get(
            "/v1/analytics/sales/?start_date=2026-01-01&end_date=2026-01-31", headers=admin_headers
        )
        assert response.status_code == 200

    async def test_malformed_date_returns_500(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/sales/?start_date=not-a-date", headers=admin_headers)
        assert response.status_code == 500


@pytest.mark.api
@pytest.mark.analytics
class TestSimpleQueryEndpointsErrorHandling:
    """users/, products/, orders/ build their queries inline (no AnalyticsService), so a
    DB failure is injected directly on the request's own db_session. Every request also
    re-authenticates via one db.execute() call inside get_current_auth_user() first, so
    the fake failure only kicks in from the *second* execute() onward - otherwise it
    would break authentication itself (401) rather than the route body (500)."""

    @staticmethod
    def _break_execute_after_auth(db_session, mocker):
        original_execute = db_session.execute
        state = {"calls": 0}

        async def flaky_execute(*args, **kwargs):
            state["calls"] += 1
            if state["calls"] == 1:
                return await original_execute(*args, **kwargs)
            raise RuntimeError("boom")

        mocker.patch.object(db_session, "execute", side_effect=flaky_execute)

    async def test_users_returns_500_on_db_error(self, async_client: AsyncClient, admin_headers, db_session, mocker):
        self._break_execute_after_auth(db_session, mocker)
        response = await async_client.get("/v1/analytics/users/", headers=admin_headers)
        assert response.status_code == 500

    async def test_products_returns_500_on_db_error(self, async_client: AsyncClient, admin_headers, db_session, mocker):
        self._break_execute_after_auth(db_session, mocker)
        response = await async_client.get("/v1/analytics/products/", headers=admin_headers)
        assert response.status_code == 500

    async def test_orders_returns_500_on_db_error(self, async_client: AsyncClient, admin_headers, db_session, mocker):
        self._break_execute_after_auth(db_session, mocker)
        response = await async_client.get("/v1/analytics/orders/", headers=admin_headers)
        assert response.status_code == 500


@pytest.mark.api
@pytest.mark.analytics
class TestAdminStatsAndDashboardErrorHandling:
    """Regression coverage for a real bug: `status` used to be the name of a Query(...)
    parameter on both admin_stats() and admin_dashboard(), shadowing the module-level
    `from fastapi import status` import within those two functions. Their generic
    `except Exception` branch referenced `status.HTTP_500_INTERNAL_SERVER_ERROR` - with
    `status` rebound to a plain string (or None), that line raised AttributeError
    instead of returning a clean 500, masking the real error entirely. Fixed by
    renaming the parameter to `order_status` (aliased back to the `status` query key)."""

    async def test_status_query_param_still_works_via_alias(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/stats/?status=delivered", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["filters"]["status_filter"] == "delivered"

    async def test_admin_stats_passes_through_api_exception(self, async_client: AsyncClient, admin_headers, mocker):
        from core.exceptions import APIException
        mocker.patch(
            "services.analytics.analytics.AnalyticsService.get_admin_stats",
            side_effect=APIException(status_code=418, message="teapot"),
        )
        response = await async_client.get("/v1/analytics/stats/", headers=admin_headers)
        assert response.status_code == 418

    async def test_admin_stats_passes_through_http_exception(self, async_client: AsyncClient, admin_headers, mocker):
        from fastapi import HTTPException
        mocker.patch(
            "services.analytics.analytics.AnalyticsService.get_admin_stats",
            side_effect=HTTPException(status_code=503, detail="down"),
        )
        response = await async_client.get("/v1/analytics/stats/", headers=admin_headers)
        assert response.status_code == 503

    async def test_admin_stats_generic_exception_becomes_clean_500(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch(
            "services.analytics.analytics.AnalyticsService.get_admin_stats",
            side_effect=RuntimeError("boom"),
        )
        response = await async_client.get("/v1/analytics/stats/?status=pending", headers=admin_headers)
        assert response.status_code == 500
        assert "Failed to fetch admin stats" in response.json()["message"]

    async def test_admin_dashboard_passes_through_api_exception(self, async_client: AsyncClient, admin_headers, mocker):
        from core.exceptions import APIException
        mocker.patch(
            "services.analytics.analytics.AnalyticsService.get_admin_overview",
            side_effect=APIException(status_code=418, message="teapot"),
        )
        response = await async_client.get("/v1/analytics/dashboard/admin/", headers=admin_headers)
        assert response.status_code == 418

    async def test_admin_dashboard_passes_through_http_exception(self, async_client: AsyncClient, admin_headers, mocker):
        from fastapi import HTTPException
        mocker.patch(
            "services.analytics.analytics.AnalyticsService.get_admin_overview",
            side_effect=HTTPException(status_code=503, detail="down"),
        )
        response = await async_client.get("/v1/analytics/dashboard/admin/", headers=admin_headers)
        assert response.status_code == 503

    async def test_admin_dashboard_generic_exception_becomes_clean_500(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch(
            "services.analytics.analytics.AnalyticsService.get_admin_overview",
            side_effect=RuntimeError("boom"),
        )
        response = await async_client.get("/v1/analytics/dashboard/admin/?status=pending", headers=admin_headers)
        assert response.status_code == 500
        assert "Failed to fetch dashboard data" in response.json()["message"]


@pytest.mark.api
@pytest.mark.analytics
class TestExportOrders:

    async def test_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get("/v1/analytics/export/orders/", headers=auth_headers)
        assert response.status_code == 403

    async def test_admin_can_export_csv(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/export/orders/", headers=admin_headers)
        assert response.status_code == 200

    async def test_invalid_format_returns_400(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/export/orders/?format=json", headers=admin_headers)
        assert response.status_code == 400
        assert "Invalid format" in response.json()["message"]

    async def test_export_excel(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/export/orders/?format=excel", headers=admin_headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    async def test_export_pdf(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/export/orders/?format=pdf", headers=admin_headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/pdf")

    async def test_export_with_status_filter_alias(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/analytics/export/orders/?status=delivered", headers=admin_headers)
        assert response.status_code == 200

    async def test_pagination_loop_advances_to_the_next_page(self, async_client: AsyncClient, admin_headers, mocker):
        """OrderService.list() is mocked here (not AnalyticsService) purely to make the
        while-True pagination loop in export_orders() actually take a second lap,
        without needing 100+ real orders in the DB just to exercise a page += 1."""
        from services.commerce.orders import OrderService

        def make_order(i):
            return {
                "id": f"order-{i}", "user": {}, "status": "delivered", "payment_status": "paid",
                "total_amount": 10.0, "items": [], "created_at": "2026-01-01T00:00:00Z",
            }

        page1 = {"data": [make_order(i) for i in range(100)]}
        page2 = {"data": [make_order(i) for i in range(3)]}
        mock_list = mocker.patch.object(OrderService, "list", side_effect=[page1, page2])

        response = await async_client.get("/v1/analytics/export/orders/?format=csv", headers=admin_headers)
        assert response.status_code == 200
        assert mock_list.call_count == 2

    async def test_returns_500_when_order_service_raises(self, async_client: AsyncClient, admin_headers, mocker):
        from services.commerce.orders import OrderService
        mocker.patch.object(OrderService, "list", side_effect=RuntimeError("db exploded"))
        response = await async_client.get("/v1/analytics/export/orders/", headers=admin_headers)
        assert response.status_code == 500
        assert "Failed to export orders" in response.json()["message"]
