"""Tests for models/commerce/cart.py - Cart.subtotal/discount_amount and CartItem validation.

These are plain in-memory model instances (never added to a session), so the
math can be exercised without a database.
"""

import pytest
from decimal import Decimal

from models.commerce.cart import Cart, CartItem
from models.commerce.promocode import Promocode


def make_item(quantity: int, price_per_unit: str) -> CartItem:
    return CartItem(quantity=quantity, price_per_unit=Decimal(price_per_unit))


def make_cart(items) -> Cart:
    cart = Cart()
    cart.items = list(items)
    return cart


class TestCartSubtotalAndItemCount:

    def test_subtotal_sums_item_totals(self):
        cart = make_cart([make_item(2, "10.00"), make_item(1, "5.00")])
        assert cart.subtotal == Decimal("25.00")

    def test_empty_cart_subtotal_is_zero(self):
        assert make_cart([]).subtotal == 0

    def test_total_items_sums_quantities_not_line_count(self):
        cart = make_cart([make_item(2, "10.00"), make_item(3, "5.00")])
        assert cart.total_items == 5


class TestCartItemValidation:

    def test_positive_quantity_is_accepted(self):
        assert make_item(1, "1.00").quantity == 1

    def test_zero_quantity_is_accepted(self):
        # An out-of-stock cart item is capped to 0 by CartService, not rejected.
        assert make_item(0, "1.00").quantity == 0

    def test_negative_quantity_is_rejected(self):
        with pytest.raises(ValueError):
            make_item(-1, "1.00")

    def test_non_integer_quantity_is_rejected(self):
        with pytest.raises(ValueError):
            CartItem(quantity=1.5, price_per_unit=Decimal("1.00"))

    def test_total_price_multiplies_price_by_quantity(self):
        item = make_item(3, "4.50")
        assert item.total_price == Decimal("13.50")


def make_promocode(discount_type: str, value: str, is_active=True, maximum_discount_amount=None) -> Promocode:
    promo = Promocode()
    promo.discount_type = discount_type
    promo.value = Decimal(value)
    promo.is_active = is_active
    promo.maximum_discount_amount = Decimal(maximum_discount_amount) if maximum_discount_amount else None
    return promo


class TestCartDiscountAmount:
    """Cart.discount_amount backs both the /cart/ response and checkout pricing -
    a bug here silently over- or under-charges every order that uses a promocode."""

    def test_no_promocode_means_no_discount(self):
        cart = make_cart([make_item(1, "100.00")])
        assert cart.discount_amount == Decimal("0")

    def test_inactive_promocode_is_ignored(self):
        cart = make_cart([make_item(1, "100.00")])
        cart.promocode = make_promocode("percentage", "10", is_active=False)
        assert cart.discount_amount == Decimal("0")

    def test_percentage_discount(self):
        cart = make_cart([make_item(1, "100.00")])
        cart.promocode = make_promocode("percentage", "10")
        assert cart.discount_amount == Decimal("10.00")

    def test_fixed_discount(self):
        cart = make_cart([make_item(1, "100.00")])
        cart.promocode = make_promocode("fixed", "15")
        assert cart.discount_amount == Decimal("15")

    def test_percentage_discount_is_capped_by_maximum(self):
        cart = make_cart([make_item(1, "1000.00")])
        cart.promocode = make_promocode("percentage", "50", maximum_discount_amount="20")
        assert cart.discount_amount == Decimal("20")

    def test_discount_never_exceeds_subtotal(self):
        """A fixed discount larger than the cart must not produce a negative total."""
        cart = make_cart([make_item(1, "10.00")])
        cart.promocode = make_promocode("fixed", "50")
        assert cart.discount_amount == Decimal("10.00")

    def test_discount_amount_uses_current_subtotal_not_a_stored_value(self):
        """Discount is computed live from the cart's items, so it always reflects
        whatever is in the cart right now rather than a snapshot from apply-time."""
        cart = make_cart([make_item(1, "100.00")])
        cart.promocode = make_promocode("percentage", "10")
        assert cart.discount_amount == Decimal("10.00")

        cart.items.append(make_item(1, "100.00"))
        assert cart.discount_amount == Decimal("20.00")
