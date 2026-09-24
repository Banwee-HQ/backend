"""Tests for services/commerce/orders.py - OrderService.

tests/api/commerce/test_orders.py already covers the full checkout round-trip
through the API; this file targets OrderService methods directly (list, get,
cancel, update_status, tracking, payments, reorder, invoice, notes CRUD,
statistics, and the private pricing/tax helpers) that aren't reachable, or
aren't reachable with enough branch coverage, from the HTTP layer alone.
"""

import asyncio
import pytest
from types import SimpleNamespace
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.exceptions import APIException
from core.utils.uuid_utils import uuid7
from core.utils.encryption import PasswordManager
from services.commerce.orders import OrderService, get_currency_from_address
from services.commerce.discounts import DiscountEngine
from services.commerce.cart import CartService
from schemas.commerce.orders import Checkout
from models.commerce.discounts import DiscountType
from models.catalog.category import Category
from models.catalog.product import Product, ProductVariant
from models.catalog.inventories import Inventory, StockAdjustment
from models.commerce.cart import Cart, CartItem
from models.accounts.user import Address, User, UserRole
from models.commerce.shipping import ShippingMethod
from models.commerce.payments import PaymentMethod, PaymentType, PaymentProvider, CardBrand
from models.commerce.tax_rates import TaxRate
from models.commerce.orders import Order, OrderItem, TrackingEvent, OrderStatus, PaymentStatus, FulfillmentStatus
from tests.conftest import TestingSessionLocal


# --------------------------------------------------------------------------- Fixtures ---------------------------------------------------------------------------

@pytest.fixture
async def variant(db_session) -> ProductVariant:
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    product = Product(id=uuid7(), name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    v = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("19.99"))
    db_session.add_all([category, product, v])
    await db_session.flush()
    db_session.add(Inventory(id=uuid7(), variant_id=v.id, quantity_available=50))
    await db_session.commit()
    result = await db_session.execute(
        select(ProductVariant).where(ProductVariant.id == v.id).options(selectinload(ProductVariant.product))
    )
    return result.scalar_one()


@pytest.fixture
async def address(db_session, test_user) -> Address:
    a = Address(id=uuid7(), user_id=test_user.id, street="1 Test St", city="Lagos", state="Lagos", country="NG", post_code="100001")
    db_session.add(a)
    await db_session.commit()
    return a


@pytest.fixture
async def shipping_method(db_session) -> ShippingMethod:
    m = ShippingMethod(id=uuid7(), name="Standard", price=Decimal("10.00"), estimated_days=5, is_active=True)
    db_session.add(m)
    await db_session.commit()
    return m


@pytest.fixture
async def payment_method(db_session, test_user) -> PaymentMethod:
    pm = PaymentMethod(
        id=uuid7(), user_id=test_user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
        last_four="4242", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
        stripe_payment_method_id=f"pm_test_{uuid4().hex[:16]}", is_default=True, is_active=True,
    )
    db_session.add(pm)
    await db_session.commit()
    return pm


@pytest.fixture
async def cart_with_item(db_session, test_user, variant) -> Cart:
    cart = Cart(id=uuid7(), user_id=test_user.id)
    db_session.add(cart)
    await db_session.flush()
    item = CartItem(id=uuid7(), cart_id=cart.id, product_id=variant.product_id, variant_id=variant.id,
                     quantity=2, price_per_unit=variant.base_price)
    db_session.add(item)
    await db_session.commit()
    result = await db_session.execute(
        select(Cart).where(Cart.id == cart.id).options(
            selectinload(Cart.items).selectinload(CartItem.variant).selectinload(ProductVariant.product)
        )
    )
    return result.scalar_one()


@pytest.fixture
async def variant_without_inventory(db_session) -> ProductVariant:
    """A variant with no Inventory row at all (distinct from a zero-quantity one)."""
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    product = Product(id=uuid7(), name="No Inventory Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    v = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("9.99"))
    db_session.add_all([category, product, v])
    await db_session.flush()
    await db_session.commit()
    # Preload .product into the identity map (like the `variant` fixture above) so a later lazy access from a freshly-queried OrderItem resolves from memory instead of attempting a real lazy-load, which would crash with MissingGreenlet in this async context.
    result = await db_session.execute(
        select(ProductVariant).where(ProductVariant.id == v.id).options(selectinload(ProductVariant.product))
    )
    return result.scalar_one()


@pytest.fixture
async def out_of_stock_variant(db_session) -> ProductVariant:
    category = Category(id=uuid7(), name="Cat", slug=f"cat-{uuid4().hex[:8]}")
    product = Product(id=uuid7(), name="Sold Out Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category.id)
    v = ProductVariant(id=uuid7(), product_id=product.id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("9.99"))
    db_session.add_all([category, product, v])
    await db_session.flush()
    db_session.add(Inventory(id=uuid7(), variant_id=v.id, quantity_available=0))
    await db_session.commit()
    return v


@pytest.fixture
def checkout_request(address, shipping_method, payment_method) -> Checkout:
    return Checkout(
        shipping_address_id=address.id,
        shipping_method_id=shipping_method.id,
        payment_method_id=payment_method.id,
        notes="Leave at door",
    )


@pytest.fixture
async def existing_order(db_session, test_user, variant) -> Order:
    """A confirmed order with one item, inserted directly - no live payment needed."""
    order = Order(
        id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
        order_status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.UNFULFILLED,
        subtotal=Decimal("39.98"), shipping_cost=Decimal("10.00"), tax_amount=Decimal("0.00"),
        total_amount=Decimal("49.98"),
        billing_address={"street": "1 Test St", "city": "Lagos", "state": "Lagos", "country": "NG", "post_code": "100001"},
        shipping_address={"street": "1 Test St", "city": "Lagos", "state": "Lagos", "country": "NG", "post_code": "100001"},
        shipping_method="Standard",
    )
    db_session.add(order)
    await db_session.flush()
    item = OrderItem(id=uuid7(), order_id=order.id, variant_id=variant.id, quantity=2,
                      price_per_unit=variant.base_price, total_price=variant.base_price * 2)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(order)
    return order


# --------------------------------------------------------------------------- get_currency_from_address (module-level helper) ---------------------------------------------------------------------------

class TestGetCurrencyFromAddress:

    def test_known_country_code(self):
        assert get_currency_from_address("NG") == "NGN"

    def test_known_full_name_case_insensitive(self):
        assert get_currency_from_address("canada") == "CAD"

    def test_unknown_country_defaults_to_usd(self):
        assert get_currency_from_address("Atlantis") == "USD"

    def test_empty_defaults_to_usd(self):
        assert get_currency_from_address("") == "USD"

    def test_none_defaults_to_usd(self):
        assert get_currency_from_address(None) == "USD"


# --------------------------------------------------------------------------- calc_pricing ---------------------------------------------------------------------------

class TestCalcPricing:

    async def test_calculates_subtotal_shipping_and_total(self, db_session, cart_with_item, address, shipping_method):
        service = OrderService(db_session)
        result = await service.calc_pricing(cart_with_item.items, address, shipping_method.id)
        assert result["subtotal"] == Decimal("39.98")
        assert result["shipping_cost"] == Decimal("10.00")
        assert result["currency"] == "USD"
        assert result["total_amount"] >= result["subtotal"]

    async def test_inactive_shipping_method_costs_nothing(self, db_session, cart_with_item, address, shipping_method):
        shipping_method.is_active = False
        await db_session.commit()
        service = OrderService(db_session)
        result = await service.calc_pricing(cart_with_item.items, address, shipping_method.id)
        assert result["shipping_cost"] == Decimal("0.00")

    async def test_applies_percentage_discount_code(self, db_session, cart_with_item, address, shipping_method):
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"pct{uuid4().hex[:6]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=10,
                             valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=10))
        service = OrderService(db_session)
        result = await service.calc_pricing(cart_with_item.items, address, shipping_method.id, discount_code=code)
        assert result["discount_amount"] > Decimal("0.00")
        assert result["breakdown"]["discount"]["code"] == code.upper()

    async def test_applies_fixed_amount_discount_code(self, db_session, cart_with_item, address, shipping_method):
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"fix{uuid4().hex[:6]}"
        await engine.create(code=code, discount_type=DiscountType.FIXED_AMOUNT.value, value=5,
                             valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=10))
        service = OrderService(db_session)
        result = await service.calc_pricing(cart_with_item.items, address, shipping_method.id, discount_code=code)
        assert result["discount_amount"] == Decimal("5.00")

    async def test_applies_free_shipping_discount_code(self, db_session, cart_with_item, address, shipping_method):
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"ship{uuid4().hex[:6]}"
        await engine.create(code=code, discount_type=DiscountType.FREE_SHIPPING.value, value=0,
                             valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=10))
        service = OrderService(db_session)
        result = await service.calc_pricing(cart_with_item.items, address, shipping_method.id, discount_code=code)
        assert result["shipping_cost"] == Decimal("0.00")
        assert result["discount_amount"] == Decimal("10.00")

    async def test_unknown_discount_code_is_silently_ignored(self, db_session, cart_with_item, address, shipping_method):
        service = OrderService(db_session)
        result = await service.calc_pricing(cart_with_item.items, address, shipping_method.id, discount_code=f"nope{uuid4().hex[:6]}")
        assert result["discount_amount"] == Decimal("0.00")


