"""Tests for models/commerce/orders.py - Order, OrderItem, TrackingEvent."""

import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timezone

from core.utils.uuid_utils import uuid7
from models.commerce.orders import Order, OrderItem, TrackingEvent, OrderStatus, PaymentStatus, FulfillmentStatus


def make_order(**overrides) -> Order:
    fields = dict(
        id=uuid7(), order_number=f"ORD-{uuid4().hex[:8].upper()}", user_id=uuid7(),
        order_status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.UNFULFILLED,
        subtotal=Decimal("39.98"), shipping_cost=Decimal("10.00"), tax_amount=Decimal("0.00"),
        total_amount=Decimal("49.98"),
        billing_address={"street": "1 Test St"}, shipping_address={"street": "1 Test St"},
        created_at=datetime.now(timezone.utc),
    )
    fields.update(overrides)
    order = Order(**fields)
    order.items = []
    return order


class TestOrderToDict:

    def test_serializes_core_fields(self):
        order = make_order()
        data = order.to_dict()
        assert data["id"] == str(order.id)
        assert data["order_number"] == order.order_number
        assert data["total_amount"] == Decimal("49.98")
        assert data["order_status"] == OrderStatus.CONFIRMED

    def test_null_dates_serialize_as_none(self):
        order = make_order()
        data = order.to_dict()
        assert data["confirmed_at"] is None
        assert data["shipped_at"] is None
        assert data["delivered_at"] is None
        assert data["cancelled_at"] is None

    def test_set_dates_are_isoformatted(self):
        now = datetime.now(timezone.utc)
        order = make_order(confirmed_at=now)
        data = order.to_dict()
        assert data["confirmed_at"] == now.isoformat()


class TestOrderItemToDict:

    def test_serializes_fields(self):
        item = OrderItem(
            id=uuid7(), order_id=uuid7(), variant_id=uuid7(),
            quantity=2, price_per_unit=Decimal("19.99"), total_price=Decimal("39.98"),
            created_at=datetime.now(timezone.utc),
        )
        data = item.to_dict()
        assert data["quantity"] == 2
        assert data["total_price"] == Decimal("39.98")
        assert data["id"] == str(item.id)


class TestTrackingEventToDict:

    def test_serializes_fields(self):
        event = TrackingEvent(
            id=uuid7(), order_id=uuid7(), status="shipped",
            description="Left warehouse", location="Warehouse A",
            created_at=datetime.now(timezone.utc),
        )
        data = event.to_dict()
        assert data["status"] == "shipped"
        assert data["description"] == "Left warehouse"
        assert data["location"] == "Warehouse A"
