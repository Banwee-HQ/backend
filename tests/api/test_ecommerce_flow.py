"""End-to-end test of the core e-commerce journey: search for a product, add it to
the cart, check out, and confirm inventory was actually decremented - all through
the real public API, proving the request/response schemas are compatible end to end
and that checkout genuinely holds inventory rather than just returning a 200.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from models.commerce.payments import PaymentMethod, PaymentType, PaymentProvider, CardBrand
from core.utils.uuid_utils import uuid7


@pytest.mark.api
class TestSearchCartCheckoutFlow:

    async def test_search_add_to_cart_and_checkout_holds_inventory(
        self, async_client: AsyncClient, auth_headers, admin_headers, test_user, db_session: AsyncSession, mocker
    ):
        # --- Merchant lists a product with limited stock ---
        category = await async_client.post(
            "/v1/categories/", headers=admin_headers, json={"name": "Gadgets", "slug": f"gadgets-{uuid4().hex[:8]}"}
        )
        assert category.status_code in (200, 201)
        unique_name = f"Solar Lantern {uuid4().hex[:8]}"
        product = await async_client.post("/v1/products/", headers=admin_headers, json={
            "name": unique_name,
            "slug": f"solar-lantern-{uuid4().hex[:8]}",
            "sku": f"SKU-{uuid4().hex[:8].upper()}",
            "description": "A bright, portable solar lantern.",
            "short_description": "Solar lantern",
            "base_price": 29.99,
            "sale_price": 24.99,
            "cost_price": 15.00,
            "quantity": 3,
            "origin_country": "Nigeria",
            "is_active": True,
            "is_featured": False,
            "weight_kg": 0.5,
            "tags": ["solar", "outdoor"],
            "category_id": category.json()["data"]["id"],
        })
        assert product.status_code in (200, 201), product.text
        product_id = product.json()["data"]["id"]

        # --- Customer searches for it by name ---
        search = await async_client.get("/v1/products/", params={"q": unique_name})
        assert search.status_code == 200
        search_results = search.json()["data"]
        assert any(p["id"] == product_id for p in search_results), search_results

        variants = await async_client.get(f"/v1/products/{product_id}/variants/")
        variant = variants.json()["data"][0]
        variant_id = variant["id"]
        assert variant["stock"] == 3

        # --- Customer adds it to their cart ---
        add_to_cart = await async_client.post(
            "/v1/cart/", headers=auth_headers, json={"variant_id": variant_id, "quantity": 2}
        )
        assert add_to_cart.status_code in (200, 201), add_to_cart.text

        cart = await async_client.get("/v1/cart/", headers=auth_headers)
        assert cart.status_code == 200
        assert cart.json()["data"]["items"][0]["variant_id"] == variant_id
        assert cart.json()["data"]["items"][0]["quantity"] == 2

        # --- Customer sets up checkout prerequisites ---
        address = await async_client.post("/v1/addresses/", headers=auth_headers, json={
            "street": "123 Test St", "city": "Lagos", "state": "Lagos", "post_code": "100001", "country": "NG"
        })
        shipping_method = await async_client.post("/v1/shipping/methods/", headers=admin_headers, json={
            "name": "Standard", "price": 10.0, "estimated_days": 5
        })
        payment_method = PaymentMethod(
            id=uuid7(), user_id=test_user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
            last_four="4242", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
            stripe_payment_method_id=f"pm_test_{uuid4().hex[:16]}", is_default=True, is_active=True,
        )
        db_session.add(payment_method)
        await db_session.commit()

        mocker.patch(
            "services.commerce.payments.PaymentService.process_idempotent",
            return_value={"status": "succeeded", "payment_intent_id": str(uuid4())},
        )
        mocker.patch("services.accounts.email.EmailService.send_order_confirmation_email", return_value=None)

        # --- Customer checks out ---
        checkout = await async_client.post("/v1/orders/checkout/", headers=auth_headers, json={
            "shipping_address_id": address.json()["data"]["id"],
            "shipping_method_id": shipping_method.json()["data"]["id"],
            "payment_method_id": str(payment_method.id),
        })
        assert checkout.status_code == 200, checkout.text
        order = checkout.json()["data"]
        assert order["order_status"] == "confirmed"
        assert order["payment_status"] == "paid"
        assert order["items"][0]["variant_id"] == variant_id
        assert order["items"][0]["quantity"] == 2

        # --- Cart is cleared and inventory was actually held/decremented ---
        cart_after = await async_client.get("/v1/cart/", headers=auth_headers)
        assert cart_after.json()["data"]["items"] == []

        variants_after = await async_client.get(f"/v1/products/{product_id}/variants/")
        assert variants_after.json()["data"][0]["stock"] == 1