# --------------------------------------------------------------------------- validate_checkout ---------------------------------------------------------------------------

class TestValidateCheckout:

    async def test_valid_checkout_returns_pricing(self, db_session, test_user, cart_with_item, checkout_request):
        service = OrderService(db_session)
        result = await service.validate_checkout(test_user.id, checkout_request)
        assert result["valid"] is True
        assert result["can_proceed"] is True
        assert result["pricing"] is not None

    async def test_empty_cart_is_invalid(self, db_session, test_user, checkout_request):
        service = OrderService(db_session)
        result = await service.validate_checkout(test_user.id, checkout_request)
        assert result["valid"] is False
        assert result["can_proceed"] is False

    async def test_invalid_shipping_address_is_rejected(self, db_session, test_user, cart_with_item, shipping_method, payment_method):
        req = Checkout(shipping_address_id=uuid4(), shipping_method_id=shipping_method.id, payment_method_id=payment_method.id)
        service = OrderService(db_session)
        result = await service.validate_checkout(test_user.id, req)
        assert result["valid"] is False
        assert any(e.get("field") == "shipping_address_id" for e in result["errors"])

    async def test_invalid_shipping_method_is_rejected(self, db_session, test_user, cart_with_item, address, payment_method):
        req = Checkout(shipping_address_id=address.id, shipping_method_id=uuid4(), payment_method_id=payment_method.id)
        service = OrderService(db_session)
        result = await service.validate_checkout(test_user.id, req)
        assert result["valid"] is False
        assert any(e.get("field") == "shipping_method_id" for e in result["errors"])

    async def test_invalid_payment_method_is_rejected(self, db_session, test_user, cart_with_item, address, shipping_method):
        req = Checkout(shipping_address_id=address.id, shipping_method_id=shipping_method.id, payment_method_id=uuid4())
        service = OrderService(db_session)
        result = await service.validate_checkout(test_user.id, req)
        assert result["valid"] is False
        assert any(e.get("field") == "payment_method_id" for e in result["errors"])

    async def test_frontend_price_mismatch_produces_warning(self, db_session, test_user, cart_with_item, checkout_request):
        checkout_request.frontend_calculated_total = 1.0
        service = OrderService(db_session)
        result = await service.validate_checkout(test_user.id, checkout_request)
        assert result["valid"] is True
        assert any(w["type"] == "price_mismatch" for w in result["warnings"])


# --------------------------------------------------------------------------- create() (checkout) ---------------------------------------------------------------------------

