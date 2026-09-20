"""Tests for models/catalog/product.py - Product/ProductVariant computed properties.

These drive what a shopper sees as price range, in-stock, and low-stock badges,
so getting the "any variant available" vs "all variants" logic wrong is a real
storefront bug, not just cosmetic.
"""

from models.catalog.product import Product, ProductVariant, ProductStatus, AvailabilityStatus
from models.catalog.inventories import Inventory


def make_variant(base_price, sale_price=None, is_active=True, quantity_available=None, low_stock_threshold=10) -> ProductVariant:
    variant = ProductVariant()
    variant.base_price = base_price
    variant.sale_price = sale_price
    variant.is_active = is_active
    variant.images = []
    if quantity_available is not None:
        inv = Inventory()
        inv.quantity_available = quantity_available
        inv.low_stock_threshold = low_stock_threshold
        variant.inventory = inv
    else:
        variant.inventory = None
    return variant


def make_product(variants=None, product_status=ProductStatus.ACTIVE) -> Product:
    product = Product()
    product.variants = variants or []
    product.product_status = product_status
    return product


class TestProductIsActive:

    def test_active_status_is_active(self):
        assert make_product(product_status=ProductStatus.ACTIVE).is_active is True

    def test_draft_status_is_not_active(self):
        assert make_product(product_status=ProductStatus.DRAFT).is_active is False

    def test_discontinued_status_is_not_active(self):
        assert make_product(product_status=ProductStatus.DISCONTINUED).is_active is False


class TestPrimaryVariant:

    def test_no_variants_means_no_primary(self):
        assert make_product([]).primary_variant is None

    def test_picks_the_cheapest_variant(self):
        cheap = make_variant(base_price=10)
        expensive = make_variant(base_price=50)
        product = make_product([expensive, cheap])
        assert product.primary_variant is cheap


class TestPriceRange:

    def test_no_variants_gives_zero_range(self):
        assert make_product([]).price_range == {"min": 0, "max": 0}

    def test_inactive_variants_are_excluded_from_range(self):
        active = make_variant(base_price=20, is_active=True)
        inactive = make_variant(base_price=5, is_active=False)
        product = make_product([active, inactive])
        assert product.price_range == {"min": 20, "max": 20}

    def test_only_inactive_variants_gives_zero_range(self):
        product = make_product([make_variant(base_price=20, is_active=False)])
        assert product.price_range == {"min": 0, "max": 0}

    def test_range_spans_min_and_max_of_active_variants(self):
        product = make_product([make_variant(base_price=10), make_variant(base_price=30), make_variant(base_price=20)])
        assert product.price_range == {"min": 10, "max": 30}

    def test_sale_price_is_used_over_base_price(self):
        product = make_product([make_variant(base_price=100, sale_price=60)])
        assert product.price_range == {"min": 60, "max": 60}


class TestInStock:

    def test_no_variants_means_out_of_stock(self):
        assert make_product([]).in_stock is False

    def test_true_if_any_active_variant_has_stock(self):
        out_of_stock = make_variant(base_price=10, quantity_available=0)
        in_stock = make_variant(base_price=10, quantity_available=5)
        product = make_product([out_of_stock, in_stock])
        assert product.in_stock is True

    def test_false_if_only_inactive_variant_has_stock(self):
        """An inactive variant with stock shouldn't make the product look purchasable."""
        inactive_with_stock = make_variant(base_price=10, quantity_available=5, is_active=False)
        product = make_product([inactive_with_stock])
        assert product.in_stock is False

    def test_false_when_variant_has_no_inventory_row_at_all(self):
        product = make_product([make_variant(base_price=10)])  # no inventory attached
        assert product.in_stock is False


class TestAvailabilityStatus:

    def test_no_variants_is_out_of_stock(self):
        assert make_product([]).availability_status == "out_of_stock"

    def test_all_variants_inactive_is_out_of_stock(self):
        product = make_product([make_variant(base_price=10, is_active=False, quantity_available=5)])
        assert product.availability_status == "out_of_stock"

    def test_zero_stock_is_out_of_stock(self):
        product = make_product([make_variant(base_price=10, quantity_available=0)])
        assert product.availability_status == "out_of_stock"

    def test_stock_above_threshold_is_available(self):
        product = make_product([make_variant(base_price=10, quantity_available=50, low_stock_threshold=10)])
        assert product.availability_status == "available"

    def test_stock_at_or_below_threshold_is_limited(self):
        product = make_product([make_variant(base_price=10, quantity_available=5, low_stock_threshold=10)])
        assert product.availability_status == "limited"

    def test_one_low_stock_variant_among_healthy_ones_still_reports_limited(self):
        healthy = make_variant(base_price=10, quantity_available=50, low_stock_threshold=10)
        low = make_variant(base_price=15, quantity_available=2, low_stock_threshold=10)
        product = make_product([healthy, low])
        assert product.availability_status == "limited"


class TestVariantCurrentPriceAndDiscount:

    def test_current_price_is_base_price_without_sale(self):
        variant = make_variant(base_price=100)
        assert variant.current_price == 100

    def test_current_price_is_sale_price_when_set(self):
        variant = make_variant(base_price=100, sale_price=75)
        assert variant.current_price == 75

    def test_discount_percentage_is_zero_without_a_sale(self):
        assert make_variant(base_price=100).discount_percentage == 0

    def test_discount_percentage_is_zero_if_sale_price_not_lower(self):
        assert make_variant(base_price=100, sale_price=100).discount_percentage == 0

    def test_discount_percentage_computed_correctly(self):
        variant = make_variant(base_price=100, sale_price=75)
        assert variant.discount_percentage == 25.0

    def test_stock_reads_through_to_inventory(self):
        assert make_variant(base_price=10, quantity_available=42).stock == 42

    def test_stock_is_zero_without_inventory(self):
        assert make_variant(base_price=10).stock == 0
