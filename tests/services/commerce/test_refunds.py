"""Tests for services/commerce/refunds.py - RefundService."""

import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import stripe

from fastapi import HTTPException
from sqlalchemy import select
from core.utils.uuid_utils import uuid7
from services.commerce.refunds import RefundService
from schemas.commerce.refunds import Request as RefundRequest, ItemRequest as RefundItemRequest
from models.commerce.orders import Order, OrderItem, OrderStatus, PaymentStatus, FulfillmentStatus
from models.commerce.refunds import Refund, RefundItem, RefundStatus, RefundReason, RefundType
from models.commerce.payments import Transaction
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant
from models.catalog.inventories import Inventory


def fail_after(db_session, n: int, exc: Exception):
    """Return a replacement for db_session.execute that runs the first `n` calls
    for real, then raises `exc` on every subsequent call. Used to force a real
    (but controlled) failure partway through a service method, to exercise its
    generic `except Exception` fallback without mocking domain logic."""
    original_execute = db_session.execute
    state = {"count": 0}

    async def _execute(*args, **kwargs):
        state["count"] += 1
        if state["count"] > n:
            raise exc
        return await original_execute(*args, **kwargs)

    return _execute


@pytest.fixture
async def variant(db_session):
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    v = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("19.99"))
    db_session.add_all([category, product, v])
    await db_session.flush()
    db_session.add(Inventory(id=uuid7(), variant_id=v.id, quantity_available=50))
    await db_session.commit()
    return v