class TestCreate:

    async def test_successful_checkout_increments_variant_purchase_count(
        self, db_session, test_user, variant, cart_with_item, checkout_request, mocker
    ):
        """The item bought is the variant, not the parent product - purchase_count lives
        on ProductVariant and must reflect the quantity actually ordered."""
        assert variant.purchase_count == 0
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded"},
        )

        service = OrderService(db_session)
        await service.create(test_user.id, checkout_request, BackgroundTasks())

        await db_session.refresh(variant)
        assert variant.purchase_count == 2  # cart_with_item requests quantity=2

    async def test_order_survives_a_failed_post_payment_cart_clear(
        self, db_session, test_user, variant, cart_with_item, checkout_request, mocker
    ):
        """Regression test: the order's confirmed/paid state and the best-effort
        cart-clearing step used to share one uncommitted transaction. If clearing
        the cart failed after a successful Stripe charge, the whole transaction -
        including the order itself - rolled back, leaving the customer charged
        with no matching order. Simulates that failure and confirms the order is
        still durably committed as paid regardless."""
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded"},
        )
        from models.commerce.cart import CartItem as CartItemModel

        real_execute = db_session.execute

        async def failing_execute(statement, *args, **kwargs):
            if statement.__class__.__name__ == "Delete" and statement.table.name == CartItemModel.__tablename__:
                raise Exception("Simulated DB failure during cart clear")
            return await real_execute(statement, *args, **kwargs)

        mocker.patch.object(db_session, "execute", side_effect=failing_execute)

        service = OrderService(db_session)
        order = await service.create(test_user.id, checkout_request, BackgroundTasks())

        result = await real_execute(select(Order).where(Order.id == order.id))
        persisted_order = result.scalar_one()
        assert persisted_order.payment_status == PaymentStatus.PAID
        assert persisted_order.order_status == OrderStatus.CONFIRMED

    async def test_payment_declined_raises_400(self, db_session, test_user, cart_with_item, checkout_request, mocker):
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "failed", "error": "Card declined"},
        )
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create(test_user.id, checkout_request, BackgroundTasks())
        assert exc_info.value.status_code == 400

    async def test_insufficient_stock_fails_before_charging_payment(
        self, db_session, test_user, variant, cart_with_item, checkout_request, mocker
    ):
        """Regression test: inventory must be locked/decremented before payment is
        charged. Two requests racing for the same last unit must have the loser fail
        cleanly (no charge, no orphaned order/transaction) instead of charging the
        card and then rolling back the DB out from under it."""
        inventory_result = await db_session.execute(
            select(Inventory).where(Inventory.variant_id == variant.id)
        )
        inventory = inventory_result.scalar_one()
        inventory.quantity_available = 1  # cart_with_item requests quantity=2
        await db_session.commit()

        mock_payment = mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded"},
        )
        service = OrderService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.create(test_user.id, checkout_request, BackgroundTasks())
        assert exc_info.value.status_code == 400
        assert "Insufficient stock" in exc_info.value.message
        mock_payment.assert_not_called()

        await db_session.refresh(inventory)
        assert inventory.quantity_available == 1

    async def test_out_of_stock_item_is_skipped_and_stays_in_cart(
        self, db_session, test_user, variant, cart_with_item, out_of_stock_variant, checkout_request, mocker
    ):
        """A quantity-0 cart item (e.g. from CartService.add_to_cart capping to stock)
        must not block checkout of the rest of the cart, and must survive it untouched."""
        cart = cart_with_item
        oos_item = CartItem(
            id=uuid7(), cart_id=cart.id, product_id=out_of_stock_variant.product_id,
            variant_id=out_of_stock_variant.id, quantity=0, price_per_unit=out_of_stock_variant.base_price,
        )
        db_session.add(oos_item)
        await db_session.commit()

        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded"},
        )

        service = OrderService(db_session)
        order = await service.create(test_user.id, checkout_request, BackgroundTasks())

        assert len(order.items) == 1
        assert order.items[0].variant_id == variant.id

        remaining = await db_session.execute(select(CartItem).where(CartItem.cart_id == cart.id))
        remaining_items = remaining.scalars().all()
        assert len(remaining_items) == 1
        assert remaining_items[0].variant_id == out_of_stock_variant.id
        assert remaining_items[0].quantity == 0

    async def test_concurrent_checkouts_for_the_last_unit_do_not_oversell(self, mocker):
        """True concurrency test: two independent sessions race to buy the last unit
        of stock at the same time. The row lock in adjust_stock() must serialize them -
        exactly one order succeeds, the other fails cleanly, and stock never goes negative.

        Setup uses its own genuinely-committed connection rather than the db_session
        fixture: db_session runs each test in a SAVEPOINT for isolation, which the
        independent racer connections below (real concurrency needs real separate
        connections) can never see.
        """
        variant_id, product_id, category_id, shipping_method_id = uuid7(), uuid7(), uuid7(), uuid7()
        async with TestingSessionLocal() as setup_session:
            setup_session.add_all([
                Category(id=category_id, name="Cat", slug=f"cat-{uuid4().hex[:8]}"),
                Product(id=product_id, name="Widget", slug=f"widget-{uuid4().hex[:8]}", category_id=category_id),
            ])
            await setup_session.flush()
            setup_session.add_all([
                ProductVariant(id=variant_id, product_id=product_id, sku=f"SKU-{uuid4().hex[:8]}", name="Default", base_price=Decimal("19.99")),
                ShippingMethod(id=shipping_method_id, name="Standard", price=Decimal("10.00"), estimated_days=5, is_active=True),
            ])
            await setup_session.flush()
            setup_session.add(Inventory(id=uuid7(), variant_id=variant_id, quantity_available=1))
            await setup_session.commit()

        password_manager = PasswordManager()
        racer_user_ids = []

        async def make_racer(session):
            user = User(
                id=uuid7(), email=f"racer_{uuid4().hex[:8]}@example.com",
                hashed_password=password_manager.hash_password("TestPassword123!"),
                firstname="Racer", lastname="User", role=UserRole.CUSTOMER,
                account_status="active", verification_status="verified",
            )
            racer_user_ids.append(user.id)
            session.add(user)
            await session.flush()

            racer_address = Address(
                id=uuid7(), user_id=user.id, street="1 Race St", city="Lagos",
                state="Lagos", country="NG", post_code="100001",
            )
            payment_method = PaymentMethod(
                id=uuid7(), user_id=user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
                last_four="4242", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
                stripe_payment_method_id=f"pm_test_{uuid4().hex[:16]}", is_default=True, is_active=True,
            )
            cart = Cart(id=uuid7(), user_id=user.id)
            session.add_all([racer_address, payment_method, cart])
            await session.flush()

            cart_item = CartItem(
                id=uuid7(), cart_id=cart.id, product_id=product_id, variant_id=variant_id,
                quantity=1, price_per_unit=Decimal("19.99"),
            )
            session.add(cart_item)
            await session.commit()

            checkout = Checkout(
                shipping_address_id=racer_address.id,
                shipping_method_id=shipping_method_id,
                payment_method_id=payment_method.id,
            )
            return user, checkout

        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded"},
        )

        try:
            async with TestingSessionLocal() as session_a, TestingSessionLocal() as session_b:
                user_a, checkout_a = await make_racer(session_a)
                user_b, checkout_b = await make_racer(session_b)

                results = await asyncio.gather(
                    OrderService(session_a).create(user_a.id, checkout_a, BackgroundTasks()),
                    OrderService(session_b).create(user_b.id, checkout_b, BackgroundTasks()),
                    return_exceptions=True,
                )

            successes = [r for r in results if not isinstance(r, Exception)]
            failures = [r for r in results if isinstance(r, Exception)]
            assert len(successes) == 1, f"expected exactly one winner, got: {results}"
            assert len(failures) == 1
            assert "Insufficient stock" in str(getattr(failures[0], "message", failures[0]))

            async with TestingSessionLocal() as check_session:
                result = await check_session.execute(select(Inventory).where(Inventory.variant_id == variant_id))
                assert result.scalar_one().quantity_available == 0
        finally:
            async with TestingSessionLocal() as cleanup_session:
                await cleanup_session.execute(StockAdjustment.__table__.delete().where(
                    StockAdjustment.inventory_id.in_(select(Inventory.id).where(Inventory.variant_id == variant_id))
                ))
                for user_id in racer_user_ids:
                    await cleanup_session.execute(OrderItem.__table__.delete().where(
                        OrderItem.order_id.in_(select(Order.id).where(Order.user_id == user_id))
                    ))
                    await cleanup_session.execute(Order.__table__.delete().where(Order.user_id == user_id))
                    await cleanup_session.execute(CartItem.__table__.delete().where(
                        CartItem.cart_id.in_(select(Cart.id).where(Cart.user_id == user_id))
                    ))
                    await cleanup_session.execute(Cart.__table__.delete().where(Cart.user_id == user_id))
                    await cleanup_session.execute(PaymentMethod.__table__.delete().where(PaymentMethod.user_id == user_id))
                    await cleanup_session.execute(Address.__table__.delete().where(Address.user_id == user_id))
                    await cleanup_session.execute(User.__table__.delete().where(User.id == user_id))
                await cleanup_session.execute(Inventory.__table__.delete().where(Inventory.variant_id == variant_id))
                await cleanup_session.execute(ShippingMethod.__table__.delete().where(ShippingMethod.id == shipping_method_id))
                await cleanup_session.execute(ProductVariant.__table__.delete().where(ProductVariant.id == variant_id))
                await cleanup_session.execute(Product.__table__.delete().where(Product.id == product_id))
                await cleanup_session.execute(Category.__table__.delete().where(Category.id == category_id))
                await cleanup_session.commit()


# --------------------------------------------------------------------------- list ---------------------------------------------------------------------------

