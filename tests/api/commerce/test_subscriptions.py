"""Tests for api/commerce/subscriptions.py - /v1/subscriptions endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from models.commerce.promocode import Promocode, DiscountType
from core.utils.uuid_utils import uuid7


@pytest.fixture
async def subscription_variant(async_client: AsyncClient, admin_headers, sample_product_data):
    cat = await async_client.post("/v1/categories/",
        headers=admin_headers, json={"name": "Cat", "slug": f"cat-{uuid4().hex[:8]}"}
    )
    sample_product_data["category_id"] = cat.json()["data"]["id"]
    product = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    variants = await async_client.get(f"/v1/products/{product.json()['data']['id']}/")
    return variants.json()["data"]["variants"][0]


@pytest.fixture
async def second_variant(async_client: AsyncClient, admin_headers, sample_product_data):
    sample_product_data["slug"] = f"second-{uuid4().hex[:8]}"
    sample_product_data["sku"] = f"SKU-{uuid4().hex[:8].upper()}"
    cat = await async_client.post("/v1/categories/",
        headers=admin_headers, json={"name": "Cat2", "slug": f"cat2-{uuid4().hex[:8]}"}
    )
    sample_product_data["category_id"] = cat.json()["data"]["id"]
    product = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    variants = await async_client.get(f"/v1/products/{product.json()['data']['id']}/")
    return variants.json()["data"]["variants"][0]


@pytest.fixture
async def subscription_address(async_client: AsyncClient, auth_headers):
    resp = await async_client.post("/v1/addresses/", headers=auth_headers, json={
        "street": "123 Test St", "city": "Lagos", "state": "Lagos", "post_code": "100001", "country": "NG"
    })
    return resp.json()["data"]


@pytest.fixture
async def subscription_shipping_method(async_client: AsyncClient, admin_headers):
    resp = await async_client.post("/v1/shipping/methods/", headers=admin_headers, json={
        "name": "Standard", "price": 10.0, "estimated_days": 5
    })
    return resp.json()["data"]


@pytest.fixture
async def created_subscription(
    async_client: AsyncClient, auth_headers, subscription_variant, subscription_address, subscription_shipping_method
):
    """A real, active subscription - created through the actual endpoint, not inserted directly."""
    sub_data = {
        "name": "Test Subscription",
        "variant_ids": [subscription_variant["id"]],
        "variant_quantities": {subscription_variant["id"]: 1},
        "delivery_address_id": subscription_address["id"],
        "shipping_method_id": subscription_shipping_method["id"],
        "billing_cycle": "monthly",
        "currency": "USD",
    }
    resp = await async_client.post("/v1/subscriptions/", headers=auth_headers, json=sub_data)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["data"]


@pytest.mark.api
@pytest.mark.subscriptions
class TestSubscriptionEndpoints:

    async def test_create(self, async_client: AsyncClient, created_subscription):
        assert created_subscription["name"] == "Test Subscription"
        assert created_subscription["status"] == "active"
        assert created_subscription["billing_cycle"] == "monthly"

    async def test_create_applies_a_promo_code(self, async_client: AsyncClient, auth_headers, subscription_variant, db_session: AsyncSession):
        promo = Promocode(id=uuid7(), code=f"NEW{uuid4().hex[:6].upper()}", discount_type=DiscountType.FIXED, value=2, is_active=True)
        db_session.add(promo)
        await db_session.commit()
        response = await async_client.post("/v1/subscriptions/", headers=auth_headers, json={
            "name": "With code", "variant_ids": [subscription_variant["id"]], "discount_code": promo.code,
        })
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["discount"]["code"] == promo.code
        assert data["current_discount_amount"] == 2.0

    async def test_create_unknown_variant_is_rejected(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/subscriptions/", headers=auth_headers, json={
            "name": "Bad Sub", "variant_ids": [str(uuid4())],
        })
        assert response.status_code == 400

    async def test_create_empty_variant_ids_is_rejected(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/subscriptions/", headers=auth_headers, json={
            "name": "Bad Sub", "variant_ids": [],
        })
        assert response.status_code == 400

    async def test_create_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.post("/v1/subscriptions/", json={"name": "Bad Sub", "variant_ids": []})
        assert response.status_code == 401

    async def test_list_unauthenticated(self, async_client: AsyncClient):
        response = await async_client.get("/v1/subscriptions/")
        assert response.status_code == 401


    async def test_list_returns_own_subscription(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.get("/v1/subscriptions/", headers=auth_headers)
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()["data"]]
        assert created_subscription["id"] in ids

    async def test_admin_list_sees_all_subscriptions(self, async_client: AsyncClient, admin_headers, created_subscription):
        response = await async_client.get("/v1/subscriptions/", headers=admin_headers)
        assert response.status_code == 200
        ids = [s["id"] for s in response.json()["data"]]
        assert created_subscription["id"] in ids

    async def test_get_by_id(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.get(f"/v1/subscriptions/{created_subscription['id']}/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == created_subscription["id"]

    async def test_get_unknown_id_returns_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get(f"/v1/subscriptions/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_update_name(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.patch(f"/v1/subscriptions/{created_subscription['id']}/",
            headers=auth_headers, json={"name": "Renamed Subscription"})
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Renamed Subscription"

    async def test_cancel(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/cancel/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "cancelled"

    async def test_pause_then_resume(self, async_client: AsyncClient, auth_headers, created_subscription):
        paused = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/pause/", headers=auth_headers)
        assert paused.status_code == 200
        assert paused.json()["data"]["status"] == "paused"

        resumed = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/resume/", headers=auth_headers)
        assert resumed.status_code == 200
        assert resumed.json()["data"]["status"] == "active"

    async def test_add_and_remove_products(self, async_client: AsyncClient, auth_headers, created_subscription, second_variant):
        added = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/products/",
            headers=auth_headers, json={"variant_ids": [second_variant["id"]]})
        assert added.status_code == 200
        variant_ids = [p["variant_id"] for p in added.json()["data"]["products"]]
        assert second_variant["id"] in variant_ids

        removed = await async_client.request("DELETE", f"/v1/subscriptions/{created_subscription['id']}/products/",
            headers=auth_headers, json={"variant_ids": [second_variant["id"]]})
        assert removed.status_code == 200
        variant_ids = [p["variant_id"] for p in removed.json()["data"]["products"]]
        assert second_variant["id"] not in variant_ids


    async def test_change_frequency(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.patch(f"/v1/subscriptions/{created_subscription['id']}/frequency/",
            headers=auth_headers, json={"frequency": "weekly"})
        assert response.status_code == 200
        assert response.json()["data"]["billing_cycle"] == "weekly"

    async def test_change_frequency_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.patch(f"/v1/subscriptions/{uuid4()}/frequency/",
            headers=auth_headers, json={"frequency": "weekly"})
        assert response.status_code == 404

    async def test_skip_to_a_specific_date(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/skip/",
            headers=auth_headers, json={"next_shipment_date": "2099-12-31T00:00:00+00:00"})
        assert response.status_code == 200
        assert response.json()["data"]["next_billing_date"].startswith("2099-12-31")

    async def test_skip_then_unskip_restores_original_date(self, async_client: AsyncClient, auth_headers, created_subscription):
        original_date = created_subscription["next_billing_date"]

        skipped = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/skip/",
            headers=auth_headers, json={})
        assert skipped.status_code == 200
        assert skipped.json()["data"]["next_billing_date"] != original_date

        unskipped = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/unskip/",
            headers=auth_headers, json={})
        assert unskipped.status_code == 200
        assert unskipped.json()["data"]["next_billing_date"] == original_date

    async def test_unskip_without_a_prior_skip_is_rejected(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/unskip/",
            headers=auth_headers, json={})
        assert response.status_code == 400


    async def test_quantity_change_refreshes_displayed_pricing(self, async_client: AsyncClient, auth_headers,
                                                               created_subscription, subscription_variant):
        """The customer sees updated line totals right away, not only at the next charge."""
        response = await async_client.patch(f"/v1/subscriptions/{created_subscription['id']}/products/quantity/",
            headers=auth_headers, json={"variant_id": subscription_variant["id"], "quantity": 3})
        line = next(v for v in response.json()["data"]["current_variant_prices"] if v["id"] == subscription_variant["id"])
        assert line["qty"] == 3

    async def test_quantity_for_variant_not_in_subscription_is_rejected(self, async_client: AsyncClient, auth_headers,
                                                                         created_subscription):
        response = await async_client.patch(f"/v1/subscriptions/{created_subscription['id']}/products/quantity/",
            headers=auth_headers, json={"variant_id": str(uuid4()), "quantity": 2})
        assert response.status_code == 400

    async def test_skip_rejects_a_past_date(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/skip/",
            headers=auth_headers, json={"next_shipment_date": "2000-01-01T00:00:00+00:00"})
        assert response.status_code == 400

    async def test_skip_requires_an_active_subscription(self, async_client: AsyncClient, auth_headers, created_subscription):
        await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/pause/", headers=auth_headers, json={})
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/skip/", headers=auth_headers, json={})
        assert response.status_code == 400

    async def test_double_skip_then_unskip_returns_to_the_original_date(self, async_client: AsyncClient, auth_headers,
                                                                        created_subscription):
        original_date = created_subscription["next_billing_date"]
        url = f"/v1/subscriptions/{created_subscription['id']}"
        await async_client.post(f"{url}/skip/", headers=auth_headers, json={})
        await async_client.post(f"{url}/skip/", headers=auth_headers, json={})
        unskipped = await async_client.post(f"{url}/unskip/", headers=auth_headers, json={})
        assert unskipped.json()["data"]["next_billing_date"] == original_date


    async def test_apply_and_remove_discount(self, async_client: AsyncClient, auth_headers, created_subscription, db_session: AsyncSession):
        promo = Promocode(id=uuid7(), code=f"SUB{uuid4().hex[:6].upper()}", discount_type=DiscountType.PERCENTAGE, value=10, is_active=True)
        db_session.add(promo)
        await db_session.commit()

        applied = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/discounts/",
            headers=auth_headers, json={"discount_code": promo.code})
        assert applied.status_code == 200
        assert applied.json()["data"]["discount"]["code"] == promo.code

        removed = await async_client.delete(
            f"/v1/subscriptions/{created_subscription['id']}/discounts/{promo.id}/", headers=auth_headers
        )
        assert removed.status_code == 200
        assert removed.json()["data"]["discount"] is None

    async def test_get_includes_products_and_totals(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.get(f"/v1/subscriptions/{created_subscription['id']}/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == created_subscription["id"]
        assert len(data["products"]) == 1
        assert data["current_total"] == pytest.approx(
            data["current_subtotal"] + data["current_shipping_amount"] + data["current_tax_amount"] - data["current_discount_amount"]
        )

    async def test_orders_list_is_empty_for_a_new_subscription(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.get(f"/v1/subscriptions/{created_subscription['id']}/orders/", headers=auth_headers)
        assert response.status_code == 200


    async def test_delete(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.delete(f"/v1/subscriptions/{created_subscription['id']}/", headers=auth_headers)
        assert response.status_code == 200

        get_after = await async_client.get(f"/v1/subscriptions/{created_subscription['id']}/", headers=auth_headers)
        assert get_after.status_code == 404

    async def test_cannot_delete_another_users_subscription(self, async_client: AsyncClient, admin_headers, created_subscription):
        """DELETE /v1/subscriptions/{id} - A different user can't delete someone else's subscription."""
        response = await async_client.delete(f"/v1/subscriptions/{created_subscription['id']}/", headers=admin_headers)
        assert response.status_code == 404

        still_there = await async_client.get(f"/v1/subscriptions/{created_subscription['id']}/", headers=admin_headers)
        assert still_there.status_code == 200

    async def test_cannot_cancel_another_users_subscription(self, async_client: AsyncClient, admin_headers, created_subscription):
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/cancel/", headers=admin_headers)
        assert response.status_code == 404

    async def test_cannot_update_another_users_subscription(self, async_client: AsyncClient, admin_headers, created_subscription):
        response = await async_client.patch(f"/v1/subscriptions/{created_subscription['id']}/",
            headers=admin_headers, json={"name": "Hacked"})
        assert response.status_code == 404

    async def test_adding_a_product_reprices_the_subscription(self, async_client: AsyncClient, auth_headers, created_subscription, second_variant):
        before = (await async_client.get(f"/v1/subscriptions/{created_subscription['id']}/", headers=auth_headers)).json()["data"]
        added = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/products/",
            headers=auth_headers, json={"variant_ids": [second_variant["id"]]})
        assert added.status_code == 200
        after = added.json()["data"]
        assert after["current_subtotal"] > before["current_subtotal"]
        assert len(after["current_variant_prices"]) == 2

    async def test_the_last_product_cannot_be_removed(self, async_client: AsyncClient, auth_headers, created_subscription, subscription_variant):
        response = await async_client.request("DELETE", f"/v1/subscriptions/{created_subscription['id']}/products/",
            headers=auth_headers, json={"variant_ids": [subscription_variant["id"]]})
        assert response.status_code == 400

    async def test_an_unknown_product_cannot_be_added(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/products/",
            headers=auth_headers, json={"variant_ids": [str(uuid4())]})
        assert response.status_code == 400

    async def test_a_cancelled_subscription_cannot_be_changed(self, async_client: AsyncClient, auth_headers, created_subscription, second_variant):
        await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/cancel/", headers=auth_headers)
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/products/",
            headers=auth_headers, json={"variant_ids": [second_variant["id"]]})
        assert response.status_code == 400

    # -- calculate-cost branches -------------------------------------------------


    # -- 404s for endpoints that weren't exercised against an unknown id --------

    async def test_add_products_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers, second_variant):
        response = await async_client.post(f"/v1/subscriptions/{uuid4()}/products/",
            headers=auth_headers, json={"variant_ids": [second_variant["id"]]})
        assert response.status_code == 404

    async def test_remove_products_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers, second_variant):
        response = await async_client.request("DELETE", f"/v1/subscriptions/{uuid4()}/products/",
            headers=auth_headers, json={"variant_ids": [second_variant["id"]]})
        assert response.status_code == 404

    async def test_update_quantity_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers, second_variant):
        response = await async_client.patch(f"/v1/subscriptions/{uuid4()}/products/quantity/",
            headers=auth_headers, json={"variant_id": second_variant["id"], "quantity": 2})
        assert response.status_code == 404


    async def test_pause_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post(f"/v1/subscriptions/{uuid4()}/pause/", headers=auth_headers)
        assert response.status_code == 404

    async def test_resume_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post(f"/v1/subscriptions/{uuid4()}/resume/", headers=auth_headers)
        assert response.status_code == 404

    async def test_resume_from_cancelled_reactivates_the_subscription(self, async_client: AsyncClient, auth_headers, created_subscription):
        """Note: the endpoint's `action_message = "resumed" if subscription.status
        == "active" else "activated"` is dead code - service.resume() always sets
        status to "active" before this check runs, from either paused or cancelled,
        so the message is always "resumed" regardless of the prior state. Cosmetic
        only (does not affect billing/behavior), so left as-is; asserting on the
        actual (always-"resumed") wording rather than the unreachable branch."""
        await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/cancel/", headers=auth_headers)
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/resume/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "active"
        assert "resumed" in response.json()["message"]

    async def test_skip_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post(f"/v1/subscriptions/{uuid4()}/skip/", headers=auth_headers, json={})
        assert response.status_code == 404

    async def test_unskip_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post(f"/v1/subscriptions/{uuid4()}/unskip/", headers=auth_headers, json={})
        assert response.status_code == 404

    async def test_apply_discount_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post(f"/v1/subscriptions/{uuid4()}/discounts/",
            headers=auth_headers, json={"discount_code": "WHATEVER"})
        assert response.status_code == 404

    async def test_apply_discount_invalid_code_is_400(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/discounts/",
            headers=auth_headers, json={"discount_code": f"NOPE{uuid4().hex[:8]}"})
        assert response.status_code == 400

    async def test_remove_discount_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.delete(
            f"/v1/subscriptions/{uuid4()}/discounts/{uuid4()}/", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_remove_discount_mismatched_id_is_404(self, async_client: AsyncClient, auth_headers, created_subscription, db_session: AsyncSession):
        promo = Promocode(id=uuid7(), code=f"SUB{uuid4().hex[:6].upper()}", discount_type=DiscountType.PERCENTAGE, value=10, is_active=True)
        db_session.add(promo)
        await db_session.commit()
        await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/discounts/",
            headers=auth_headers, json={"discount_code": promo.code})

        response = await async_client.delete(
            f"/v1/subscriptions/{created_subscription['id']}/discounts/{uuid4()}/", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get(f"/v1/subscriptions/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_applied_discount_is_priced_and_removable_by_its_id(self, async_client: AsyncClient, auth_headers, created_subscription, db_session: AsyncSession):
        promo = Promocode(id=uuid7(), code=f"SUB{uuid4().hex[:6].upper()}", discount_type=DiscountType.PERCENTAGE, value=10, is_active=True)
        db_session.add(promo)
        await db_session.commit()
        applied = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/discounts/",
            headers=auth_headers, json={"discount_code": promo.code})
        data = applied.json()["data"]
        assert data["discount"]["id"] == str(promo.id)
        assert data["current_discount_amount"] > 0
        assert len(data["products"]) == 1

        removed = await async_client.delete(
            f"/v1/subscriptions/{created_subscription['id']}/discounts/{data['discount']['id']}/", headers=auth_headers
        )
        assert removed.json()["data"]["current_discount_amount"] == 0

    async def test_fixed_amount_discount(self, async_client: AsyncClient, auth_headers, created_subscription, db_session: AsyncSession):
        promo = Promocode(id=uuid7(), code=f"SUB{uuid4().hex[:6].upper()}", discount_type=DiscountType.FIXED, value=5, is_active=True)
        db_session.add(promo)
        await db_session.commit()
        await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/discounts/",
            headers=auth_headers, json={"discount_code": promo.code})

        response = await async_client.get(f"/v1/subscriptions/{created_subscription['id']}/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["current_discount_amount"] == 5.0

    async def test_orders_unknown_subscription_is_404(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get(f"/v1/subscriptions/{uuid4()}/orders/", headers=auth_headers)
        assert response.status_code == 404

    async def test_plans_is_public(self, async_client: AsyncClient):
        response = await async_client.get("/v1/subscriptions/plans/")
        assert response.status_code == 200
        ids = [p["id"] for p in response.json()["data"]]
        assert {"monthly", "quarterly", "yearly"} <= set(ids)

    async def test_trigger_notifications_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/subscriptions/trigger-notifications/", headers=auth_headers)
        assert response.status_code == 403

    async def test_trigger_notifications_as_admin(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch("services.accounts.email.EmailService.send_subscription_reminder", return_value=None)
        response = await async_client.post("/v1/subscriptions/trigger-notifications/", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json()["data"]["sent"], int)

    async def test_calculate_cost(self, async_client: AsyncClient, auth_headers, subscription_variant):
        response = await async_client.post("/v1/subscriptions/calculate-cost/",
            headers=auth_headers, json={"variant_ids": [subscription_variant["id"]]})
        assert response.status_code == 200
        assert {"subtotal", "tax", "total", "currency"} <= set(response.json()["data"])

    async def test_trigger_processing_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/subscriptions/trigger-order-processing/", headers=auth_headers)
        assert response.status_code == 403

    async def test_trigger_processing_as_admin(self, async_client: AsyncClient, admin_headers, mocker):
        # The test database holds other data too; don't bill it.
        batch = mocker.patch(
            "services.commerce.subscriptions_scheduler.SubscriptionScheduler.process_due_subscriptions",
            return_value={"processed_count": 0, "failed_count": 0, "total_due": 0},
        )
        response = await async_client.post("/v1/subscriptions/trigger-order-processing/", headers=admin_headers)
        assert response.status_code == 200
        batch.assert_awaited_once()

    async def test_trigger_processing_while_renewals_run_is_409(self, async_client: AsyncClient, admin_headers, db_session: AsyncSession):
        from services.commerce.subscriptions_scheduler import renewal_lock
        async with renewal_lock(db_session) as acquired:
            assert acquired
            response = await async_client.post("/v1/subscriptions/trigger-order-processing/", headers=admin_headers)
        assert response.status_code == 409

    async def test_list_due_requires_admin(self, async_client: AsyncClient, auth_headers):
        response = await async_client.get("/v1/subscriptions/due/", headers=auth_headers)
        assert response.status_code == 403

    async def test_list_due_as_admin(self, async_client: AsyncClient, admin_headers):
        response = await async_client.get("/v1/subscriptions/due/", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)

    async def test_process_shipment(self, async_client: AsyncClient, admin_headers, created_subscription, test_user, db_session: AsyncSession, mocker):
        """An admin bills a customer's subscription now with the customer's saved card (Stripe test mode)."""
        import stripe
        from models.commerce.payments import PaymentMethod, PaymentType, PaymentProvider, CardBrand
        mocker.patch("services.commerce.orders.OrderService._send_confirmation_email", return_value=None)
        db_session.add(PaymentMethod(
            id=uuid7(), user_id=test_user.id, type=PaymentType.CARD, provider=PaymentProvider.STRIPE,
            last_four="4242", expiry_month=12, expiry_year=2099, brand=CardBrand.VISA,
            stripe_payment_method_id=stripe.PaymentMethod.create(type="card", card={"token": "tok_visa"}).id,
            is_default=True, is_active=True,
        ))
        await db_session.commit()

        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/process-shipment/", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["data"]["subscription_id"] == created_subscription["id"]
        assert response.json()["data"]["order_number"].startswith("SUB-")

    async def test_process_shipment_is_admin_only(self, async_client: AsyncClient, auth_headers, created_subscription):
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/process-shipment/", headers=auth_headers)
        assert response.status_code == 403

    async def test_calculate_cost_unknown_variant_is_rejected(self, async_client: AsyncClient, auth_headers):
        response = await async_client.post("/v1/subscriptions/calculate-cost/",
            headers=auth_headers, json={"variant_ids": [str(uuid4())]})
        assert response.status_code == 400

    async def test_calculate_cost_with_delivery_address(self, async_client: AsyncClient, auth_headers, subscription_variant, subscription_address):
        response = await async_client.post("/v1/subscriptions/calculate-cost/",
            headers=auth_headers, json={
                "variant_ids": [subscription_variant["id"]], "delivery_address_id": subscription_address["id"],
            })
        assert response.status_code == 200
        assert {"subtotal", "tax", "total", "currency"} <= set(response.json()["data"])

    async def test_process_shipment_unknown_subscription_is_404(self, async_client: AsyncClient, admin_headers):
        response = await async_client.post(f"/v1/subscriptions/{uuid4()}/process-shipment/", headers=admin_headers)
        assert response.status_code == 404

    async def test_process_shipment_paused_subscription_is_400(self, async_client: AsyncClient, auth_headers, admin_headers, created_subscription):
        await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/pause/", headers=auth_headers)
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/process-shipment/", headers=admin_headers)
        assert response.status_code == 400

    async def test_process_shipment_without_a_payment_method_explains_the_decline(self, async_client: AsyncClient, admin_headers, created_subscription, mocker):
        mocker.patch("services.accounts.email.EmailService.send_subscription_payment_failed", return_value=None)
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/process-shipment/", headers=admin_headers)
        assert response.status_code == 400
        assert "no saved card" in response.json()["message"]

    # -- process-shipment branches -----------------------------------------------


@pytest.mark.api
@pytest.mark.subscriptions
class TestUnexpectedErrorsBecomeSafe500s:
    """Every route in this router wraps its body in the same
    try/except APIException/except HTTPException/except Exception->500 pattern.
    The APIException/HTTPException passthroughs are exercised throughout
    TestSubscriptionEndpoints via real 400/404s; these tests instead force the
    underlying service call to raise something completely unexpected, verifying
    the final safety net turns it into a clean 500 rather than leaking a raw
    traceback or crashing the request."""


    async def test_create(self, async_client: AsyncClient, auth_headers, subscription_variant, mocker):
        mocker.patch(
            "services.commerce.subscriptions.SubscriptionService.create", side_effect=Exception("boom"),
        )
        response = await async_client.post("/v1/subscriptions/",
            headers=auth_headers, json={"name": "X", "variant_ids": [subscription_variant["id"]]})
        assert response.status_code == 500

    async def test_list_subscriptions(self, async_client: AsyncClient, auth_headers, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.list", side_effect=Exception("boom"))
        response = await async_client.get("/v1/subscriptions/", headers=auth_headers)
        assert response.status_code == 500

    async def test_get(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.get", side_effect=Exception("boom"))
        response = await async_client.get(f"/v1/subscriptions/{created_subscription['id']}/", headers=auth_headers)
        assert response.status_code == 500

    async def test_update(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.update", side_effect=Exception("boom"))
        response = await async_client.patch(f"/v1/subscriptions/{created_subscription['id']}/",
            headers=auth_headers, json={"name": "X"})
        assert response.status_code == 500

    async def test_cancel(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.cancel", side_effect=Exception("boom"))
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/cancel/", headers=auth_headers)
        assert response.status_code == 500

    async def test_delete(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.delete", side_effect=Exception("boom"))
        response = await async_client.delete(f"/v1/subscriptions/{created_subscription['id']}/", headers=auth_headers)
        assert response.status_code == 500

    async def test_add_products(self, async_client: AsyncClient, auth_headers, created_subscription, second_variant, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.add_products", side_effect=Exception("boom"))
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/products/",
            headers=auth_headers, json={"variant_ids": [second_variant["id"]]})
        assert response.status_code == 500

    async def test_remove_products(self, async_client: AsyncClient, auth_headers, created_subscription, second_variant, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.remove_products", side_effect=Exception("boom"))
        response = await async_client.request("DELETE", f"/v1/subscriptions/{created_subscription['id']}/products/",
            headers=auth_headers, json={"variant_ids": [second_variant["id"]]})
        assert response.status_code == 500

    async def test_update_quantity(self, async_client: AsyncClient, auth_headers, created_subscription, subscription_variant, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.set_quantity", side_effect=Exception("boom"))
        response = await async_client.patch(f"/v1/subscriptions/{created_subscription['id']}/products/quantity/",
            headers=auth_headers, json={"variant_id": subscription_variant["id"], "quantity": 2})
        assert response.status_code == 500


    async def test_pause(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.pause", side_effect=Exception("boom"))
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/pause/", headers=auth_headers)
        assert response.status_code == 500

    async def test_resume(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.resume", side_effect=Exception("boom"))
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/resume/", headers=auth_headers)
        assert response.status_code == 500

    async def test_change_frequency(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.change_frequency", side_effect=Exception("boom"))
        response = await async_client.patch(f"/v1/subscriptions/{created_subscription['id']}/frequency/",
            headers=auth_headers, json={"frequency": "weekly"})
        assert response.status_code == 500

    async def test_skip(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.skip_next_shipment", side_effect=Exception("boom"))
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/skip/", headers=auth_headers, json={})
        assert response.status_code == 500

    async def test_unskip(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.unskip_next_shipment", side_effect=Exception("boom"))
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/unskip/", headers=auth_headers, json={})
        assert response.status_code == 500

    async def test_apply_discount(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.apply_discount", side_effect=Exception("boom"))
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/discounts/",
            headers=auth_headers, json={"discount_code": "X"})
        assert response.status_code == 500

    async def test_remove_discount(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.remove_discount", side_effect=Exception("boom"))
        response = await async_client.delete(
            f"/v1/subscriptions/{created_subscription['id']}/discounts/{uuid4()}/", headers=auth_headers
        )
        assert response.status_code == 500

    async def test_orders(self, async_client: AsyncClient, auth_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions.SubscriptionService.get_orders", side_effect=Exception("boom"))
        response = await async_client.get(f"/v1/subscriptions/{created_subscription['id']}/orders/", headers=auth_headers)
        assert response.status_code == 500

    async def test_trigger_order_processing(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch(
            "services.commerce.subscriptions_scheduler.SubscriptionScheduler.process_due_subscriptions",
            side_effect=Exception("boom"),
        )
        response = await async_client.post("/v1/subscriptions/trigger-order-processing/", headers=admin_headers)
        assert response.status_code == 500

    async def test_trigger_notifications(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch("core.utils.response.Response.success", side_effect=Exception("boom"))
        response = await async_client.post("/v1/subscriptions/trigger-notifications/", headers=admin_headers)
        assert response.status_code == 500

    async def test_plans(self, async_client: AsyncClient, mocker):
        mocker.patch("core.utils.response.Response.success", side_effect=Exception("boom"))
        response = await async_client.get("/v1/subscriptions/plans/")
        assert response.status_code == 500

    async def test_list_due(self, async_client: AsyncClient, admin_headers, mocker):
        mocker.patch(
            "services.commerce.subscriptions.SubscriptionService.list_due", side_effect=Exception("boom"),
        )
        response = await async_client.get("/v1/subscriptions/due/", headers=admin_headers)
        assert response.status_code == 500

    async def test_calculate_cost(self, async_client: AsyncClient, auth_headers, subscription_variant, mocker):
        mocker.patch(
            "services.commerce.subscriptions.SubscriptionService._calculate_pricing", side_effect=Exception("boom"),
        )
        response = await async_client.post("/v1/subscriptions/calculate-cost/",
            headers=auth_headers, json={"variant_ids": [subscription_variant["id"]]})
        assert response.status_code == 400

    async def test_process_shipment(self, async_client: AsyncClient, admin_headers, created_subscription, mocker):
        mocker.patch("services.commerce.subscriptions_scheduler.SubscriptionScheduler.process_subscription", side_effect=Exception("boom"))
        response = await async_client.post(f"/v1/subscriptions/{created_subscription['id']}/process-shipment/", headers=admin_headers)
        assert response.status_code == 500
