"""Tests for api/commerce/refunds.py - /v1/refunds endpoints."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from models.commerce.orders import Order, OrderItem, OrderStatus, PaymentStatus, FulfillmentStatus
from core.utils.uuid_utils import uuid7
from services.commerce.refunds import RefundService


@pytest.fixture
async def created_variant(async_client: AsyncClient, admin_headers, sample_product_data):
    cat = await async_client.post("/v1/categories/",
        headers=admin_headers, json={"name": "Cat", "slug": f"cat-{uuid4().hex[:8]}"}
    )
    sample_product_data["category_id"] = cat.json()["data"]["id"]
    product = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    variants = await async_client.get(f"/v1/products/{product.json()['data']['id']}/")
    return variants.json()["data"]["variants"][0]


@pytest.fixture
async def refundable_order(db_session: AsyncSession, test_user, created_variant) -> Order:
    """A delivered, paid order with one item - eligible for a refund request."""
    order = Order(
        id=uuid7(),
        order_number=f"ORD-{uuid4().hex[:10].upper()}",
        user_id=test_user.id,
        order_status=OrderStatus.DELIVERED,
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.FULFILLED,
        subtotal=39.98,
        shipping_cost=10.0,
        tax_amount=0.0,
        total_amount=49.98,
        billing_address={"street": "1 Test St", "city": "Lagos", "country": "NG"},
        shipping_address={"street": "1 Test St", "city": "Lagos", "country": "NG"},
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id=uuid7(), order_id=order.id, variant_id=created_variant["id"],
        quantity=2, price_per_unit=19.99, total_price=39.98,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(order)
    order.item_id = item.id  # stash for tests, not a real column
    return order


@pytest.mark.api
@pytest.mark.refunds
class TestRefundEndpoints:

    async def test_list_own(self, async_client: AsyncClient, auth_headers):
        """GET /v1/refunds/ - List own refunds."""
        response = await async_client.get("/v1/refunds/", headers=auth_headers)
        assert response.status_code == 200

    async def test_list_generic_failure_returns_500(self, async_client: AsyncClient, auth_headers, mocker):
        """An unexpected error from the service must be wrapped as a 500, not leak raw."""
        mocker.patch.object(RefundService, "list", side_effect=RuntimeError("boom"))
        response = await async_client.get("/v1/refunds/", headers=auth_headers)
        assert response.status_code == 500
        assert "Failed to retrieve refunds" in response.json()["message"]

    async def test_list_httpexception_from_service_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        """An HTTPException raised by the service must propagate with its own status
        code, not get rewrapped into a generic 500 by the route's except Exception."""
        mocker.patch.object(RefundService, "list", side_effect=HTTPException(status_code=418, detail="teapot"))
        response = await async_client.get("/v1/refunds/", headers=auth_headers)
        assert response.status_code == 418


    async def test_request_via_order_path(self, async_client: AsyncClient, auth_headers, refundable_order):
        """POST /v1/refunds/orders/{order_id}/request - Same flow via the order-scoped route."""
        response = await async_client.post(f"/v1/refunds/orders/{refundable_order.id}/request/",
            headers=auth_headers, json={
                "reason": "changed_mind",
                "items": [{"order_item_id": str(refundable_order.item_id), "quantity": 1}],
            }
        )
        assert response.status_code == 200

    async def test_request_via_order_path_not_found(self, async_client: AsyncClient, auth_headers):
        """POST /v1/refunds/orders/{order_id}/request - A nonexistent order's HTTPException(404)
        from the service must pass through the route's except HTTPException, not become a 400."""
        response = await async_client.post(f"/v1/refunds/orders/{uuid4()}/request/",
            headers=auth_headers, json={
                "reason": "changed_mind",
                "items": [{"order_item_id": str(uuid4()), "quantity": 1}],
            }
        )
        assert response.status_code == 404

    async def test_request_via_order_path_generic_failure_returns_400(
        self, async_client: AsyncClient, auth_headers, refundable_order, mocker
    ):
        mocker.patch.object(RefundService, "request", side_effect=RuntimeError("boom"))
        response = await async_client.post(f"/v1/refunds/orders/{refundable_order.id}/request/",
            headers=auth_headers, json={
                "reason": "changed_mind",
                "items": [{"order_item_id": str(refundable_order.item_id), "quantity": 1}],
            }
        )
        assert response.status_code == 400
        assert "Failed to request refund" in response.json()["message"]

    async def test_get_by_id_not_found(self, async_client: AsyncClient, auth_headers):
        """GET /v1/refunds/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/refunds/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_get_generic_failure_returns_500(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch.object(RefundService, "get", side_effect=RuntimeError("boom"))
        response = await async_client.get(f"/v1/refunds/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 500
        assert "Failed to retrieve refund" in response.json()["message"]


    async def test_update_status_requires_admin(self, async_client: AsyncClient, auth_headers):
        """PUT /v1/refunds/{id}/status - Non-admin is forbidden."""
        response = await async_client.put(f"/v1/refunds/{uuid4()}/status/",
            headers=auth_headers, json={"status": "approved"}
        )
        assert response.status_code == 403


    async def test_update_status_generic_failure_returns_500(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch.object(RefundService, "update_status", side_effect=RuntimeError("boom"))
        response = await async_client.put(f"/v1/refunds/{uuid4()}/status/",
            headers=admin_headers, json={"status": "approved"}
        )
        assert response.status_code == 500
        assert "Failed to update refund status" in response.json()["message"]

    async def test_update_status_as_admin_not_found(self, async_client: AsyncClient, admin_headers):
        """PUT /v1/refunds/{id}/status - Unknown refund returns 404 for an admin.

        Regression test: RefundService had no update_status() method at all
        (nor patch()), so this - and PATCH /v1/refunds/{id} - always 500'd,
        regardless of whether the refund existed.
        """
        response = await async_client.put(f"/v1/refunds/{uuid4()}/status/",
            headers=admin_headers, json={"status": "approved"}
        )
        assert response.status_code == 404
