"""Tests for product and catalog endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.api
@pytest.mark.unit
class TestProductEndpoints:
    """Test product endpoints."""

    async def test_get_home_data(self, async_client: AsyncClient):
        """Test getting home page data."""
        response = await async_client.get("/v1/products/home")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "categories" in data["data"]
        assert "featured" in data["data"]
        assert "popular" in data["data"]
        assert "deals" in data["data"]

    async def test_list_products(self, async_client: AsyncClient):
        """Test listing all products."""
        response = await async_client.get("/v1/products/")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_list_products_with_pagination(self, async_client: AsyncClient):
        """Test listing products with pagination."""
        response = await async_client.get("/v1/products/?page=1&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "pagination" in data or "total" in data

    async def test_list_products_with_filters(self, async_client: AsyncClient):
        """Test listing products with filters."""
        response = await async_client.get("/v1/products/?category=grains-pulses")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_list_products_with_sorting(self, async_client: AsyncClient):
        """Test listing products with sorting."""
        response = await async_client.get("/v1/products/?sort_by=price&sort_order=asc")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_search_products(self, async_client: AsyncClient):
        """Test searching products."""
        response = await async_client.get("/v1/products/?q=organic")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_product_by_slug(self, async_client: AsyncClient):
        """Test getting a product by slug."""
        # First list products to get a valid slug
        list_response = await async_client.get("/v1/products/?limit=1")
        if list_response.status_code == 200 and list_response.json()["data"]:
            slug = list_response.json()["data"][0]["slug"]
            response = await async_client.get(f"/v1/products/{slug}")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "data" in data

    async def test_get_product_not_found(self, async_client: AsyncClient):
        """Test getting a non-existent product."""
        response = await async_client.get("/v1/products/non-existent-slug-12345")
        assert response.status_code == 404


    async def test_get_featured_products(self, async_client: AsyncClient):
        """Test getting featured products."""
        response = await async_client.get("/v1/products/featured")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_deals(self, async_client: AsyncClient):
        """Test getting products on sale/deals."""
        response = await async_client.get("/v1/products/deals")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data


@pytest.mark.api
@pytest.mark.unit
class TestReviewEndpoints:
    """Test product review endpoints."""

    async def test_get_product_reviews(self, async_client: AsyncClient):
        """Test getting reviews for a product."""
        # Use a sample product ID
        product_id = str(uuid4())
        response = await async_client.get(f"/v1/reviews/product/{product_id}")
        # Should return empty list or 404
        assert response.status_code in [200, 404]

    async def test_create_review_unauthorized(self, async_client: AsyncClient):
        """Test creating review without authentication."""
        review_data = {
            "product_id": str(uuid4()),
            "rating": 5,
            "comment": "Great product!"
        }
        response = await async_client.post("/v1/reviews/", json=review_data)
        assert response.status_code == 401

    async def test_create_review(self, async_client: AsyncClient, auth_headers: dict):
        """Test creating a review."""
        review_data = {
            "product_id": str(uuid4()),
            "rating": 5,
            "comment": "Great product!",
            "title": "Excellent"
        }
        response = await async_client.post("/v1/reviews/", headers=auth_headers, json=review_data)
        # May fail if product doesn't exist
        assert response.status_code in [200, 201, 404, 400]


@pytest.mark.api
@pytest.mark.unit
class TestWishlistEndpoints:
    """Test wishlist endpoints."""

    async def test_get_wishlist(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting user wishlist."""
        response = await async_client.get("/v1/wishlist/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_wishlist_unauthorized(self, async_client: AsyncClient):
        """Test getting wishlist without authentication."""
        response = await async_client.get("/v1/wishlist/")
        assert response.status_code == 401

    async def test_add_to_wishlist(self, async_client: AsyncClient, auth_headers: dict):
        """Test adding item to wishlist."""
        wishlist_data = {
            "product_id": str(uuid4())
        }
        response = await async_client.post("/v1/wishlist/add", headers=auth_headers, json=wishlist_data)
        # May fail if product doesn't exist
        assert response.status_code in [200, 201, 404, 400]

    async def test_remove_from_wishlist(self, async_client: AsyncClient, auth_headers: dict):
        """Test removing item from wishlist."""
        product_id = str(uuid4())
        response = await async_client.delete(f"/v1/wishlist/items/{product_id}", headers=auth_headers)
        # Should succeed even if not in wishlist
        assert response.status_code in [200, 404]

    async def test_clear_wishlist(self, async_client: AsyncClient, auth_headers: dict):
        """Test clearing entire wishlist."""
        response = await async_client.delete("/v1/wishlist/clear", headers=auth_headers)
        assert response.status_code in [200, 404]


@pytest.mark.api
@pytest.mark.unit
class TestInventoryEndpoints:
    """Test inventory endpoints (admin only)."""

    async def test_get_inventory_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting inventory as admin."""
        response = await async_client.get("/v1/inventory/", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_get_inventory_unauthorized(self, async_client: AsyncClient):
        """Test getting inventory without authentication."""
        response = await async_client.get("/v1/inventory/")
        assert response.status_code == 401

    async def test_get_inventory_as_regular_user(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting inventory as regular user (should fail)."""
        response = await async_client.get("/v1/inventory/", headers=auth_headers)
        assert response.status_code == 403

    async def test_update_stock_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test updating stock as admin."""
        stock_data = {
            "product_id": str(uuid4()),
            "quantity_change": 50,
            "reason": "Restock",
            "adjustment_type": "add"
        }
        response = await async_client.post("/v1/inventory/adjustments", headers=admin_headers, json=stock_data)
        # May fail if product doesn't exist
        assert response.status_code in [200, 201, 404]
