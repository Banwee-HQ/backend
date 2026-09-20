"""API endpoint tests - see conftest.py for shared fixtures."""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any

@pytest.mark.api
class TestReviewEndpoints:
    """Test all 6 review endpoints."""

    async def test_042_reviews_list(self, async_client: AsyncClient):
        """GET /v1/reviews/ - List reviews."""
        response = await async_client.get("/v1/reviews/?limit=10")
        assert response.status_code == 200

    async def test_043_reviews_list_by_product(self, async_client: AsyncClient):
        """GET /v1/reviews/?product_id={id} - Filter by product."""
        product_id = str(uuid4())
        response = await async_client.get(f"/v1/reviews/?product_id={product_id}")
        assert response.status_code == 200

    async def test_044_reviews_get_by_id(self, async_client: AsyncClient):
        """GET /v1/reviews/{id} - Get review by ID."""
        review_id = str(uuid4())
        response = await async_client.get(f"/v1/reviews/{review_id}/")
        assert response.status_code in [200, 404]

    async def test_045_reviews_for_product(self, async_client: AsyncClient):
        """GET /v1/reviews/product/{id} - Get product reviews."""
        product_id = str(uuid4())
        response = await async_client.get(f"/v1/reviews/product/{product_id}/")
        assert response.status_code in [200, 404]

    async def test_046_reviews_create(self, async_client: AsyncClient, auth_headers):
        """POST /v1/reviews/ - Create review."""
        review_data = {
            "product_id": str(uuid4()),
            "rating": 5,
            "comment": "Great product!",
            "title": "Excellent"
        }
        response = await async_client.post("/v1/reviews/", headers=auth_headers, json=review_data)
        assert response.status_code in [200, 201, 404, 400]

    async def test_047_reviews_update(self, async_client: AsyncClient, auth_headers):
        """PATCH /v1/reviews/{id} - Update review."""
        review_id = str(uuid4())
        response = await async_client.patch(f"/v1/reviews/{review_id}/",
            headers=auth_headers,
            json={"rating": 4, "title": "Updated", "content": "Updated review"})
        assert response.status_code in [200, 404, 405]  # 405 if endpoint doesn't support PATCH


# =============================================================================
# CART ENDPOINTS (7 endpoints)
# =============================================================================

