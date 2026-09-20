"""Tests for api/commerce/cart.py - /v1/cart endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.fixture
async def created_variant(async_client: AsyncClient, admin_headers, sample_product_data):
    cat = await async_client.post("/v1/categories/",
        headers=admin_headers, json={"name": "Cat", "slug": f"cat-{uuid4().hex[:8]}"}
    )
    sample_product_data["category_id"] = cat.json()["data"]["id"]
    product = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    variants = await async_client.get(f"/v1/products/{product.json()['data']['id']}/variants/")
    return variants.json()["data"][0]


@pytest.fixture
async def cart_with_item(async_client: AsyncClient, auth_headers, created_variant):
    await async_client.post("/v1/cart/add/", headers=auth_headers, json={
        "variant_id": created_variant["id"], "quantity": 2
    })
    return created_variant


@pytest.mark.api
class TestCartEndpoints:

    async def test_get_empty(self, async_client: AsyncClient, auth_headers):
        """GET /v1/cart/ - A new user has an empty cart."""
        response = await async_client.get("/v1/cart/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["items"] == []

    async def test_get_unauthorized(self, async_client: AsyncClient):
        """GET /v1/cart/ - No auth is rejected."""
        response = await async_client.get("/v1/cart/")
        assert response.status_code == 401

    async def test_add_item(self, async_client: AsyncClient, auth_headers, created_variant):
        """POST /v1/cart/add - Add item to cart."""
        response = await async_client.post("/v1/cart/add/", headers=auth_headers, json={
            "variant_id": created_variant["id"], "quantity": 2
        })
        assert response.status_code == 200
        assert response.json()["data"]["items"][0]["quantity"] == 2

    async def test_add_item_unknown_variant(self, async_client: AsyncClient, auth_headers):
        """POST /v1/cart/add - Unknown variant is rejected."""
        response = await async_client.post("/v1/cart/add/", headers=auth_headers, json={
            "variant_id": str(uuid4()), "quantity": 1
        })
        assert response.status_code == 404

    async def test_add_item_zero_quantity_rejected(self, async_client: AsyncClient, auth_headers, created_variant):
        """POST /v1/cart/add - Quantity must be at least 1."""
        response = await async_client.post("/v1/cart/add/", headers=auth_headers, json={
            "variant_id": created_variant["id"], "quantity": 0
        })
        assert response.status_code == 422

    async def test_update_item(self, async_client: AsyncClient, auth_headers, cart_with_item):
        """PATCH /v1/cart/{item_id} - Update cart item quantity."""
        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        item_id = cart.json()["data"]["items"][0]["id"]

        response = await async_client.patch(f"/v1/cart/{item_id}/", headers=auth_headers, json={"quantity": 5})
        assert response.status_code == 200
        assert response.json()["data"]["items"][0]["quantity"] == 5

    async def test_update_item_alias(self, async_client: AsyncClient, auth_headers, cart_with_item):
        """PATCH /v1/cart/items/{item_id} - Compatibility alias."""
        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        item_id = cart.json()["data"]["items"][0]["id"]

        response = await async_client.patch(f"/v1/cart/items/{item_id}/", headers=auth_headers, json={"quantity": 3})
        assert response.status_code == 200
        assert response.json()["data"]["items"][0]["quantity"] == 3

    async def test_update_item_not_found(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/cart/{item_id} - Unknown item ID."""
        response = await async_client.patch(f"/v1/cart/{uuid4()}/", headers=auth_headers, json={"quantity": 1})
        assert response.status_code == 404

    async def test_remove_item(self, async_client: AsyncClient, auth_headers, cart_with_item):
        """DELETE /v1/cart/{item_id} - Remove cart item."""
        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        item_id = cart.json()["data"]["items"][0]["id"]

        response = await async_client.delete(f"/v1/cart/{item_id}/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["items"] == []

    async def test_remove_item_alias(self, async_client: AsyncClient, auth_headers, cart_with_item):
        """DELETE /v1/cart/items/{item_id} - Compatibility alias."""
        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        item_id = cart.json()["data"]["items"][0]["id"]

        response = await async_client.delete(f"/v1/cart/items/{item_id}/", headers=auth_headers)
        assert response.status_code == 200

    async def test_count(self, async_client: AsyncClient, auth_headers, cart_with_item):
        """GET /v1/cart/count - Item count."""
        response = await async_client.get("/v1/cart/count/", headers=auth_headers)
        assert response.status_code == 200

    async def test_validate(self, async_client: AsyncClient, auth_headers, cart_with_item):
        """POST /v1/cart/validate - Validate cart before checkout."""
        response = await async_client.post("/v1/cart/validate/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["valid"] is True

    async def test_calculate(self, async_client: AsyncClient, auth_headers, cart_with_item):
        """POST /v1/cart/calculate - Calculate cart totals."""
        response = await async_client.post("/v1/cart/calculate/", headers=auth_headers, json={})
        assert response.status_code == 200

    async def test_clear(self, async_client: AsyncClient, auth_headers, cart_with_item):
        """POST /v1/cart/clear - Clear cart."""
        response = await async_client.post("/v1/cart/clear/", headers=auth_headers)
        assert response.status_code == 200

        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        assert cart.json()["data"]["items"] == []

    async def test_checkout_summary(self, async_client: AsyncClient, auth_headers, cart_with_item):
        """GET /v1/cart/checkout-summary - Get checkout summary."""
        response = await async_client.get("/v1/cart/checkout-summary/", headers=auth_headers)
        assert response.status_code == 200
