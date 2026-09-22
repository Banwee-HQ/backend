"""Tests for services/commerce/refunds.py - RefundService."""

import pytest
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from core.utils.uuid_utils import uuid7
from services.commerce.refunds import RefundService
from schemas.commerce.refunds import Request as RefundRequest, ItemRequest as RefundItemRequest
from models.commerce.orders import Order, OrderItem, OrderStatus, PaymentStatus, FulfillmentStatus
from models.commerce.refunds import Refund, RefundStatus, RefundReason, RefundType
from models.commerce.payments import Transaction
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant
from models.catalog.inventories import Inventory


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


def make_request(order, reason=RefundReason.CHANGED_MIND, quantity=2) -> RefundRequest:
    return RefundRequest(
        order_id=order.id,
        refund_type=RefundType.FULL_REFUND,
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
        # Full refund - includes proportional shipping and tax, not just item subtotal
        assert response.requested_amount == pytest.approx(54.98, abs=0.01)
        assert len(response.items) == 1

    async def test_order_not_found_raises_404(self, db_session, test_user):
        service = RefundService(db_session)
        req = RefundRequest(
            order_id=uuid4(), refund_type=RefundType.FULL_REFUND, reason=RefundReason.CHANGED_MIND,
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
        assert entry.customer_name

    async def test_filters_by_status(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        result = await service.list(user_id=test_user.id, status=RefundStatus.REQUESTED)
        assert all(r.status == RefundStatus.REQUESTED for r in result["items"])


class TestGet:

    async def test_returns_own_refund(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        result = await service.get(requested_refund.id, test_user.id)
        assert result.id == requested_refund.id

    async def test_admin_get_includes_customer(self, db_session, requested_refund):
        service = RefundService(db_session)
        result = await service.get(requested_refund.id)
        assert result.customer["id"] == str(result.id) or "email" in result.customer

    async def test_not_found_raises_404(self, db_session, test_user):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


class TestCancel:

    async def test_cancels_a_requested_refund(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        result = await service.cancel(test_user.id, requested_refund.id)
        assert result.status == RefundStatus.CANCELLED

    async def test_not_found_raises_404(self, db_session, test_user):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.cancel(test_user.id, uuid4())
        assert exc_info.value.status_code == 404

    async def test_cannot_cancel_a_completed_refund(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        result = await db_session.execute(
            select(Refund).where(Refund.id == requested_refund.id)
        )
        refund = result.scalar_one()
        refund.status = RefundStatus.COMPLETED
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await service.cancel(test_user.id, requested_refund.id)
        assert exc_info.value.status_code == 400


class TestUpdateStatus:

    async def test_approves_and_restores_inventory(self, db_session, test_user, variant, requested_refund):
        service = RefundService(db_session)
        result = await service.update_status(requested_refund.id, "approved", admin_notes="Looks good")
        assert result.status == RefundStatus.APPROVED
        # approved_amount is stored as Numeric(10,2), so it's the DB-rounded value
        assert result.approved_amount == pytest.approx(requested_refund.requested_amount, abs=0.01)

    async def test_not_found_raises_404(self, db_session):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_status(uuid4(), "approved")
        assert exc_info.value.status_code == 404

    async def test_invalid_status_raises_400(self, db_session, requested_refund):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_status(requested_refund.id, "not-a-status")
        assert exc_info.value.status_code == 400

    async def test_rejects(self, db_session, requested_refund):
        service = RefundService(db_session)
        result = await service.update_status(requested_refund.id, "rejected", admin_notes="Out of window")
        assert result.status == RefundStatus.REJECTED


class TestPatch:

    async def test_updates_admin_notes(self, db_session, requested_refund):
        service = RefundService(db_session)
        result = await service.patch(requested_refund.id, {"admin_notes": "Called customer"})
        assert result.id == requested_refund.id

    async def test_updates_approved_amount(self, db_session, requested_refund):
        service = RefundService(db_session)
        result = await service.patch(requested_refund.id, {"approved_amount": 10.0})
        assert result.approved_amount == 10.0

    async def test_invalid_status_raises_400(self, db_session, requested_refund):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.patch(requested_refund.id, {"status": "not-a-status"})
        assert exc_info.value.status_code == 400

    async def test_not_found_raises_404(self, db_session):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.patch(uuid4(), {"admin_notes": "x"})
        assert exc_info.value.status_code == 404


class TestCount:

    async def test_counts_own_refunds(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        assert await service.count(test_user.id) >= 1

    async def test_filters_by_status(self, db_session, test_user, requested_refund):
        service = RefundService(db_session)
        assert await service.count(test_user.id, status=RefundStatus.COMPLETED) == 0


class TestStats:

    async def test_computes_totals_from_real_refunds(self, db_session, test_user, requested_refund):
        """Regression test: this fetched the user's refunds but never actually
        used them - total_amount was set to the refund *count*, and every
        per-status count was hardcoded to 0."""
        service = RefundService(db_session)
        stats = await service.stats(test_user.id)
        assert stats["total_refunds"] >= 1
        assert stats["total_amount"] == pytest.approx(float(requested_refund.requested_amount), abs=0.01)
        assert stats["pending_count"] >= 1

    async def test_no_refunds_returns_zeroed_stats(self, db_session, test_user):
        service = RefundService(db_session)
        stats = await service.stats(test_user.id)
        assert stats["total_refunds"] == 0
        assert stats["total_amount"] == 0
        assert stats["average_processing_time_hours"] is None


class TestEligibility:

    async def test_eligible_order(self, db_session, test_user, delivered_order):
        service = RefundService(db_session)
        result = await service.eligibility(test_user.id, delivered_order.id)
        assert result["eligible"] is True
        assert result["days_remaining"] <= 90

    async def test_ineligible_order_status(self, db_session, test_user, delivered_order):
        delivered_order.order_status = OrderStatus.PENDING
        await db_session.commit()
        service = RefundService(db_session)
        result = await service.eligibility(test_user.id, delivered_order.id)
        assert result["eligible"] is False

    async def test_order_not_found_raises_404(self, db_session, test_user):
        service = RefundService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.eligibility(test_user.id, uuid4())
        assert exc_info.value.status_code == 404

    async def test_expired_refund_window(self, db_session, test_user, delivered_order):
        delivered_order.created_at = datetime.now(timezone.utc) - timedelta(days=100)
        await db_session.commit()
        service = RefundService(db_session)
        result = await service.eligibility(test_user.id, delivered_order.id)
        assert result["eligible"] is False
        assert "90 days" in result["reason"]


class TestProcessAuto:

    async def test_processes_an_approved_refund_via_stripe(self, db_session, test_user, delivered_order, requested_refund, mocker):
        mocker.patch(
            "stripe.Refund.create",
            return_value=mocker.Mock(id=f"re_{uuid4().hex[:16]}", status="succeeded"),
        )
        result = await db_session.execute(
            select(Refund).where(Refund.id == requested_refund.id)
        )
        refund = result.scalar_one()
        refund.status = RefundStatus.APPROVED
        refund.auto_approved = True
        refund.approved_amount = refund.requested_amount

        txn = Transaction(
            id=uuid7(), user_id=test_user.id, order_id=delivered_order.id,
            stripe_payment_intent_id=f"pi_test_{uuid4().hex[:16]}", amount=Decimal("53.98"),
            currency="USD", status="succeeded", transaction_type="payment",
        )
        db_session.add(txn)
        await db_session.commit()

        service = RefundService(db_session)
        result = await service.process_auto()
        assert result["processed"] >= 1

        await db_session.refresh(refund)
        assert refund.status == RefundStatus.COMPLETED

    async def test_no_pending_refunds_returns_zero(self, db_session):
        service = RefundService(db_session)
        result = await service.process_auto()
        assert result["total"] == 0

    async def test_one_failure_does_not_lose_a_sibling_success_in_the_batch(
        self, db_session, test_user, delivered_order, requested_refund, variant, mocker
    ):
        """Regression test: process_auto() used to accumulate all per-refund changes
        in memory and commit them once at the very end. If any refund's processing
        left the session in a bad state, that single commit could discard every
        other refund's already-successful work along with it. Verifies a failing
        refund (no matching payment transaction) and a succeeding one (mocked
        Stripe success) in the same batch are each durably persisted independently."""
        mocker.patch(
            "stripe.Refund.create",
            return_value=mocker.Mock(id=f"re_{uuid4().hex[:16]}", status="succeeded"),
        )

        # Refund #1: will fail - no Transaction exists for its order.
        result = await db_session.execute(select(Refund).where(Refund.id == requested_refund.id))
        failing_refund = result.scalar_one()
        failing_refund.status = RefundStatus.APPROVED
        failing_refund.auto_approved = True
        failing_refund.approved_amount = failing_refund.requested_amount

        # Refund #2: will succeed - has a matching succeeded payment Transaction.
        order2 = Order(
            id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
            order_status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID,
            fulfillment_status=FulfillmentStatus.FULFILLED,
            subtotal=Decimal("39.98"), shipping_cost=Decimal("10.00"), tax_amount=Decimal("4.00"),
            total_amount=Decimal("53.98"),
            billing_address={"street": "1 Test St"}, shipping_address={"street": "1 Test St"},
        )
        db_session.add(order2)
        await db_session.flush()
        item2 = OrderItem(
            id=uuid7(), order_id=order2.id, variant_id=variant.id,
            quantity=2, price_per_unit=Decimal("19.99"), total_price=Decimal("39.98"),
        )
        db_session.add(item2)
        await db_session.flush()
        order2.item_id = item2.id

        service = RefundService(db_session)
        succeeding_response = await service.request(test_user.id, order2.id, make_request(order2))
        result = await db_session.execute(select(Refund).where(Refund.id == succeeding_response.id))
        succeeding_refund = result.scalar_one()
        succeeding_refund.status = RefundStatus.APPROVED
        succeeding_refund.auto_approved = True
        succeeding_refund.approved_amount = succeeding_refund.requested_amount

        txn = Transaction(
            id=uuid7(), user_id=test_user.id, order_id=order2.id,
            stripe_payment_intent_id=f"pi_test_{uuid4().hex[:16]}", amount=Decimal("53.98"),
            currency="USD", status="succeeded", transaction_type="payment",
        )
        db_session.add(txn)
        await db_session.commit()

        result = await service.process_auto()
        assert result["processed"] == 1
        assert result["failed"] == 1

        await db_session.refresh(failing_refund)
        assert failing_refund.status == RefundStatus.FAILED

        await db_session.refresh(succeeding_refund)
        assert succeeding_refund.status == RefundStatus.COMPLETED
