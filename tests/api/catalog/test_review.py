"""Tests for api/catalog/review.py - /v1/reviews endpoints."""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.fixture
async def created_product(async_client: AsyncClient, admin_headers, sample_product_data):
    cat = await async_client.post("/v1/categories/",
        headers=admin_headers, json={"name": "Cat", "slug": f"cat-{uuid4().hex[:8]}"}
    )
    sample_product_data["category_id"] = cat.json()["data"]["id"]
    response = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    return response.json()["data"]


@pytest.fixture
async def created_review(async_client: AsyncClient, auth_headers, created_product):
    response = await async_client.post("/v1/reviews/", headers=auth_headers, json={
        "product_id": created_product["id"], "rating": 5, "comment": "Great product!"
    })
    return response.json()["data"]


@pytest.mark.api
class TestReviewEndpoints:

    async def test_list(self, async_client: AsyncClient, created_review):
        """GET /v1/reviews/ - List reviews."""
        response = await async_client.get("/v1/reviews/?limit=10")
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_list_by_product(self, async_client: AsyncClient, created_product, created_review):
        """GET /v1/reviews/?product_id={id} - Filter by product."""
        response = await async_client.get(f"/v1/reviews/?product_id={created_product['id']}")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_get_by_id(self, async_client: AsyncClient, created_review):
        """GET /v1/reviews/{id} - Get review by ID."""
        response = await async_client.get(f"/v1/reviews/{created_review['id']}/")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == created_review["id"]

    async def test_get_by_id_not_found(self, async_client: AsyncClient):
        """GET /v1/reviews/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/reviews/{uuid4()}/")
        assert response.status_code == 404

    async def test_for_product(self, async_client: AsyncClient, created_product, created_review):
        """GET /v1/reviews/product/{id} - Get product reviews."""
        response = await async_client.get(f"/v1/reviews/product/{created_product['id']}/")
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_create(self, async_client: AsyncClient, auth_headers, created_product):
        """POST /v1/reviews/ - Create review."""
        response = await async_client.post("/v1/reviews/", headers=auth_headers, json={
            "product_id": created_product["id"], "rating": 4, "comment": "Pretty good"
        })
        assert response.status_code == 200
        assert response.json()["data"]["rating"] == 4

    async def test_create_unknown_product(self, async_client: AsyncClient, auth_headers):
        """POST /v1/reviews/ - Unknown product returns 404."""
        response = await async_client.post("/v1/reviews/", headers=auth_headers, json={
            "product_id": str(uuid4()), "rating": 5
        })
        assert response.status_code == 404

    async def test_create_duplicate_rejected(self, async_client: AsyncClient, auth_headers, created_product, created_review):
        """POST /v1/reviews/ - A second review from the same user for the same product is rejected."""
        response = await async_client.post("/v1/reviews/", headers=auth_headers, json={
            "product_id": created_product["id"], "rating": 3
        })
        assert response.status_code == 400

    async def test_update_as_owner(self, async_client: AsyncClient, auth_headers, created_review):
        """PATCH /v1/reviews/{id} - Owner updates their review."""
        response = await async_client.patch(f"/v1/reviews/{created_review['id']}/",
            headers=auth_headers, json={"rating": 3, "comment": "Changed my mind"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["rating"] == 3

    async def test_update_not_owner_forbidden(self, async_client: AsyncClient, admin_headers, created_review):
        """PATCH /v1/reviews/{id} - Non-owner is forbidden."""
        response = await async_client.patch(f"/v1/reviews/{created_review['id']}/",
            headers=admin_headers, json={"rating": 1}
        )
        assert response.status_code == 403

    async def test_delete_as_owner(self, async_client: AsyncClient, auth_headers, created_review):
        """DELETE /v1/reviews/{id} - Owner deletes their review."""
        response = await async_client.delete(f"/v1/reviews/{created_review['id']}/", headers=auth_headers)
        assert response.status_code == 200

        get_resp = await async_client.get(f"/v1/reviews/{created_review['id']}/")
        assert get_resp.status_code == 404

    async def test_delete_not_owner_forbidden(self, async_client: AsyncClient, admin_headers, created_review):
        """DELETE /v1/reviews/{id} - Non-owner is forbidden."""
        response = await async_client.delete(f"/v1/reviews/{created_review['id']}/", headers=admin_headers)
        assert response.status_code == 403

    async def test_create_unauthenticated(self, async_client: AsyncClient, created_product):
        response = await async_client.post("/v1/reviews/", json={"product_id": created_product["id"], "rating": 5})
        assert response.status_code == 401

    async def test_update_unauthenticated(self, async_client: AsyncClient, created_review):
        response = await async_client.patch(f"/v1/reviews/{created_review['id']}/", json={"rating": 1})
        assert response.status_code == 401

    async def test_update_not_found(self, async_client: AsyncClient, auth_headers):
        response = await async_client.patch(f"/v1/reviews/{uuid4()}/", headers=auth_headers, json={"rating": 1})
        assert response.status_code == 404

    async def test_delete_not_found(self, async_client: AsyncClient, auth_headers):
        response = await async_client.delete(f"/v1/reviews/{uuid4()}/", headers=auth_headers)
        assert response.status_code == 404

    async def test_list_filters_by_rating(self, async_client: AsyncClient, created_review):
        response = await async_client.get("/v1/reviews/?min_rating=5&max_rating=5")
        assert response.status_code == 200
        assert all(r["rating"] == 5 for r in response.json()["data"])

        excluded = await async_client.get("/v1/reviews/?min_rating=1&max_rating=1")
        assert response.json()["data"] != [] and created_review["id"] not in [r["id"] for r in excluded.json()["data"]]

    async def test_list_sort_by_rating_asc(self, async_client: AsyncClient, created_review):
        response = await async_client.get("/v1/reviews/?sort_by=rating_asc")
        assert response.status_code == 200
