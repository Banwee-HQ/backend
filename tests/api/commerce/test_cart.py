"""Tests for api/commerce/cart.py - /v1/cart endpoints."""

import pytest
from httpx import AsyncClient
from fastapi import HTTPException
from uuid import uuid4

from api.commerce.cart import validate as validate_route
from core.exceptions import APIException


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

    async def test_remove_item_not_found(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/cart/{item_id} - Unknown item ID returns 404."""
        response = await async_client.delete(f"/v1/cart/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_cannot_update_another_users_cart_item(self, async_client: AsyncClient, auth_headers, admin_headers, cart_with_item):
        """PATCH /v1/cart/{item_id} - Another user's cart item isn't accessible."""
        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        item_id = cart.json()["data"]["items"][0]["id"]

        response = await async_client.patch(f"/v1/cart/{item_id}/", headers=admin_headers, json={"quantity": 1})
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

    async def test_count_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.get("/v1/cart/count/")
        assert response.status_code == 401

    async def test_validate_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.post("/v1/cart/validate/")
        assert response.status_code == 401

    async def test_clear_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.post("/v1/cart/clear/")
        assert response.status_code == 401

    async def test_checkout_summary_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.get("/v1/cart/checkout-summary/")
        assert response.status_code == 401


@pytest.mark.api
class TestCreateItemEdgeCases:

    async def test_unexpected_service_error_returns_400(self, async_client: AsyncClient, auth_headers, created_variant, mocker):
        mocker.patch("services.commerce.cart.CartService.add_to_cart", side_effect=RuntimeError("db down"))
        response = await async_client.post("/v1/cart/add/", headers=auth_headers, json={
            "variant_id": created_variant["id"], "quantity": 1
        })
        assert response.status_code == 400
        assert "Failed to add item to cart" in response.json()["message"]


@pytest.mark.api
class TestGetCartEdgeCases:

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.get_cart", side_effect=HTTPException(status_code=403, detail="nope"))
        response = await async_client.get("/v1/cart/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_service_error_returns_500(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.get_cart", side_effect=RuntimeError("db down"))
        response = await async_client.get("/v1/cart/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestPatchItemEdgeCases:

    async def test_unexpected_service_error_returns_400(self, async_client: AsyncClient, auth_headers, cart_with_item, mocker):
        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        item_id = cart.json()["data"]["items"][0]["id"]
        mocker.patch("services.commerce.cart.CartService.update_item", side_effect=RuntimeError("db down"))
        response = await async_client.patch(f"/v1/cart/{item_id}/", headers=auth_headers, json={"quantity": 1})
        assert response.status_code == 400


@pytest.mark.api
class TestDeleteItemEdgeCases:

    async def test_unexpected_service_error_returns_400(self, async_client: AsyncClient, auth_headers, cart_with_item, mocker):
        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        item_id = cart.json()["data"]["items"][0]["id"]
        mocker.patch("services.commerce.cart.CartService.remove_item", side_effect=RuntimeError("db down"))
        response = await async_client.delete(f"/v1/cart/{item_id}/", headers=auth_headers)
        assert response.status_code == 400


@pytest.mark.api
class TestCountEdgeCases:

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.item_count", side_effect=HTTPException(status_code=403, detail="nope"))
        response = await async_client.get("/v1/cart/count/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_service_error_returns_500(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.item_count", side_effect=RuntimeError("db down"))
        response = await async_client.get("/v1/cart/count/", headers=auth_headers)
        assert response.status_code == 500


@pytest.mark.api
class TestValidateEdgeCases:

    async def test_missing_current_user_raises_401_defensively(self, db_session):
        """This guard is unreachable via HTTP (require_auth already rejects an
        unauthenticated request before the route body runs), but is exercised
        directly to confirm it still does the right thing on its own."""
        with pytest.raises(APIException) as exc_info:
            await validate_route(request=None, country=None, province=None, current_user=None, db=db_session)
        assert exc_info.value.status_code == 401

    async def test_empty_cart_returns_error_response(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/cart/validate/", headers=auth_headers)
        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert "error(s)" in body["message"]

    async def test_warnings_only_result_still_returns_success(self, async_client: AsyncClient, auth_headers, mocker):
        """Isolated test of the endpoint's own formatting branch for a
        warnings-only (no error-severity issues) validation result."""
        mocker.patch(
            "services.commerce.cart.CartService.validate_cart",
            return_value={"valid": True, "can_checkout": False,
                          "issues": [{"type": "quantity_limit_exceeded", "severity": "warning", "message": "heads up"}],
                          "summary": {}},
        )
        response = await async_client.post("/v1/cart/validate/", headers=auth_headers)
        assert response.status_code == 200
        assert "warning(s)" in response.json()["message"]

    async def test_unexpected_service_error_returns_500(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.validate_cart", side_effect=RuntimeError("db down"))
        response = await async_client.post("/v1/cart/validate/", headers=auth_headers)
        assert response.status_code == 500

    async def test_no_issues_and_not_checkoutable_returns_generic_error(self, async_client: AsyncClient, auth_headers, mocker):
        """Isolated test of the endpoint's final else-branch (can_checkout False and
        valid False, but with no issues to report) - not reachable via CartService's
        real validate_cart, whose can_checkout=False paths always add an issue."""
        mocker.patch(
            "services.commerce.cart.CartService.validate_cart",
            return_value={"valid": False, "can_checkout": False, "issues": [], "summary": {}},
        )
        response = await async_client.post("/v1/cart/validate/", headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["message"] == "Cart validation failed"


@pytest.mark.api
class TestCalculateEdgeCases:

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.calc_totals", side_effect=HTTPException(status_code=403, detail="nope"))
        response = await async_client.post("/v1/cart/calculate/", headers=auth_headers, json={})
        assert response.status_code == 403

    async def test_unexpected_service_error_returns_400(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.calc_totals", side_effect=RuntimeError("db down"))
        response = await async_client.post("/v1/cart/calculate/", headers=auth_headers, json={})
        assert response.status_code == 400


@pytest.mark.api
class TestClearEdgeCases:

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.clear_cart", side_effect=HTTPException(status_code=403, detail="nope"))
        response = await async_client.post("/v1/cart/clear/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_service_error_returns_400(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.clear_cart", side_effect=RuntimeError("db down"))
        response = await async_client.post("/v1/cart/clear/", headers=auth_headers)
        assert response.status_code == 400


@pytest.mark.api
class TestCheckoutSummaryEdgeCases:

    async def test_service_httpexception_passes_through(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.checkout_summary", side_effect=HTTPException(status_code=403, detail="nope"))
        response = await async_client.get("/v1/cart/checkout-summary/", headers=auth_headers)
        assert response.status_code == 403

    async def test_unexpected_service_error_returns_500(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.cart.CartService.checkout_summary", side_effect=RuntimeError("db down"))
        response = await async_client.get("/v1/cart/checkout-summary/", headers=auth_headers)
        assert response.status_code == 500