@pytest.fixture
async def delivered_order(db_session, test_user, variant) -> Order:
    order = Order(
        id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
        order_status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.FULFILLED,
        subtotal=Decimal("39.98"), shipping_cost=Decimal("10.00"), tax_amount=Decimal("4.00"),
        total_amount=Decimal("53.98"),
        billing_address={"street": "1 Test St"}, shipping_address={"street": "1 Test St"},
    )
    db_session.add(order)
    await db_session.flush()
    item = OrderItem(
        id=uuid7(), order_id=order.id, variant_id=variant.id,
        quantity=2, price_per_unit=Decimal("19.99"), total_price=Decimal("39.98"),
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(order)
    order.item_id = item.id  # stash for tests, not a real column
    return order


@pytest.fixture(autouse=True)
async def card_payment(db_session, delivered_order):
    """The order was paid by card, so approving a refund has something to refund."""
    db_session.add(Transaction(
        id=uuid7(), user_id=delivered_order.user_id, order_id=delivered_order.id,
        stripe_payment_intent_id="pi_test", amount=Decimal("53.98"), currency="CAD",
        status="succeeded", transaction_type="payment",
    ))
    await db_session.commit()


@pytest.fixture(autouse=True)
def stripe_refunds(mocker):
    """Stripe accepts every refund unless a test says otherwise."""
    return mocker.patch("services.commerce.payments.stripe.Refund.create", return_value=SimpleNamespace(id=f"re_{uuid4().hex[:8]}"))


def make_request(order, reason=RefundReason.CHANGED_MIND, quantity=2) -> RefundRequest:
    return RefundRequest(
        order_id=order.id,
        reason=reason,
        items=[RefundItemRequest(order_item_id=order.item_id, quantity=quantity)],
    )


@pytest.fixture
async def requested_refund(db_session, test_user, delivered_order):
    """A REQUESTED (not auto-approved) refund, via a non-auto-approval reason."""
    service = RefundService(db_session)
    response = await service.request(test_user.id, delivered_order.id, make_request(delivered_order))
    return response


class TestRequest:

    async def test_creates_a_refund_for_an_eligible_order(self, db_session, test_user, delivered_order):
        service = RefundService(db_session)
        response = await service.request(test_user.id, delivered_order.id, make_request(delivered_order))
        assert response.status == RefundStatus.REQUESTED
        # Every item back: exactly what was paid, never more
        assert response.requested_amount == pytest.approx(53.98, abs=0.001)
        assert response.refund_type == RefundType.FULL_REFUND
        assert len(response.items) == 1

    async def test_some_items_get_their_share_of_what_was_paid(self, db_session, test_user, delivered_order):
        service = RefundService(db_session)
        response = await service.request(test_user.id, delivered_order.id, make_request(delivered_order, quantity=1))
        # Half the goods: half of (paid - shipping)
        assert response.requested_amount == pytest.approx(21.99, abs=0.001)
        assert response.refund_type == RefundType.PARTIAL_REFUND

    async def test_unpaid_order_is_not_refundable(self, db_session, test_user, delivered_order):
        delivered_order.payment_status = PaymentStatus.REFUNDED
        await db_session.commit()
        with pytest.raises(HTTPException) as exc_info:
            await RefundService(db_session).request(test_user.id, delivered_order.id, make_request(delivered_order))
        assert exc_info.value.status_code == 400

    async def test_order_not_found_raises_404(self, db_session, test_user):
        service = RefundService(db_session)
        req = RefundRequest(
            order_id=uuid4(), reason=RefundReason.CHANGED_MIND,
            items=[RefundItemRequest(order_item_id=uuid4(), quantity=1)],
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.request(test_user.id, uuid4(), req)
        assert exc_info.value.status_code == 404

    async def test_ineligible_order_status_is_rejected(self, db_session, test_user, delivered_order):
        delivered_order.order_status = OrderStatus.PENDING
        await db_session.commit()
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.request(test_user.id, delivered_order.id, make_request(delivered_order))
        assert exc_info.value.status_code == 400

    async def test_duplicate_request_is_rejected(self, db_session, test_user, delivered_order, requested_refund):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.request(test_user.id, delivered_order.id, make_request(delivered_order))
        assert exc_info.value.status_code == 400

    async def test_unknown_order_item_is_rejected(self, db_session, test_user, delivered_order):
        service = RefundService(db_session)
        req = RefundRequest(
            order_id=delivered_order.id, refund_type=RefundType.FULL_REFUND, reason=RefundReason.CHANGED_MIND,
            items=[RefundItemRequest(order_item_id=uuid4(), quantity=1)],
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.request(test_user.id, delivered_order.id, req)
        assert exc_info.value.status_code == 400

    async def test_quantity_exceeding_order_is_rejected(self, db_session, test_user, delivered_order):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.request(test_user.id, delivered_order.id, make_request(delivered_order, quantity=99))
        assert exc_info.value.status_code == 400

    async def test_auto_approves_when_reason_and_amount_are_eligible(self, db_session, test_user, delivered_order, stripe_refunds):
        """DEFECTIVE_PRODUCT + full refund + small amount + recent order: approved and paid back at once."""
        service = RefundService(db_session)
        req = RefundRequest(
            order_id=delivered_order.id,
            reason=RefundReason.DEFECTIVE_PRODUCT,
            items=[RefundItemRequest(order_item_id=delivered_order.item_id, quantity=2)],
        )
        response = await service.request(test_user.id, delivered_order.id, req)
        assert response.status == RefundStatus.COMPLETED
        assert response.auto_approved is True
        assert response.processed_amount == pytest.approx(53.98, abs=0.001)
        assert stripe_refunds.call_args.kwargs["amount"] == 5398

    async def test_high_amount_reason_is_not_auto_approved(self, db_session, test_user, delivered_order):
        """Same eligible reason, but requested_amount > $500 must NOT auto-approve."""
        delivered_order.subtotal = Decimal("600.00")
        delivered_order.total_amount = Decimal("610.00")
        await db_session.commit()
        item_result = await db_session.execute(select(OrderItem).where(OrderItem.id == delivered_order.item_id))
        item = item_result.scalar_one()
        item.price_per_unit = Decimal("300.00")
        item.total_price = Decimal("600.00")
        await db_session.commit()

        service = RefundService(db_session)
        req = RefundRequest(
            order_id=delivered_order.id,
            reason=RefundReason.DEFECTIVE_PRODUCT,
            items=[RefundItemRequest(order_item_id=delivered_order.item_id, quantity=2)],
        )
        response = await service.request(test_user.id, delivered_order.id, req)
        assert response.status == RefundStatus.REQUESTED
        assert response.auto_approved is False

    async def test_generic_failure_raises_500(self, db_session, test_user, delivered_order, mocker):
        """A DB failure while committing the new refund is a genuine unexpected error,
        not an HTTPException raised on purpose - must surface as a 500, not crash raw."""
        mocker.patch.object(db_session, "commit", AsyncMock(side_effect=RuntimeError("commit boom")))
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.request(test_user.id, delivered_order.id, make_request(delivered_order))
        assert exc_info.value.status_code == 500


class TestList:

    async def test_lists_own_refunds(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        result = await service.list(user_id=test_user.id)
        assert result["total"] >= 1
        assert any(str(r.id) == str(requested_refund.id) for r in result["items"])

    async def test_admin_list_includes_customer_name(self, db_session, requested_refund):
        """Regression test: list()/get() used refund_data["customer_name"] = ...
        on a plain Pydantic BaseModel (no __setitem__) - every admin refund
        list/detail request crashed with TypeError."""
        service = RefundService(db_session)
        result = await service.list(user_id=None)
        entry = next(r for r in result["items"] if str(r.id) == str(requested_refund.id))
        assert entry.customer["email"]

    async def test_customers_never_see_staff_details(self, db_session, test_user, requested_refund):
        await RefundService(db_session).update_status(requested_refund.id, "rejected", admin_notes="internal")
        own = await RefundService(db_session).get(requested_refund.id, test_user.id)
        assert own.admin_notes is None and own.customer is None

    async def test_filters_by_status(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        result = await service.list(user_id=test_user.id, status=RefundStatus.REQUESTED)
        assert all(r.status == RefundStatus.REQUESTED for r in result["items"])

    async def test_sorts_by_amount_ascending(self, db_session, test_user, delivered_order, requested_refund, variant):
        """sort_by="amount" uses requested_amount as the sort column; sort_order="asc" ascends."""
        order2 = Order(
            id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
            order_status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID,
            fulfillment_status=FulfillmentStatus.FULFILLED,
            subtotal=Decimal("5.00"), shipping_cost=Decimal("0.00"), tax_amount=Decimal("0.00"),
            total_amount=Decimal("5.00"),
            billing_address={"street": "1 Test St"}, shipping_address={"street": "1 Test St"},
        )
        db_session.add(order2)
        await db_session.flush()
        item2 = OrderItem(
            id=uuid7(), order_id=order2.id, variant_id=variant.id,
            quantity=1, price_per_unit=Decimal("5.00"), total_price=Decimal("5.00"),
        )
        db_session.add(item2)
        await db_session.commit()
        order2.item_id = item2.id

        service = RefundService(db_session)
        cheap_refund = await service.request(test_user.id, order2.id, make_request(order2, quantity=1))

        result = await service.list(user_id=test_user.id, sort_by="amount", sort_order="asc")
        amounts = [r.requested_amount for r in result["items"]]
        assert amounts == sorted(amounts)
        assert float(cheap_refund.requested_amount) <= float(requested_refund.requested_amount)

    async def test_generic_failure_raises_500(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        db_session.execute = fail_after(db_session, n=0, exc=RuntimeError("query boom"))
        with pytest.raises(HTTPException) as exc_info:
            await service.list(user_id=test_user.id)
        assert exc_info.value.status_code == 500


class TestGet:

    async def test_returns_own_refund(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        result = await service.get(requested_refund.id, test_user.id)
        assert result.id == requested_refund.id

    async def test_admin_get_includes_customer(self, db_session, requested_refund):
        service = RefundService(db_session)
        result = await service.get(requested_refund.id)
        assert result.customer["email"]

    async def test_not_found_raises_404(self, db_session, test_user):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404

    async def test_generic_failure_raises_500(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        db_session.execute = fail_after(db_session, n=0, exc=RuntimeError("query boom"))
        with pytest.raises(HTTPException) as exc_info:
            await service.get(requested_refund.id, test_user.id)
        assert exc_info.value.status_code == 500


class TestUpdateStatus:

    async def test_approving_pays_the_customer_back_through_stripe(self, db_session, delivered_order, requested_refund, stripe_refunds):
        result = await RefundService(db_session).update_status(requested_refund.id, "approved", admin_notes="Looks good")
        assert result.status == RefundStatus.COMPLETED
        assert result.processed_amount == pytest.approx(53.98, abs=0.001)
        assert stripe_refunds.call_args.kwargs["payment_intent"] == "pi_test"
        assert stripe_refunds.call_args.kwargs["amount"] == 5398
        await db_session.refresh(delivered_order)
        assert delivered_order.payment_status == PaymentStatus.REFUNDED
        refund_rows = (await db_session.execute(
            select(Transaction).where(Transaction.order_id == delivered_order.id, Transaction.transaction_type == "refund")
        )).scalars().all()
        assert [float(t.amount) for t in refund_rows] == [-53.98]

    async def test_approving_restores_stock(self, db_session, variant, requested_refund):
        await RefundService(db_session).update_status(requested_refund.id, "approved")
        stock = (await db_session.execute(select(Inventory).where(Inventory.variant_id == variant.id))).scalar_one()
        await db_session.refresh(stock)
        assert stock.quantity_available == 52

    async def test_a_refused_stripe_refund_fails_and_can_be_retried(self, db_session, requested_refund, stripe_refunds):
        stripe_refunds.side_effect = stripe.error.InvalidRequestError("Charge already refunded", param=None)
        with pytest.raises(HTTPException) as exc_info:
            await RefundService(db_session).update_status(requested_refund.id, "approved")
        assert exc_info.value.status_code == 400
        failed = await RefundService(db_session).get(requested_refund.id)
        assert failed.status == RefundStatus.FAILED
        assert "already refunded" in failed.admin_notes

        stripe_refunds.side_effect = None
        retried = await RefundService(db_session).update_status(requested_refund.id, "approved")
        assert retried.status == RefundStatus.COMPLETED

    async def test_a_completed_refund_cannot_be_decided_again(self, db_session, requested_refund, stripe_refunds):
        service = RefundService(db_session)
        await service.update_status(requested_refund.id, "approved")
        with pytest.raises(HTTPException) as exc_info:
            await service.update_status(requested_refund.id, "approved")
        assert exc_info.value.status_code == 400
        assert stripe_refunds.call_count == 1

    async def test_never_refunds_more_than_was_paid(self, db_session, test_user, delivered_order, stripe_refunds):
        service = RefundService(db_session)
        first = await service.request(test_user.id, delivered_order.id, make_request(delivered_order, quantity=1))
        await service.update_status(first.id, "approved")
        second = await service.request(test_user.id, delivered_order.id, make_request(delivered_order, quantity=2))
        assert second.requested_amount == pytest.approx(53.98 - 21.99, abs=0.001)

    async def test_not_found_raises_404(self, db_session):
        with pytest.raises(HTTPException) as exc_info:
            await RefundService(db_session).update_status(uuid4(), "approved")
        assert exc_info.value.status_code == 404

    async def test_invalid_status_raises_400(self, db_session, requested_refund):
        with pytest.raises(HTTPException) as exc_info:
            await RefundService(db_session).update_status(requested_refund.id, "not-a-status")
        assert exc_info.value.status_code == 400

    async def test_rejects_without_touching_stripe(self, db_session, requested_refund, stripe_refunds):
        result = await RefundService(db_session).update_status(requested_refund.id, "rejected", admin_notes="Out of window")
        assert result.status == RefundStatus.REJECTED
        stripe_refunds.assert_not_called()

    async def test_inventory_restore_failure_does_not_fail_the_refund(self, db_session, requested_refund, mocker):
        mocker.patch("services.catalog.inventory.InventoryService.increment", AsyncMock(side_effect=RuntimeError("inventory boom")))
        result = await RefundService(db_session).update_status(requested_refund.id, "approved")
        assert result.status == RefundStatus.COMPLETED


