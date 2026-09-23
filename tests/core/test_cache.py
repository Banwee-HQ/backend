"""Tests for core/utils/cache.py - in-process TTL cache for read-only display data."""

from core.utils.cache import product_read_cache, invalidate_variant, invalidate_product, invalidate_all


class TestInvalidateVariant:

    def setup_method(self):
        product_read_cache.clear()

    def test_drops_the_variant_entry(self):
        product_read_cache[("variant", "v1")] = "cached"
        invalidate_variant("v1")
        assert ("variant", "v1") not in product_read_cache

    def test_also_drops_the_parent_products_entries_when_given(self):
        product_read_cache[("variant", "v1")] = "cached"
        product_read_cache[("variants", "p1")] = "cached"
        product_read_cache[("product", "p1")] = "cached"
        invalidate_variant("v1", "p1")
        assert ("variant", "v1") not in product_read_cache
        assert ("variants", "p1") not in product_read_cache
        assert ("product", "p1") not in product_read_cache

    def test_missing_key_is_a_noop(self):
        invalidate_variant("unknown")  # must not raise


class TestInvalidateProduct:

    def setup_method(self):
        product_read_cache.clear()

    def test_drops_product_and_variants_list_entries(self):
        product_read_cache[("product", "p1")] = "cached"
        product_read_cache[("variants", "p1")] = "cached"
        invalidate_product("p1")
        assert ("product", "p1") not in product_read_cache
        assert ("variants", "p1") not in product_read_cache

    def test_also_drops_the_slug_entry_when_given(self):
        product_read_cache[("product", "my-slug")] = "cached"
        invalidate_product("p1", "my-slug")
        assert ("product", "my-slug") not in product_read_cache

    def test_leaves_unrelated_entries_alone(self):
        product_read_cache[("variant", "v1")] = "cached"
        invalidate_product("p1")
        assert ("variant", "v1") in product_read_cache


class TestInvalidateAll:

    def setup_method(self):
        product_read_cache.clear()

    def test_clears_every_entry(self):
        product_read_cache[("product", "p1")] = "cached"
        product_read_cache[("variant", "v1")] = "cached"
        invalidate_all()
        assert len(product_read_cache) == 0
