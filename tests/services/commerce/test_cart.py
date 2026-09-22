"""Tests for services/commerce/cart.py - CartService.

Covers cart creation/retrieval, pricing (subtotal/tax), add/update/remove/
clear item flows with stock checks, promocode apply/remove (including the
minimum-order-amount gate and auto-clearing a promocode that's been
deactivated since it was applied), full cart validation (stock/active/
quantity-limit issues), and saved-for-later items.
"""

import pytest
from types import SimpleNamespace
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from fastapi import HTTPException

from services.commerce.cart import CartService
from services.accounts.auth import AuthService
from services.commerce.tax import TaxService
from services.catalog.inventory import InventoryService
from models.accounts.user import User, UserRole
from models.catalog.product import Product, ProductVariant, ProductStatus, ProductImage
from models.catalog.inventories import Inventory
from models.commerce.promocode import Promocode
from models.commerce.tax_rates import TaxRate
from core.utils.uuid_utils import uuid7


async def make_user(db_session) -> User:
    auth = AuthService(db_session)
    user = User(
        id=uuid4(), email=f"cart_{uuid4().hex[:8]}@example.com", firstname="T", lastname="U",
        hashed_password=auth.get_password_hash("Password123!"), role=UserRole.CUSTOMER,
        account_status="active", verification_status="verified",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def make_product(db_session, status=ProductStatus.ACTIVE, **overrides) -> Product:
    fields = {"id": uuid4(), "name": "Test Product", "slug": f"prod-{uuid4().hex[:8]}", "product_status": status}
    fields.update(overrides)
    product = Product(**fields)
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def make_variant(db_session, product_id, base_price=20.0, sale_price=None, is_active=True, **overrides) -> ProductVariant:
    fields = {
        "id": uuid4(), "product_id": product_id, "sku": f"SKU-{uuid4().hex[:10]}",
        "name": "Variant", "base_price": base_price, "sale_price": sale_price, "is_active": is_active,
    }
    fields.update(overrides)
    variant = ProductVariant(**fields)
    db_session.add(variant)
    await db_session.commit()
    await db_session.refresh(variant)
    return variant


async def make_inventory(db_session, variant_id, quantity_available=100) -> Inventory:
    inv = Inventory(id=uuid4(), variant_id=variant_id, quantity_available=quantity_available)
    db_session.add(inv)
    await db_session.commit()
    await db_session.refresh(inv)
    return inv


async def make_promocode(db_session, code=None, discount_type="percentage", value=10, **overrides) -> Promocode:
    fields = {"id": uuid4(), "code": code or f"CART{uuid4().hex[:8].upper()}", "discount_type": discount_type,
              "value": value, "is_active": True}
    fields.update(overrides)
    promo = Promocode(**fields)
    db_session.add(promo)
    await db_session.commit()
    await db_session.refresh(promo)
    return promo


async def make_stocked_variant(db_session, price=20.0, stock=50, **overrides):
    product = await make_product(db_session)
    variant = await make_variant(db_session, product.id, base_price=price, **overrides)
    await make_inventory(db_session, variant.id, quantity_available=stock)
    # make_variant's refresh above cached variant.inventory = None before this row
    # existed; expire it so a later query actually reloads the relationship.
    db_session.expire(variant, ["inventory"])
    return product, variant


class TestGetOrCreate:

    async def test_creates_a_new_cart(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        cart = await service.get_or_create(user.id)
        assert cart.user_id == user.id

    async def test_returns_the_existing_cart(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        first = await service.get_or_create(user.id)
        second = await service.get_or_create(user.id)
        assert first.id == second.id


class TestGetCart:

    async def test_empty_cart_response_shape(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        result = await service.get_cart(user.id)
        assert result["items"] == []
        assert result["total_amount"] == 0.0

    async def test_no_user_id_raises(self, db_session):
        service = CartService(db_session)
        with pytest.raises(ValueError):
            await service.get_cart(None)

    async def test_cart_with_items_computes_subtotal(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=25.0)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=2)

        result = await service.get_cart(user.id, country_code="ZZ")
        assert result["subtotal"] == pytest.approx(50.0)
        assert result["item_count"] == 1
        assert len(result["items"]) == 1

    async def test_uses_sale_price_when_present(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=25.0, sale_price=15.0)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.get_cart(user.id)
        assert result["items"][0]["unit_price"] == pytest.approx(15.0)

    async def test_auto_clears_deactivated_promocode(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        promo = await make_promocode(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        await service.apply_promo(user.id, promo.code)

        promo.is_active = False
        await db_session.commit()

        result = await service.get_cart(user.id)
        assert result["promocode"] is None


class TestAddToCart:

    async def test_adds_a_new_item(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        service = CartService(db_session)
        result = await service.add_to_cart(user.id, variant.id, quantity=1)
        assert result["item_count"] == 1

    async def test_increments_existing_item_quantity(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=50)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=2)
        result = await service.add_to_cart(user.id, variant.id, quantity=3)
        assert result["items"][0]["quantity"] == 5

    async def test_no_user_id_raises_401(self, db_session):
        product, variant = await make_stocked_variant(db_session)
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.add_to_cart(None, variant.id, quantity=1)
        assert exc_info.value.status_code == 401

    async def test_unknown_variant_raises_404(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.add_to_cart(user.id, uuid4(), quantity=1)
        assert exc_info.value.status_code == 404

    async def test_inactive_variant_raises_400(self, db_session):
        user = await make_user(db_session)
        product = await make_product(db_session)
        variant = await make_variant(db_session, product.id, is_active=False)
        await make_inventory(db_session, variant.id, quantity_available=10)
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.add_to_cart(user.id, variant.id, quantity=1)
        assert exc_info.value.status_code == 400

    async def test_quantity_beyond_stock_is_capped_not_rejected(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=1)
        service = CartService(db_session)
        result = await service.add_to_cart(user.id, variant.id, quantity=5)
        assert result["items"][0]["quantity"] == 1

    async def test_out_of_stock_item_is_added_with_zero_quantity(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=0)
        service = CartService(db_session)
        result = await service.add_to_cart(user.id, variant.id, quantity=1)
        assert result["items"][0]["quantity"] == 0

    async def test_incrementing_beyond_stock_is_capped_not_rejected(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=3)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=2)
        result = await service.add_to_cart(user.id, variant.id, quantity=2)
        assert result["items"][0]["quantity"] == 3


class TestUpdateItem:

    async def test_updates_quantity(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=50)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        item_id = cart.items[0].id

        result = await service.update_item(user.id, item_id, quantity=4)
        assert result["items"][0]["quantity"] == 4

    async def test_unknown_item_raises_404(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_item(user.id, uuid4(), quantity=1)
        assert exc_info.value.status_code == 404

    async def test_missing_variant_raises_404(self, db_session):
        """Defensive check against an orphaned variant reference (not reachable through
        normal use given the NOT NULL FK on CartItem.variant_id), simulated by clearing
        the relationship in-memory on the identity-mapped item."""
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=50)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        item_id = cart.items[0].id
        cart.items[0].variant = None

        with pytest.raises(HTTPException) as exc_info:
            await service.update_item(user.id, item_id, quantity=2)
        assert exc_info.value.status_code == 404

    async def test_insufficient_stock_raises_400(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=2)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        item_id = cart.items[0].id

        with pytest.raises(HTTPException) as exc_info:
            await service.update_item(user.id, item_id, quantity=10)
        assert exc_info.value.status_code == 400


class TestRemoveItem:

    async def test_removes_the_item(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        item_id = cart.items[0].id

        result = await service.remove_item(user.id, item_id)
        assert result["items"] == []

    async def test_unknown_item_raises_404(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.remove_item(user.id, uuid4())
        assert exc_info.value.status_code == 404


class TestClearCart:

    async def test_removes_all_items_and_promocode(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        promo = await make_promocode(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        await service.apply_promo(user.id, promo.code)

        result = await service.clear_cart(user.id)
        assert result["items"] == []
        # An emptied cart takes the _create_empty_cart_response() shape, which
        # has no "promocode" key at all (rather than an explicit None).
        assert result.get("promocode") is None


class TestItemCount:

    async def test_sums_quantities(self, db_session):
        user = await make_user(db_session)
        _, v1 = await make_stocked_variant(db_session)
        _, v2 = await make_stocked_variant(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, v1.id, quantity=2)
        await service.add_to_cart(user.id, v2.id, quantity=3)

        assert await service.item_count(user.id) == 5

    async def test_no_user_id_returns_zero(self, db_session):
        service = CartService(db_session)
        assert await service.item_count(None) == 0


class TestApplyPromo:

    async def test_applies_a_valid_code(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=100.0)
        promo = await make_promocode(db_session, value=10)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.apply_promo(user.id, promo.code)
        assert result["promocode_applied"] is True
        assert result["discount_amount"] == pytest.approx(10.0)

    async def test_missing_code_raises_400(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.apply_promo(user.id, None)
        assert exc_info.value.status_code == 400

    async def test_empty_cart_raises_400(self, db_session):
        user = await make_user(db_session)
        promo = await make_promocode(db_session)
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.apply_promo(user.id, promo.code)
        assert exc_info.value.status_code == 400

    async def test_invalid_code_raises_400(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        with pytest.raises(HTTPException) as exc_info:
            await service.apply_promo(user.id, f"NOPE{uuid4().hex[:8]}")
        assert exc_info.value.status_code == 400

    async def test_below_minimum_order_amount_raises_400(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=10.0)
        promo = await make_promocode(db_session, minimum_order_amount=100)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        with pytest.raises(HTTPException) as exc_info:
            await service.apply_promo(user.id, promo.code)
        assert exc_info.value.status_code == 400


class TestRemovePromo:

    async def test_clears_the_promocode(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        promo = await make_promocode(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        await service.apply_promo(user.id, promo.code)

        result = await service.remove_promo(user.id)
        assert result["promocode_removed"] is True
        assert result["promocode"] is None


class TestValidateCart:

    async def test_empty_cart_is_invalid(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        result = await service.validate_cart(user.id)
        assert result["valid"] is False
        assert result["can_checkout"] is False

    async def test_valid_cart_can_checkout(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=50.0, stock=10)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.validate_cart(user.id)
        assert result["can_checkout"] is True
        assert result["summary"]["valid_items"] == 1

    async def test_inactive_variant_is_flagged(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=10)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        variant.is_active = False
        await db_session.commit()

        result = await service.validate_cart(user.id)
        assert any(i["type"] == "inactive_variant" for i in result["issues"])
        assert result["can_checkout"] is False

    async def test_insufficient_stock_is_flagged(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=5)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=2)

        inventory_result = await db_session.execute(
            select(Inventory).where(Inventory.variant_id == variant.id)
        )
        inv = inventory_result.scalar_one()
        inv.quantity_available = 0
        await db_session.commit()

        result = await service.validate_cart(user.id)
        assert any(i["type"] == "insufficient_stock" for i in result["issues"])

    async def test_below_minimum_order_value_cannot_checkout(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=0.50, stock=10)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.validate_cart(user.id)
        assert any(i["type"] == "minimum_order_value" for i in result["issues"])
        assert result["can_checkout"] is False


class TestShippingOptions:

    async def test_returns_default_options_when_none_in_db(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        result = await service.shipping_options(user.id)
        assert len(result["shipping_options"]) >= 1

    async def test_returns_db_methods_when_present(self, db_session):
        from models.commerce.shipping import ShippingMethod
        method = ShippingMethod(id=uuid4(), name="Rocket", price=99.0, estimated_days=1, is_active=True)
        db_session.add(method)
        await db_session.commit()

        user = await make_user(db_session)
        service = CartService(db_session)
        result = await service.shipping_options(user.id)
        assert any(o["name"] == "Rocket" for o in result["shipping_options"])


class TestCalcTotals:

    async def test_adds_shipping_cost_from_selected_method(self, db_session):
        from models.commerce.shipping import ShippingMethod
        method = ShippingMethod(id=uuid4(), name="Standard", price=7.5, estimated_days=3, is_active=True)
        db_session.add(method)
        await db_session.commit()

        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=20.0)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.calc_totals(user.id, data={"shipping_method_id": str(method.id)})
        assert result["shipping_amount"] == pytest.approx(7.5)
        assert result["total_amount"] == pytest.approx(27.5)


class TestCheckoutSummary:

    async def test_can_checkout_true_when_cart_has_value(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=20.0)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.checkout_summary(user.id)
        assert result["can_checkout"] is True
        assert result["checkout_url"] == "/checkout"

    async def test_can_checkout_false_for_empty_cart(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        result = await service.checkout_summary(user.id)
        assert result["can_checkout"] is False


class TestSavedItems:

    async def test_save_later_and_move_back(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        item_id = cart.items[0].id

        await service.save_later(user.id, item_id)
        saved = await service.saved_items(user.id)
        assert saved["count"] == 1

        await service.move_to_cart(user.id, item_id)
        saved_after = await service.saved_items(user.id)
        assert saved_after["count"] == 0

    async def test_save_later_unknown_item_raises_404(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.save_later(user.id, uuid4())
        assert exc_info.value.status_code == 404

    async def test_save_later_db_failure_raises_500(self, db_session, mocker):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        item_id = cart.items[0].id

        mocker.patch.object(db_session, "commit", side_effect=RuntimeError("db down"))
        with pytest.raises(HTTPException) as exc_info:
            await service.save_later(user.id, item_id)
        assert exc_info.value.status_code == 500

    async def test_move_to_cart_unknown_item_raises_404(self, db_session):
        user = await make_user(db_session)
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.move_to_cart(user.id, uuid4())
        assert exc_info.value.status_code == 404

    async def test_move_to_cart_db_failure_raises_500(self, db_session, mocker):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        item_id = cart.items[0].id
        await service.save_later(user.id, item_id)

        mocker.patch.object(db_session, "commit", side_effect=RuntimeError("db down"))
        with pytest.raises(HTTPException) as exc_info:
            await service.move_to_cart(user.id, item_id)
        assert exc_info.value.status_code == 500

    async def test_saved_items_failure_raises_500(self, db_session, mocker):
        mocker.patch.object(CartService, "get_or_create", side_effect=RuntimeError("db down"))
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.saved_items(uuid4())
        assert exc_info.value.status_code == 500


class TestUnauthenticatedGuards:
    """`update_item`, `remove_item`, and `clear_cart` must reject a missing user_id
    with 401 rather than a raw 500 from failing to query the DB with a null id."""

    async def test_update_item_requires_auth(self, db_session):
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_item(None, uuid4(), quantity=1)
        assert exc_info.value.status_code == 401

    async def test_remove_item_requires_auth(self, db_session):
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.remove_item(None, uuid4())
        assert exc_info.value.status_code == 401

    async def test_clear_cart_requires_auth(self, db_session):
        service = CartService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.clear_cart(None)
        assert exc_info.value.status_code == 401


class TestShippingOptionsEdgeCases:

    async def test_db_failure_falls_back_to_default_options(self, db_session, mocker):
        user = await make_user(db_session)
        mocker.patch.object(db_session, "execute", side_effect=RuntimeError("db down"))
        service = CartService(db_session)
        result = await service.shipping_options(user.id)
        assert len(result["shipping_options"]) >= 1
        assert result["shipping_options"][0]["id"] == "standard"


class TestValidateCartItemEdgeCases:
    """Direct unit tests of `_validate_cart_item`, targeting branches not reachable
    (or not reachable cleanly) through a full `validate_cart` call."""

    async def test_inactive_product_is_flagged_even_when_variant_is_active(self, db_session):
        user = await make_user(db_session)
        product = await make_product(db_session, status=ProductStatus.DRAFT)
        variant = await make_variant(db_session, product.id, is_active=True)
        await make_inventory(db_session, variant.id, quantity_available=10)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.validate_cart(user.id)
        assert any(i["type"] == "inactive_product" for i in result["issues"])

    async def test_stock_check_failure_does_not_block_validation(self, db_session, mocker):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=10)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        mocker.patch.object(InventoryService, "check_stock", side_effect=RuntimeError("inventory service down"))
        result = await service.validate_cart(user.id)
        assert not any(i["type"] == "insufficient_stock" for i in result["issues"])

    async def test_zero_quantity_item_is_flagged_invalid(self, db_session):
        service = CartService(db_session)
        fake_variant = SimpleNamespace(id=uuid4(), is_active=True, name="Widget")
        fake_item = SimpleNamespace(
            id=uuid4(), variant=fake_variant, variant_id=fake_variant.id,
            product=None, product_id=uuid4(), quantity=0,
        )
        issues = await service._validate_cart_item(fake_item)
        assert any(i["type"] == "invalid_quantity" for i in issues)

    async def test_quantity_over_100_is_flagged_as_warning(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, stock=200)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        cart.items[0].quantity = 150
        await db_session.commit()

        result = await service.validate_cart(user.id)
        warning = next((i for i in result["issues"] if i["type"] == "quantity_limit_exceeded"), None)
        assert warning is not None
        assert warning["severity"] == "warning"

    async def test_unexpected_error_is_caught_as_validation_error(self, db_session):
        class ExplodingVariant:
            @property
            def is_active(self):
                raise RuntimeError("boom")

        service = CartService(db_session)
        fake_item = SimpleNamespace(id=uuid4(), variant=ExplodingVariant(), variant_id=uuid4())
        issues = await service._validate_cart_item(fake_item)
        assert any(i["type"] == "validation_error" for i in issues)


class TestCalculateCartPricingEdgeCases:
    """Direct unit tests of `_calculate_cart_pricing` for branches that are
    impractical to reach through a full cart (an item with no resolvable variant,
    malformed quantity data, and tax-lookup success/failure)."""

    async def test_skips_item_with_missing_variant(self, db_session):
        service = CartService(db_session)
        fake_item = SimpleNamespace(id=uuid4(), variant=None, variant_id=uuid4(), quantity=1)
        result = await service._calculate_cart_pricing([fake_item], "US", None)
        assert result["subtotal"] == 0.0

    async def test_malformed_quantity_is_caught_and_skipped(self, db_session):
        service = CartService(db_session)
        fake_variant = SimpleNamespace(sale_price=None, base_price=Decimal("10.00"))
        fake_item = SimpleNamespace(id=uuid4(), variant=fake_variant, variant_id=uuid4(), quantity=None)
        result = await service._calculate_cart_pricing([fake_item], "US", None)
        assert result["subtotal"] == 0.0

    async def test_tax_is_calculated_when_a_matching_rate_exists(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=100.0)
        db_session.add(TaxRate(id=uuid7(), country_code="ZZ", country_name="Test Country",
                                tax_rate=Decimal("0.10"), is_active=True))
        await db_session.flush()
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.get_cart(user.id, country_code="ZZ")
        assert result["tax_amount"] == pytest.approx(10.0)

    async def test_tax_lookup_failure_is_swallowed(self, db_session, mocker):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session, price=100.0)
        mocker.patch.object(TaxService, "rate", side_effect=RuntimeError("tax service down"))
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.get_cart(user.id, country_code="US")
        assert result["tax_amount"] == 0.0


class TestGetCartEdgeCases:

    async def test_item_with_images_includes_image_list(self, db_session):
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        db_session.add(ProductImage(id=uuid7(), variant_id=variant.id, url="https://example.com/a.jpg", is_primary=True))
        await db_session.commit()
        # variant.images was already cached as [] (lazy="selectin" populates eagerly on load) by the time this fixture's variant object was first created, before the image row above existed - expire it so a later query reloads the relationship.
        db_session.expire(variant, ["images"])
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)

        result = await service.get_cart(user.id)
        assert len(result["items"][0]["variant"]["images"]) == 1
        assert result["items"][0]["variant"]["images"][0]["url"] == "https://example.com/a.jpg"

    async def test_item_with_missing_variant_is_skipped(self, db_session):
        """Defensive check against an orphaned variant reference (not reachable through
        normal use given the NOT NULL FK on CartItem.variant_id, but guarded regardless).
        Simulated by clearing the relationship in-memory on the identity-mapped item."""
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        cart.items[0].variant = None

        result = await service.get_cart(user.id)
        assert result["items"] == []

    async def test_item_with_missing_product_is_skipped(self, db_session):
        """Same defensive check, for an orphaned product reference."""
        user = await make_user(db_session)
        product, variant = await make_stocked_variant(db_session)
        service = CartService(db_session)
        await service.add_to_cart(user.id, variant.id, quantity=1)
        cart = await service.get_or_create(user.id)
        cart.items[0].product = None

        result = await service.get_cart(user.id)
        assert result["items"] == []

    async def test_reloaded_cart_with_no_items_returns_empty_response(self, db_session, mocker):
        """Defensive re-check: get_or_create() reports a non-empty cart, but the
        follow-up eager-loaded re-query (used to build response detail) legitimately
        finds no items - covers get_cart()'s second empty-cart guard."""
        user = await make_user(db_session)
        real_cart = await CartService(db_session).get_or_create(user.id)  # genuinely empty in DB
        fake_populated_cart = SimpleNamespace(id=real_cart.id, items=[SimpleNamespace()])
        mocker.patch.object(CartService, "get_or_create", return_value=fake_populated_cart)

        service = CartService(db_session)
        result = await service.get_cart(user.id)
        assert result["items"] == []