class TestList:

    async def test_lists_own_orders(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=test_user.id)
        assert result["pagination"]["total"] >= 1
        assert any(str(o["id"]) == str(existing_order.id) for o in result["orders"])

    async def test_filters_by_status(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=test_user.id, status="confirmed")
        assert all(o["order_status"] == "confirmed" for o in result["orders"])

    async def test_filters_by_search(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=test_user.id, search=existing_order.order_number[:8])
        assert any(str(o["id"]) == str(existing_order.id) for o in result["orders"])

    async def test_filters_by_q(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=test_user.id, q=str(existing_order.id)[:8])
        assert any(str(o["id"]) == str(existing_order.id) for o in result["orders"])

    async def test_filters_by_price_range_excludes_out_of_range(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=test_user.id, min_price=1000, max_price=2000)
        assert not any(str(o["id"]) == str(existing_order.id) for o in result["orders"])

    async def test_admin_lists_all_orders(self, db_session, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=None)
        assert result["pagination"]["total"] >= 1

    async def test_sort_by_total_ascending(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=test_user.id, sort_by="total", sort_order="asc")
        assert result["orders"]

    async def test_date_range_filters(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        result = await service.list(user_id=test_user.id, date_from=future)
        assert not any(str(o["id"]) == str(existing_order.id) for o in result["orders"])


# --------------------------------------------------------------------------- get ---------------------------------------------------------------------------

class TestGet:

    async def test_returns_order_for_owner(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.get(existing_order.id, test_user.id)
        assert result.id == existing_order.id

    async def test_returns_none_for_unknown_id(self, db_session, test_user):
        service = OrderService(db_session)
        assert await service.get(uuid4(), test_user.id) is None

    async def test_admin_can_fetch_any_order(self, db_session, existing_order):
        service = OrderService(db_session)
        result = await service.get(existing_order.id)
        assert result.id == existing_order.id


# --------------------------------------------------------------------------- cancel ---------------------------------------------------------------------------

class TestCancel:

    async def test_cancels_pending_order_and_restores_stock(self, db_session, test_user, variant, existing_order):
        # Unpaid, so this exercises restocking only; paid cancellations refund (see test_orders API tests).
        existing_order.order_status = OrderStatus.PENDING
        existing_order.payment_status = PaymentStatus.PENDING
        await db_session.commit()
        service = OrderService(db_session)
        result = await service.cancel(existing_order.id, test_user.id)
        assert result.order_status == OrderStatus.CANCELLED

    async def test_not_found_raises_404(self, db_session, test_user):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.cancel(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404

    async def test_shipped_order_cannot_be_cancelled(self, db_session, test_user, existing_order):
        existing_order.order_status = OrderStatus.SHIPPED
        await db_session.commit()
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.cancel(existing_order.id, test_user.id)
        assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------- update_status / deliver / ship ---------------------------------------------------------------------------

class TestUpdateStatus:

    async def test_confirms_order_and_sets_timestamp(self, db_session, existing_order):
        existing_order.order_status = OrderStatus.PENDING
        existing_order.confirmed_at = None
        await db_session.commit()
        service = OrderService(db_session)
        order = await service.update_status(existing_order.id, "confirmed")
        assert order.order_status == OrderStatus.CONFIRMED
        assert order.confirmed_at is not None

    async def test_invalid_status_raises_400(self, db_session, existing_order):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_status(existing_order.id, "not-a-status")
        assert exc_info.value.status_code == 400

    async def test_not_found_raises_404(self, db_session):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_status(uuid4(), "confirmed")
        assert exc_info.value.status_code == 404

    async def test_shipped_status_sends_email(self, db_session, existing_order, mocker):
        mock = mocker.patch("services.accounts.email.EmailService.send_shipping_update", return_value=None)
        service = OrderService(db_session)
        order = await service.update_status(
            existing_order.id, "shipped", tracking_number="TRACK1", carrier_name="UPS",
            background_tasks=BackgroundTasks()
        )
        assert order.order_status == OrderStatus.SHIPPED
        mock.assert_called_once()

    async def test_delivered_status_sends_email(self, db_session, existing_order, mocker):
        mock = mocker.patch("services.accounts.email.EmailService.send_order_delivered", return_value=None)
        service = OrderService(db_session)
        order = await service.update_status(existing_order.id, "delivered", background_tasks=BackgroundTasks())
        assert order.order_status == OrderStatus.DELIVERED
        mock.assert_called_once()

    async def test_auto_populates_carrier_from_shipping_method(self, db_session, existing_order):
        # A method name unique to this test - "Standard" collides with rows left behind by other tests, and lookup-by-name has no ordering guarantee, so a shared name could resolve to the wrong row.
        unique_name = f"Method-{uuid4().hex[:8]}"
        existing_order.shipping_method = unique_name
        db_session.add(ShippingMethod(id=uuid7(), name=unique_name, price=Decimal("10.00"),
                                       estimated_days=5, is_active=True, carrier="ups"))
        await db_session.commit()
        service = OrderService(db_session)
        order = await service.update_status(existing_order.id, "shipped")
        assert order.carrier == "ups"

    async def test_deliver_marks_order_delivered(self, db_session, existing_order):
        service = OrderService(db_session)
        result = await service.deliver(str(existing_order.id), notes="Left at door")
        assert result.order_status == OrderStatus.DELIVERED

    async def test_ship_marks_order_shipped(self, db_session, existing_order):
        service = OrderService(db_session)
        result = await service.ship(str(existing_order.id), carrier="ups", tracking_number="TRACK1")
        assert result.order_status == OrderStatus.SHIPPED
        assert result.tracking_number == "TRACK1"


# --------------------------------------------------------------------------- tracking / payments / tracking_public ---------------------------------------------------------------------------

class TestTracking:

    async def test_returns_tracking_events_sorted_newest_first(self, db_session, test_user, existing_order):
        db_session.add(TrackingEvent(order_id=existing_order.id, status="confirmed", description="Confirmed", location="System"))
        await db_session.commit()
        service = OrderService(db_session)
        result = await service.tracking(existing_order.id, test_user.id)
        assert result["order_id"] == str(existing_order.id)
        assert len(result["tracking_events"]) >= 1

    async def test_not_found_raises_404(self, db_session, test_user):
        service = OrderService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.tracking(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


class TestPaymentsInfo:

    async def test_returns_empty_lists_when_no_payments(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.payments(existing_order.id, test_user.id)
        assert result["payment_intents"] == []
        assert result["transactions"] == []

    async def test_not_found_raises_404(self, db_session, test_user):
        service = OrderService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.payments(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


class TestTrackingPublic:

    async def test_by_order_number(self, db_session, existing_order):
        service = OrderService(db_session)
        result = await service.tracking_public(existing_order.order_number)
        assert result["order_number"] == existing_order.order_number

    async def test_by_uuid(self, db_session, existing_order):
        service = OrderService(db_session)
        result = await service.tracking_public(str(existing_order.id))
        assert result["order_number"] == existing_order.order_number

    async def test_not_found_raises_404(self, db_session):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.tracking_public("NOPE-DOES-NOT-EXIST")
        assert exc_info.value.status_code == 404

    async def test_only_includes_public_safe_events(self, db_session, existing_order):
        db_session.add_all([
            TrackingEvent(order_id=existing_order.id, status="payment_failed", description="x", location="System"),
            TrackingEvent(order_id=existing_order.id, status="shipped", description="y", location="Transit"),
        ])
        await db_session.commit()
        service = OrderService(db_session)
        result = await service.tracking_public(str(existing_order.id))
        statuses = [e["status"] for e in result["tracking_events"]]
        assert "shipped" in statuses
        assert "payment_failed" not in statuses


# --------------------------------------------------------------------------- reorder ---------------------------------------------------------------------------

class TestReorder:

    async def test_adds_available_items_to_cart(self, db_session, test_user, existing_order, variant):
        service = OrderService(db_session)
        result = await service.reorder(existing_order.id, test_user.id)
        assert result["cart_items"] >= 1

    async def test_original_order_not_found(self, db_session, test_user):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.reorder(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404

    async def test_no_items_available_when_variant_inactive(self, db_session, test_user, existing_order, variant):
        variant.is_active = False
        await db_session.commit()
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.reorder(existing_order.id, test_user.id)
        assert exc_info.value.status_code == 400


# --------------------------------------------------------------------------- invoice ---------------------------------------------------------------------------

class TestInvoice:

    async def test_generates_invoice(self, db_session, test_user, existing_order, mocker):
        """Regression test: this called InvoiceGenerator.invoice(), which doesn't
        exist (the real method is generate_invoice) - every invoice request 500'd."""
        mocker.patch(
            "core.utils.invoice_generator.InvoiceGenerator.generate_invoice",
            return_value={"format": "html", "content": "<html></html>"},
        )
        service = OrderService(db_session)
        result = await service.invoice(existing_order.id, test_user.id)
        assert result["format"] == "html"

    async def test_not_found_raises_404(self, db_session, test_user):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.invoice(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------- notes CRUD ---------------------------------------------------------------------------

class TestNotes:

    async def test_add_and_list_notes(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        add_result = await service.add_note(existing_order.id, test_user.id, "Please gift wrap")
        assert "Please gift wrap" in add_result["all_notes"]

        list_result = await service.notes(existing_order.id, test_user.id)
        assert list_result["total_notes"] == 1
        assert list_result["notes"][0]["note"] == "Please gift wrap"

    async def test_get_note_by_index(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        await service.add_note(existing_order.id, test_user.id, "First note")
        note = await service.get_note(existing_order.id, test_user.id, 0)
        assert note["note"] == "First note"

    async def test_get_note_out_of_range_returns_none(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        assert await service.get_note(existing_order.id, test_user.id, 5) is None

    async def test_update_note(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        await service.add_note(existing_order.id, test_user.id, "Original")
        result = await service.update_note(existing_order.id, test_user.id, 0, "Updated")
        assert result["updated_note"] == "Updated"
        notes = await service.notes(existing_order.id, test_user.id)
        assert notes["notes"][0]["note"] == "Updated"

    async def test_update_note_out_of_range_raises_404(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_note(existing_order.id, test_user.id, 0, "x")
        assert exc_info.value.status_code == 404

    async def test_delete_note(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        await service.add_note(existing_order.id, test_user.id, "To delete")
        assert await service.delete_note(existing_order.id, test_user.id, 0) is True
        notes = await service.notes(existing_order.id, test_user.id)
        assert notes["total_notes"] == 0

    async def test_delete_note_out_of_range_returns_false(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        assert await service.delete_note(existing_order.id, test_user.id, 5) is False

    async def test_notes_order_not_found_raises_404(self, db_session, test_user):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.notes(uuid4(), test_user.id)
        assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------- get_statistics ---------------------------------------------------------------------------

class TestGetStatistics:

    async def test_returns_totals_and_status_breakdown(self, db_session, existing_order):
        service = OrderService(db_session)
        stats = await service.get_statistics()
        assert stats["total_orders"] >= 1
        assert stats["status_breakdown"]

    async def test_filters_by_date_range(self, db_session, existing_order):
        service = OrderService(db_session)
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        stats = await service.get_statistics(date_from=future)
        assert stats["total_orders"] == 0
        assert stats["date_range"]["from"] == future

    async def test_invalid_date_is_ignored(self, db_session, existing_order):
        service = OrderService(db_session)
        stats = await service.get_statistics(date_from="not-a-date")
        assert "total_orders" in stats


# --------------------------------------------------------------------------- Private helpers ---------------------------------------------------------------------------

class TestCalculateDiscountAmount:

    def test_no_promocode_returns_zero(self, db_session):
        service = OrderService(db_session)
        assert service._calculate_discount_amount(100.0, None) == 0.0

    def test_inactive_promocode_returns_zero(self, db_session):
        service = OrderService(db_session)
        promo = SimpleNamespace(is_active=False, discount_type="percentage", value=10, maximum_discount_amount=None)
        assert service._calculate_discount_amount(100.0, promo) == 0.0

    def test_percentage_discount(self, db_session):
        service = OrderService(db_session)
        promo = SimpleNamespace(is_active=True, discount_type="percentage", value=10, maximum_discount_amount=None)
        assert service._calculate_discount_amount(100.0, promo) == 10.0

    def test_percentage_discount_capped_by_maximum(self, db_session):
        service = OrderService(db_session)
        promo = SimpleNamespace(is_active=True, discount_type="percentage", value=50, maximum_discount_amount=20)
        assert service._calculate_discount_amount(100.0, promo) == 20.0

    def test_fixed_amount_discount(self, db_session):
        service = OrderService(db_session)
        promo = SimpleNamespace(is_active=True, discount_type="fixed", value=15, maximum_discount_amount=None)
        assert service._calculate_discount_amount(100.0, promo) == 15.0

    def test_discount_never_exceeds_subtotal(self, db_session):
        service = OrderService(db_session)
        promo = SimpleNamespace(is_active=True, discount_type="fixed", value=500, maximum_discount_amount=None)
        assert service._calculate_discount_amount(100.0, promo) == 100.0


class TestGetTaxRate:

    async def test_no_address_returns_zero(self, db_session):
        service = OrderService(db_session)
        assert await service._get_tax_rate(None) == 0.0

    async def test_state_specific_rate_found(self, db_session):
        # flush (not commit) - the row only needs to be visible to this session's own SELECT, and db_session's teardown rollback then discards it instead of polluting the DB for every future test run.
        db_session.add(TaxRate(
            id=uuid7(), country_code="XA", country_name="Test Country", province_code="TS",
            province_name="Test State", tax_rate=Decimal("0.0725"), tax_name="Sales Tax", is_active=True,
        ))
        await db_session.flush()
        service = OrderService(db_session)
        result = await service._get_tax_rate({"country": "XA", "state": "TS"})
        assert float(result) == 0.0725

    async def test_falls_back_to_country_level_rate(self, db_session):
        db_session.add(TaxRate(
            id=uuid7(), country_code="XB", country_name="Test Country", province_code=None,
            tax_rate=Decimal("0.05"), is_active=True,
        ))
        await db_session.flush()
        service = OrderService(db_session)
        result = await service._get_tax_rate({"country": "XB", "state": "NOPROVINCE"})
        assert float(result) == 0.05

    async def test_no_matching_rate_returns_zero(self, db_session):
        service = OrderService(db_session)
        result = await service._get_tax_rate({"country": "ZZ", "state": "NOWHERE"})
        assert result == 0.0

    async def test_accepts_address_object_not_just_dict(self, db_session, address):
        service = OrderService(db_session)
        result = await service._get_tax_rate(address)
        assert result == 0.0 or isinstance(result, (float, Decimal))


class TestGeneratePriceUpdateMessage:

    def test_single_item_price_increase(self, db_session):
        service = OrderService(db_session)
        updates = [{"product_name": "Widget", "price_increased": True, "is_sale": False, "new_price": 12.0, "old_price": 10.0}]
        msg = service._generate_price_update_message(updates, 2.0)
        assert "Widget" in msg and "12.00" in msg

    def test_single_item_on_sale(self, db_session):
        service = OrderService(db_session)
        updates = [{"product_name": "Widget", "price_increased": True, "is_sale": True, "new_price": 8.0, "old_price": 10.0}]
        msg = service._generate_price_update_message(updates, -2.0)
        assert "sale" in msg.lower()

    def test_single_item_price_decrease(self, db_session):
        service = OrderService(db_session)
        updates = [{"product_name": "Widget", "price_increased": False, "is_sale": False, "new_price": 8.0, "old_price": 10.0}]
        msg = service._generate_price_update_message(updates, -2.0)
        assert "reduced" in msg.lower()

    def test_multiple_items_total_increase(self, db_session):
        service = OrderService(db_session)
        msg = service._generate_price_update_message([{}, {}], 5.0)
        assert "increase" in msg.lower()

    def test_multiple_items_total_decrease(self, db_session):
        service = OrderService(db_session)
        msg = service._generate_price_update_message([{}, {}], -5.0)
        assert "save" in msg.lower()

    def test_multiple_items_no_net_change(self, db_session):
        service = OrderService(db_session)
        msg = service._generate_price_update_message([{}, {}], 0.0)
        assert "updated" in msg.lower()


class TestValidateAndRecalculatePrices:

    async def test_matching_price_has_no_discrepancy(self, db_session, cart_with_item):
        service = OrderService(db_session)
        result = await service._validate_and_recalculate_prices(cart_with_item)
        assert result["valid"] is True
        assert result["price_discrepancies"] == []

    async def test_stale_cart_price_is_flagged_and_corrected(self, db_session, cart_with_item, variant):
        variant.base_price = Decimal("999.99")
        await db_session.commit()
        service = OrderService(db_session)
        result = await service._validate_and_recalculate_prices(cart_with_item)
        assert result["valid"] is True
        assert len(result["price_discrepancies"]) == 1
        assert result["validated_items"][0]["backend_price"] == Decimal("999.99")

    async def test_variant_no_longer_exists_is_invalid(self, db_session):
        fake_item = SimpleNamespace(
            saved_for_later=False, variant=SimpleNamespace(id=uuid4()),
            price_per_unit=Decimal("10.00"), total_price=Decimal("10.00"), quantity=1,
        )
        fake_cart = SimpleNamespace(items=[fake_item])
        service = OrderService(db_session)
        result = await service._validate_and_recalculate_prices(fake_cart)
        assert result["valid"] is False


class TestCalculateFinalOrderTotal:

    async def test_computes_total_with_shipping_and_tax(self, db_session, shipping_method):
        service = OrderService(db_session)
        validated_items = [{"variant_id": uuid4(), "quantity": 1, "backend_total": 50.0}]
        address_dict = {"country": "US", "state": "CA", "city": "LA", "postal_code": "90001"}
        result = await service._calculate_final_order_total(validated_items, shipping_method, address_dict)
        assert result["subtotal"] == 50.0
        assert result["total_amount"] >= 50.0

    async def test_no_shipping_method_has_zero_shipping_cost(self, db_session):
        service = OrderService(db_session)
        validated_items = [{"variant_id": uuid4(), "quantity": 1, "backend_total": 50.0}]
        address_dict = {"country": "US", "state": "CA"}
        result = await service._calculate_final_order_total(validated_items, None, address_dict)
        assert result["shipping_cost"] == 0.0

    async def test_applies_promocode_discount(self, db_session, shipping_method):
        service = OrderService(db_session)
        validated_items = [{"variant_id": uuid4(), "quantity": 1, "backend_total": 100.0}]
        address_dict = {"country": "US", "state": "CA"}
        promo = SimpleNamespace(is_active=True, discount_type="fixed", value=10, maximum_discount_amount=None)
        result = await service._calculate_final_order_total(validated_items, shipping_method, address_dict, promocode=promo)
        assert result["discount_amount"] == 10.0


class TestSendOrderEventsWithIdempotency:

    async def test_sends_confirmation_email(self, db_session, test_user, existing_order, mocker):
        mock = mocker.patch("services.accounts.email.EmailService.send_order_confirmation_email", return_value=None)
        service = OrderService(db_session)
        validated_items = [{"product_name": "Widget", "quantity": 1, "backend_price": 10.0}]
        await service._send_order_events_with_idempotency(existing_order, test_user.id, validated_items)
        mock.assert_called_once()


class TestFormatOrderResponse:

    async def test_corrects_stored_total_mismatch(self, db_session, existing_order):
        existing_order.total_amount = Decimal("1.00")
        await db_session.commit()
        result = await db_session.execute(
            select(Order).where(Order.id == existing_order.id).options(
                selectinload(Order.items).selectinload(OrderItem.variant)
            )
        )
        order = result.scalar_one()
        service = OrderService(db_session)
        response = await service._format_order_response(order)
        assert abs(response.total_amount - 49.98) < 0.01


# --------------------------------------------------------------------------- calc_pricing discount edge cases (maximum cap, never-negative floor, resilience) ---------------------------------------------------------------------------

class TestCalcPricingDiscountEdgeCases:

    async def test_percentage_discount_capped_by_maximum_discount(self, db_session, cart_with_item, address, shipping_method):
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"maxcap{uuid4().hex[:6]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=50,
                             valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=10),
                             maximum_discount=2.00)
        service = OrderService(db_session)
        result = await service.calc_pricing(cart_with_item.items, address, shipping_method.id, discount_code=code)
        # 50% of the 39.98 subtotal is 19.99, but the code's maximum_discount caps it at 2.00
        assert result["discount_amount"] == Decimal("2.00")

    async def test_total_amount_never_goes_negative(self, db_session, cart_with_item, address, shipping_method):
        """A discount larger than subtotal+shipping+tax must floor the total at 0.00,
        not go negative (which would mean paying the customer instead of charging them)."""
        engine = DiscountEngine(db_session)
        now = datetime.now(timezone.utc)
        code = f"huge{uuid4().hex[:6]}"
        await engine.create(code=code, discount_type=DiscountType.PERCENTAGE.value, value=1000,
                             valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=10))
        service = OrderService(db_session)
        result = await service.calc_pricing(cart_with_item.items, address, shipping_method.id, discount_code=code)
        assert result["total_amount"] == Decimal("0.00")

    async def test_discount_engine_error_is_swallowed_not_raised(self, db_session, cart_with_item, address, shipping_method, mocker):
        """calc_pricing must degrade gracefully (no discount applied) rather than
        failing checkout entirely if the discount engine itself errors out."""
        mocker.patch.object(DiscountEngine, "validate_discount_code", side_effect=RuntimeError("discount service down"))
        service = OrderService(db_session)
        result = await service.calc_pricing(cart_with_item.items, address, shipping_method.id, discount_code="ANYCODE")
        assert result["discount_amount"] == Decimal("0.00")


# --------------------------------------------------------------------------- validate_checkout edge cases ---------------------------------------------------------------------------

class TestValidateCheckoutEdgeCases:

    async def test_no_orderable_items_despite_cart_being_checkoutable(self, db_session, test_user, checkout_request, mocker):
        """Defensive check: guards against CartService ever reporting can_checkout=True
        for a cart whose items are all unorderable (out of stock/inactive). Not reachable
        via CartService.validate_cart's real invariants today, but exercised in isolation
        via a mocked cart_service.validate_cart result."""
        fake_cart = SimpleNamespace(items=[])
        mocker.patch.object(
            CartService, "validate_cart",
            return_value={"valid": True, "can_checkout": True, "cart": fake_cart, "issues": [], "summary": {}},
        )
        service = OrderService(db_session)
        result = await service.validate_checkout(test_user.id, checkout_request)
        assert result["valid"] is False
        assert result["can_proceed"] is False
        assert any(e.get("type") == "cart_validation" for e in result["errors"])

    async def test_unexpected_error_is_caught_and_returns_invalid(self, db_session, test_user, checkout_request, mocker):
        mocker.patch.object(CartService, "validate_cart", side_effect=RuntimeError("db exploded"))
        service = OrderService(db_session)
        result = await service.validate_checkout(test_user.id, checkout_request)
        assert result["valid"] is False
        assert result["can_proceed"] is False
        assert any(e.get("type") == "system_error" for e in result["errors"])


# --------------------------------------------------------------------------- create() edge cases ---------------------------------------------------------------------------

class TestCreateEdgeCases:

    async def test_cart_missing_at_creation_time_raises_400(self, db_session, test_user, checkout_request, mocker):
        """Defensive re-check inside create(): even if validate_checkout is bypassed/mocked
        to report success, a genuinely missing cart at the fetch-for-order-creation step
        must still fail cleanly with 400 rather than crash."""
        mocker.patch.object(
            OrderService, "validate_checkout",
            return_value={"can_proceed": True, "valid": True, "errors": [], "warnings": [],
                          "pricing": {"total": 0, "subtotal": 0, "shipping": {"cost": 0},
                                      "tax": {"amount": 0, "rate": 0}, "currency": "USD"}},
        )
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create(test_user.id, checkout_request, BackgroundTasks())
        assert exc_info.value.status_code == 400
        assert "Cart not found" in str(exc_info.value.detail)

    async def test_cart_with_no_orderable_items_at_creation_time_raises_400(
        self, db_session, test_user, out_of_stock_variant, checkout_request, mocker
    ):
        """Same defensive re-check, but for a cart that exists yet contains only a
        quantity-0 (unorderable) item."""
        cart = Cart(id=uuid7(), user_id=test_user.id)
        db_session.add(cart)
        await db_session.flush()
        db_session.add(CartItem(
            id=uuid7(), cart_id=cart.id, product_id=out_of_stock_variant.product_id,
            variant_id=out_of_stock_variant.id, quantity=0, price_per_unit=out_of_stock_variant.base_price,
        ))
        await db_session.commit()

        mocker.patch.object(
            OrderService, "validate_checkout",
            return_value={"can_proceed": True, "valid": True, "errors": [], "warnings": [],
                          "pricing": {"total": 0, "subtotal": 0, "shipping": {"cost": 0},
                                      "tax": {"amount": 0, "rate": 0}, "currency": "USD"}},
        )
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create(test_user.id, checkout_request, BackgroundTasks())
        assert exc_info.value.status_code == 400
        assert "no items available" in str(exc_info.value.detail)

    async def test_background_email_scheduling_failure_does_not_fail_the_order(
        self, db_session, test_user, variant, cart_with_item, checkout_request, mocker
    ):
        """The order is already paid and committed by the time background email
        scheduling runs - a failure there must not surface as an error to the caller."""
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded"},
        )
        service = OrderService(db_session)
        order = await service.create(test_user.id, checkout_request, background_tasks=None)
        assert order.payment_status == "paid"
        assert order.order_status == "confirmed"

    async def test_validation_failure_raises_400(self, db_session, test_user, cart_with_item, address, shipping_method):
        """The real (non-mocked) validate_checkout path: an unknown payment method
        makes can_proceed False, and create() must surface that as a clean 400."""
        req = Checkout(shipping_address_id=address.id, shipping_method_id=shipping_method.id, payment_method_id=uuid4())
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create(test_user.id, req, BackgroundTasks())
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["message"] == "Checkout validation failed"

    async def test_unexpected_payment_service_error_returns_500(
        self, db_session, test_user, cart_with_item, checkout_request, mocker
    ):
        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            side_effect=RuntimeError("Stripe connection timeout"),
        )
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create(test_user.id, checkout_request, BackgroundTasks())
        assert exc_info.value.status_code == 500
        assert "Order creation failed due to system error" in exc_info.value.detail["message"]


# --------------------------------------------------------------------------- list() edge cases ---------------------------------------------------------------------------

class TestListEdgeCases:

    async def test_invalid_date_from_is_ignored(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=test_user.id, date_from="not-a-date")
        assert any(str(o["id"]) == str(existing_order.id) for o in result["orders"])

    async def test_invalid_date_to_is_ignored(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=test_user.id, date_to="not-a-date")
        assert any(str(o["id"]) == str(existing_order.id) for o in result["orders"])

    async def test_valid_date_to_filters_results(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        result = await service.list(user_id=test_user.id, date_to=future)
        assert any(str(o["id"]) == str(existing_order.id) for o in result["orders"])

    async def test_sort_by_status(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        result = await service.list(user_id=test_user.id, sort_by="status")
        assert result["orders"]

    async def test_db_error_propagates(self, db_session, test_user, existing_order, mocker):
        mocker.patch.object(db_session, "scalar", side_effect=RuntimeError("connection lost"))
        service = OrderService(db_session)
        with pytest.raises(RuntimeError):
            await service.list(user_id=test_user.id)


# --------------------------------------------------------------------------- get() edge cases ---------------------------------------------------------------------------

class TestGetEdgeCases:

    async def test_db_error_propagates(self, db_session, test_user, existing_order, mocker):
        mocker.patch.object(db_session, "execute", side_effect=RuntimeError("connection lost"))
        service = OrderService(db_session)
        with pytest.raises(RuntimeError):
            await service.get(existing_order.id, test_user.id)


# --------------------------------------------------------------------------- cancel() edge cases ---------------------------------------------------------------------------

class TestCancelEdgeCases:

    async def test_item_with_no_inventory_record_is_skipped(self, db_session, test_user, variant_without_inventory):
        order = Order(
            id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
            order_status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING,
            fulfillment_status=FulfillmentStatus.UNFULFILLED,
            subtotal=Decimal("9.99"), shipping_cost=Decimal("0.00"), tax_amount=Decimal("0.00"),
            total_amount=Decimal("9.99"),
            billing_address={"street": "1 Test St"}, shipping_address={"street": "1 Test St"},
        )
        db_session.add(order)
        await db_session.flush()
        db_session.add(OrderItem(id=uuid7(), order_id=order.id, variant_id=variant_without_inventory.id,
                                  quantity=1, price_per_unit=Decimal("9.99"), total_price=Decimal("9.99")))
        await db_session.commit()

        service = OrderService(db_session)
        result = await service.cancel(order.id, test_user.id)
        assert result.order_status == OrderStatus.CANCELLED

    async def test_inventory_increment_failure_rolls_back_and_raises_500(
        self, db_session, test_user, existing_order, mocker
    ):
        mocker.patch(
            "services.catalog.inventory.InventoryService.increment",
            side_effect=RuntimeError("lock timeout"),
        )
        existing_order.payment_status = PaymentStatus.PENDING
        await db_session.commit()
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.cancel(existing_order.id, test_user.id)
        assert exc_info.value.status_code == 500
        await db_session.refresh(existing_order)
        assert existing_order.order_status != OrderStatus.CANCELLED


# --------------------------------------------------------------------------- update_status() edge cases ---------------------------------------------------------------------------

class TestUpdateStatusEdgeCases:

    async def test_cancelled_status_sets_cancelled_at(self, db_session, existing_order):
        service = OrderService(db_session)
        order = await service.update_status(existing_order.id, "cancelled")
        assert order.order_status == OrderStatus.CANCELLED
        assert order.cancelled_at is not None

    async def test_delivered_email_handles_non_dict_shipping_address(self, db_session, existing_order, mocker):
        mock = mocker.patch("services.accounts.email.EmailService.send_order_delivered", return_value=None)
        existing_order.shipping_address = "123 Main St, Somewhere"
        await db_session.commit()
        service = OrderService(db_session)
        await service.update_status(existing_order.id, "delivered", background_tasks=BackgroundTasks())
        assert mock.call_args.kwargs["delivery_address"] == "Your delivery address"


# --------------------------------------------------------------------------- _format_order_response edge cases ---------------------------------------------------------------------------

class TestFormatOrderResponseEdgeCases:

    async def test_missing_variant_on_item_logs_warning_and_uses_fallback(self, db_session, existing_order):
        service = OrderService(db_session)
        result = await db_session.execute(
            select(Order).where(Order.id == existing_order.id).options(
                selectinload(Order.items).selectinload(OrderItem.variant)
            )
        )
        order = result.scalar_one()
        order.items[0].variant = None  # simulate an orphaned/deleted variant reference, in-memory only
        response = await service._format_order_response(order)
        assert response.items[0].variant is None

    async def test_total_correction_db_write_failure_still_returns_corrected_total(
        self, db_session, existing_order, mocker
    ):
        existing_order.total_amount = Decimal("1.00")
        await db_session.commit()
        result = await db_session.execute(
            select(Order).where(Order.id == existing_order.id).options(
                selectinload(Order.items).selectinload(OrderItem.variant)
            )
        )
        order = result.scalar_one()
        mocker.patch.object(db_session, "commit", side_effect=RuntimeError("db write failed"))
        service = OrderService(db_session)
        response = await service._format_order_response(order)
        # Even though persisting the correction failed, the response still reflects it
        assert abs(response.total_amount - 49.98) < 0.01

    async def test_tracking_url_is_built_from_template(self, db_session, existing_order):
        unique_name = f"Method-{uuid4().hex[:8]}"
        existing_order.shipping_method = unique_name
        existing_order.tracking_number = "TRACK123"
        db_session.add(ShippingMethod(id=uuid7(), name=unique_name, price=Decimal("10.00"), estimated_days=5,
                                       is_active=True, tracking_url_template="https://track.example.com/{tracking_number}"))
        await db_session.commit()
        result = await db_session.execute(
            select(Order).where(Order.id == existing_order.id).options(
                selectinload(Order.items).selectinload(OrderItem.variant)
            )
        )
        order = result.scalar_one()
        service = OrderService(db_session)
        response = await service._format_order_response(order)
        assert response.tracking_url == "https://track.example.com/TRACK123"


# --------------------------------------------------------------------------- _validate_and_recalculate_prices edge cases ---------------------------------------------------------------------------

class TestValidateAndRecalculatePricesEdgeCases:

    async def test_missing_variant_reference_is_caught(self, db_session):
        fake_item = SimpleNamespace(saved_for_later=False, variant=None)
        fake_cart = SimpleNamespace(items=[fake_item])
        service = OrderService(db_session)
        result = await service._validate_and_recalculate_prices(fake_cart)
        assert result["valid"] is False
        assert "Price validation failed" in result["message"]


# --------------------------------------------------------------------------- _calculate_final_order_total edge cases ---------------------------------------------------------------------------

class TestCalculateFinalOrderTotalEdgeCases:

    async def test_malformed_address_raises_500(self, db_session, shipping_method):
        service = OrderService(db_session)
        validated_items = [{"variant_id": uuid4(), "quantity": 1, "backend_total": 50.0}]
        with pytest.raises(HTTPException) as exc_info:
            await service._calculate_final_order_total(validated_items, shipping_method, None)
        assert exc_info.value.status_code == 500


# --------------------------------------------------------------------------- _get_tax_rate edge cases ---------------------------------------------------------------------------

class TestGetTaxRateEdgeCases:

    async def test_malformed_address_returns_zero(self, db_session):
        service = OrderService(db_session)
        result = await service._get_tax_rate(12345)  # neither a dict nor an object exposing .get
        assert result == 0.0


# --------------------------------------------------------------------------- _send_order_events_with_idempotency edge cases ---------------------------------------------------------------------------

class TestSendOrderEventsWithIdempotencyEdgeCases:

    async def test_email_failure_propagates(self, db_session, test_user, existing_order, mocker):
        """Unlike create()'s best-effort email scheduling, this method must propagate
        failures rather than swallow them."""
        mocker.patch(
            "services.accounts.email.EmailService.send_order_confirmation_email",
            side_effect=RuntimeError("smtp down"),
        )
        service = OrderService(db_session)
        validated_items = [{"product_name": "Widget", "quantity": 1, "backend_price": 10.0}]
        with pytest.raises(RuntimeError):
            await service._send_order_events_with_idempotency(existing_order, test_user.id, validated_items)


# --------------------------------------------------------------------------- tracking / payments / tracking_public / reorder / invoice - generic error edge cases ---------------------------------------------------------------------------

class TestTrackingEdgeCases:

    async def test_db_error_returns_500(self, db_session, test_user, existing_order, mocker):
        mocker.patch.object(db_session, "execute", side_effect=RuntimeError("db down"))
        service = OrderService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.tracking(existing_order.id, test_user.id)
        assert exc_info.value.status_code == 500


class TestPaymentsInfoEdgeCases:

    async def test_db_error_returns_500(self, db_session, test_user, existing_order, mocker):
        mocker.patch.object(db_session, "execute", side_effect=RuntimeError("db down"))
        service = OrderService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.payments(existing_order.id, test_user.id)
        assert exc_info.value.status_code == 500


class TestTrackingPublicEdgeCases:

    async def test_db_error_returns_404(self, db_session, existing_order, mocker):
        mocker.patch.object(db_session, "execute", side_effect=RuntimeError("db down"))
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.tracking_public(str(existing_order.id))
        assert exc_info.value.status_code == 404


class TestReorderEdgeCases:

    async def test_unexpected_error_returns_500(self, db_session, test_user, existing_order, variant, mocker):
        mocker.patch.object(CartService, "clear_cart", side_effect=RuntimeError("boom"))
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.reorder(existing_order.id, test_user.id)
        assert exc_info.value.status_code == 500


class TestInvoiceEdgeCases:

    async def test_missing_system_library_returns_503(self, db_session, test_user, existing_order, mocker):
        mocker.patch(
            "core.utils.invoice_generator.InvoiceGenerator.generate_invoice",
            side_effect=OSError("dyld: Library not loaded: libgobject-2.0.dylib"),
        )
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.invoice(existing_order.id, test_user.id)
        assert exc_info.value.status_code == 503

    async def test_generic_invoice_failure_returns_500(self, db_session, test_user, existing_order, mocker):
        mocker.patch(
            "core.utils.invoice_generator.InvoiceGenerator.generate_invoice",
            side_effect=RuntimeError("unexpected renderer crash"),
        )
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.invoice(existing_order.id, test_user.id)
        assert exc_info.value.status_code == 500


# --------------------------------------------------------------------------- Notes CRUD edge cases ---------------------------------------------------------------------------

class TestNotesEdgeCases:

    async def test_second_note_is_appended_not_overwritten(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        await service.add_note(existing_order.id, test_user.id, "First")
        result = await service.add_note(existing_order.id, test_user.id, "Second")
        assert "First" in result["all_notes"]
        assert "Second" in result["all_notes"]

    async def test_add_note_unknown_order_raises_404(self, db_session, test_user):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.add_note(uuid4(), test_user.id, "x")
        assert exc_info.value.status_code == 404

    async def test_add_note_db_failure_raises_500(self, db_session, test_user, existing_order, mocker):
        mocker.patch.object(db_session, "commit", side_effect=RuntimeError("db down"))
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.add_note(existing_order.id, test_user.id, "x")
        assert exc_info.value.status_code == 500

    async def test_notes_db_failure_raises_500(self, db_session, test_user, existing_order, mocker):
        mocker.patch.object(db_session, "execute", side_effect=RuntimeError("db down"))
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.notes(existing_order.id, test_user.id)
        assert exc_info.value.status_code == 500

    async def test_get_note_failure_raises_500(self, db_session, test_user, existing_order, mocker):
        mocker.patch.object(OrderService, "notes", side_effect=RuntimeError("boom"))
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_note(existing_order.id, test_user.id, 0)
        assert exc_info.value.status_code == 500

    async def test_update_note_unknown_order_raises_404(self, db_session, test_user):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_note(uuid4(), test_user.id, 0, "x")
        assert exc_info.value.status_code == 404

    async def test_update_note_preserves_other_notes(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        await service.add_note(existing_order.id, test_user.id, "Keep me")
        await service.add_note(existing_order.id, test_user.id, "Change me")
        await service.update_note(existing_order.id, test_user.id, 1, "Changed")
        notes = await service.notes(existing_order.id, test_user.id)
        assert notes["notes"][0]["note"] == "Keep me"
        assert notes["notes"][1]["note"] == "Changed"

    async def test_update_note_db_failure_raises_500(self, db_session, test_user, existing_order, mocker):
        await OrderService(db_session).add_note(existing_order.id, test_user.id, "x")
        mocker.patch.object(db_session, "commit", side_effect=RuntimeError("db down"))
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_note(existing_order.id, test_user.id, 0, "y")
        assert exc_info.value.status_code == 500

    async def test_delete_note_unknown_order_raises_404(self, db_session, test_user):
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_note(uuid4(), test_user.id, 0)
        assert exc_info.value.status_code == 404

    async def test_delete_note_preserves_other_notes(self, db_session, test_user, existing_order):
        service = OrderService(db_session)
        await service.add_note(existing_order.id, test_user.id, "Delete me")
        await service.add_note(existing_order.id, test_user.id, "Keep me")
        assert await service.delete_note(existing_order.id, test_user.id, 0) is True
        notes = await service.notes(existing_order.id, test_user.id)
        assert notes["total_notes"] == 1
        assert notes["notes"][0]["note"] == "Keep me"

    async def test_delete_note_db_failure_raises_500(self, db_session, test_user, existing_order, mocker):
        await OrderService(db_session).add_note(existing_order.id, test_user.id, "x")
        mocker.patch.object(db_session, "commit", side_effect=RuntimeError("db down"))
        service = OrderService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_note(existing_order.id, test_user.id, 0)
        assert exc_info.value.status_code == 500


# --------------------------------------------------------------------------- _calculate_estimated_delivery (pure/sync helper) ---------------------------------------------------------------------------

class TestCalculateEstimatedDelivery:

    def test_delivered_order_uses_delivered_at(self, db_session):
        service = OrderService(db_session)
        delivered_at = datetime.now(timezone.utc)
        order = SimpleNamespace(delivered_at=delivered_at, order_status="delivered", id=uuid4())
        assert service._calculate_estimated_delivery(order) == delivered_at.isoformat()

    def test_cancelled_order_has_no_estimate(self, db_session):
        service = OrderService(db_session)
        order = SimpleNamespace(delivered_at=None, order_status="cancelled", id=uuid4())
        assert service._calculate_estimated_delivery(order) is None

    def test_express_shipping_uses_one_day(self, db_session):
        service = OrderService(db_session)
        shipped_at = datetime.now(timezone.utc)
        order = SimpleNamespace(delivered_at=None, order_status="shipped", shipping_method="Express Overnight",
                                 shipped_at=shipped_at, confirmed_at=None, created_at=shipped_at, id=uuid4())
        result = service._calculate_estimated_delivery(order)
        assert result == (shipped_at + timedelta(days=1)).isoformat()

    def test_priority_shipping_uses_two_days(self, db_session):
        service = OrderService(db_session)
        shipped_at = datetime.now(timezone.utc)
        order = SimpleNamespace(delivered_at=None, order_status="shipped", shipping_method="Priority 2-Day",
                                 shipped_at=shipped_at, confirmed_at=None, created_at=shipped_at, id=uuid4())
        result = service._calculate_estimated_delivery(order)
        assert result == (shipped_at + timedelta(days=2)).isoformat()

    def test_economy_shipping_uses_seven_days(self, db_session):
        service = OrderService(db_session)
        confirmed_at = datetime.now(timezone.utc)
        order = SimpleNamespace(delivered_at=None, order_status="confirmed", shipping_method="Economy",
                                 shipped_at=None, confirmed_at=confirmed_at, created_at=confirmed_at, id=uuid4())
        result = service._calculate_estimated_delivery(order)
        assert result == (confirmed_at + timedelta(days=9)).isoformat()  # 7 base + 2 processing

    def test_confirmed_only_adds_processing_time(self, db_session):
        service = OrderService(db_session)
        confirmed_at = datetime.now(timezone.utc)
        order = SimpleNamespace(delivered_at=None, order_status="confirmed", shipping_method=None,
                                 shipped_at=None, confirmed_at=confirmed_at, created_at=confirmed_at, id=uuid4())
        result = service._calculate_estimated_delivery(order)
        assert result == (confirmed_at + timedelta(days=7)).isoformat()  # 5 base + 2

    def test_exception_is_caught_and_returns_none(self, db_session):
        service = OrderService(db_session)
        order = SimpleNamespace(delivered_at=None, order_status="pending", shipping_method=None,
                                 shipped_at=None, confirmed_at=None, created_at=None, id=uuid4())
        assert service._calculate_estimated_delivery(order) is None


# --------------------------------------------------------------------------- get_statistics date_to edge cases ---------------------------------------------------------------------------

class TestGetStatisticsEdgeCases:

    async def test_valid_date_to_filters_results(self, db_session, existing_order):
        service = OrderService(db_session)
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        stats = await service.get_statistics(date_to=future)
        assert stats["total_orders"] >= 1

    async def test_invalid_date_to_is_ignored(self, db_session, existing_order):
        service = OrderService(db_session)
        stats = await service.get_statistics(date_to="not-a-date")
        assert "total_orders" in stats
