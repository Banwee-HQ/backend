"""Tests for api/catalog/products.py - /v1/products endpoints."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from uuid import uuid4

from core.exceptions import APIException
from services.catalog.products import ProductService
from services.catalog.category import CategoryService


def _async_raiser(exc):
    """Build an async function that always raises `exc` - used to monkeypatch a
    service method so a specific endpoint's except-clause body actually runs,
    matching the pattern in tests/api/commerce/test_payments.py."""
    async def _raise(*args, **kwargs):
        raise exc
    return _raise


@pytest.fixture
async def created_category(async_client: AsyncClient, admin_headers):
    response = await async_client.post("/v1/categories/",
        headers=admin_headers,
        json={"name": "Grains & Pulses", "slug": f"grains-pulses-{uuid4().hex[:8]}"}
    )
    return response.json()["data"]


@pytest.fixture
async def created_product(async_client: AsyncClient, admin_headers, sample_product_data, created_category):
    sample_product_data["category_id"] = created_category["id"]
    response = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
    return response.json()["data"]


@pytest.mark.api
class TestProductEndpoints:

    async def test_home(self, async_client: AsyncClient):
        """GET /v1/products/home - Get home data."""
        response = await async_client.get("/v1/products/home/")
        assert response.status_code == 200
        assert set(response.json()["data"]) == {"featured", "popular", "deals"}

    async def test_list(self, async_client: AsyncClient):
        """GET /v1/products/ - List products."""
        response = await async_client.get("/v1/products/?limit=10")
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_list_with_filters(self, async_client: AsyncClient):
        """GET /v1/products/ - List with price filters."""
        response = await async_client.get("/v1/products/?min_price=10&max_price=100")
        assert response.status_code == 200

    async def test_list_with_sorting(self, async_client: AsyncClient):
        """GET /v1/products/ - List with sorting."""
        response = await async_client.get("/v1/products/?sort_by=price&sort_order=asc")
        assert response.status_code == 200

    async def test_list_with_search(self, async_client: AsyncClient):
        """GET /v1/products/ - Search products."""
        response = await async_client.get("/v1/products/?q=organic")
        assert response.status_code == 200


    async def test_get_by_id_not_found(self, async_client: AsyncClient):
        """GET /v1/products/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/products/{uuid4()}/")
        assert response.status_code == 404

    async def test_get_by_id(self, async_client: AsyncClient, created_product):
        """GET /v1/products/{id} - Get an existing product."""
        response = await async_client.get(f"/v1/products/{created_product['id']}/")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == created_product["id"]

    async def test_get_by_slug(self, async_client: AsyncClient, created_product):
        """GET /v1/products/{slug} - Get a product by slug."""
        response = await async_client.get(f"/v1/products/{created_product['slug']}/")
        assert response.status_code == 200

    async def test_recommendations(self, async_client: AsyncClient, created_product):
        """GET /v1/products/{id}/recommendations - Get recommendations for a real product."""
        response = await async_client.get(f"/v1/products/{created_product['id']}/recommendations/")
        assert response.status_code == 200


    async def test_create_as_admin(self, async_client: AsyncClient, admin_headers, sample_product_data, created_category):
        """POST /v1/products/ - Create product (admin)."""
        sample_product_data["category_id"] = created_category["id"]
        response = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
        assert response.status_code == 200
        assert response.json()["data"]["name"] == sample_product_data["name"]

    async def test_create_requires_admin(self, async_client: AsyncClient, auth_headers, sample_product_data, created_category):
        """POST /v1/products/ - Non-admin is forbidden."""
        sample_product_data["category_id"] = created_category["id"]
        response = await async_client.post("/v1/products/", headers=auth_headers, json=sample_product_data)
        assert response.status_code == 403

    async def test_update_as_admin(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/{id} - Update product (admin)."""
        response = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=admin_headers, json={"name": "Updated Product"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Product"

    async def test_update_not_found(self, async_client: AsyncClient, admin_headers):
        """PATCH /v1/products/{id} - Unknown ID returns 404."""
        response = await async_client.patch(f"/v1/products/{uuid4()}/",
            headers=admin_headers, json={"name": "Updated"}
        )
        assert response.status_code == 404

    async def test_delete_as_admin(self, async_client: AsyncClient, admin_headers, created_product):
        """DELETE /v1/products/{id} - Delete product (admin)."""
        response = await async_client.delete(f"/v1/products/{created_product['id']}/", headers=admin_headers)
        assert response.status_code == 200

        get_resp = await async_client.get(f"/v1/products/{created_product['id']}/")
        assert get_resp.status_code == 404

    async def test_update_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.patch(f"/v1/products/{created_product['id']}/",
            headers=auth_headers, json={"name": "Hacked"}
        )
        assert response.status_code == 403

    async def test_delete_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.delete(f"/v1/products/{created_product['id']}/", headers=auth_headers)
        assert response.status_code == 403

    async def test_delete_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/products/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_recommendations_unknown_product(self, async_client: AsyncClient):
        response = await async_client.get(f"/v1/products/{uuid4()}/recommendations/")
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_featured(self, async_client: AsyncClient):
        """GET /v1/products/featured - List featured products."""
        response = await async_client.get("/v1/products/featured/")
        assert response.status_code == 200

    async def test_deals(self, async_client: AsyncClient):
        """GET /v1/products/deals - List products on sale."""
        response = await async_client.get("/v1/products/deals/")
        assert response.status_code == 200

    async def test_variants(self, async_client: AsyncClient, created_product):
        """GET /v1/products/{id}/variants - A newly created product has a default variant."""
        response = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    async def test_get_variant(self, async_client: AsyncClient, created_product):
        """GET /v1/products/variants/{id} - Get the default variant created with the product."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]

        response = await async_client.get(f"/v1/products/variants/{variant_id}/")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == variant_id

    async def test_variants_unknown_product(self, async_client: AsyncClient):
        response = await async_client.get(f"/v1/products/{uuid4()}/variants/")
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_get_variant_not_found(self, async_client: AsyncClient):
        response = await async_client.get(f"/v1/products/variants/{uuid4()}/")
        assert response.status_code == 404

    async def test_create_variant(self, async_client: AsyncClient, admin_headers, created_product):
        """POST /v1/products/{id}/variants - Create variant (admin)."""
        variant_data = {"name": "Large", "base_price": 99.99, "sale_price": 89.99, "stock": 100}
        response = await async_client.post(f"/v1/products/{created_product['id']}/variants/",
            headers=admin_headers, json=variant_data
        )
        assert response.status_code == 201
        assert response.json()["data"]["name"] == "Large"

    async def test_update_variant(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/variants/{id} - Update variant (admin)."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]

        response = await async_client.patch(f"/v1/products/variants/{variant_id}/",
            headers=admin_headers, json={"sale_price": 15.00}
        )
        assert response.status_code == 200
        assert response.json()["data"]["sale_price"] == 15.00

    async def test_delete_variant(self, async_client: AsyncClient, admin_headers, created_product):
        """DELETE /v1/products/variants/{id} - Delete variant (admin)."""
        create_resp = await async_client.post(f"/v1/products/{created_product['id']}/variants/",
            headers=admin_headers, json={"name": "Extra", "base_price": 10.0, "sale_price": 8.0}
        )
        variant_id = create_resp.json()["data"]["id"]

        response = await async_client.delete(f"/v1/products/variants/{variant_id}/", headers=admin_headers)
        assert response.status_code == 200

    async def test_delete_variant_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/products/variants/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404

    async def test_create_variant_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.post(f"/v1/products/{created_product['id']}/variants/",
            headers=auth_headers, json={"name": "Large", "base_price": 99.99}
        )
        assert response.status_code == 403

    async def test_update_variant_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        response = await async_client.patch(f"/v1/products/variants/{variant_id}/",
            headers=auth_headers, json={"sale_price": 1.0}
        )
        assert response.status_code == 403

    async def test_create_image(self, async_client: AsyncClient, admin_headers, created_product):
        """POST /v1/products/variants/{id}/images - Create image (admin)."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]

        response = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg", "alt_text": "Product image"}
        )
        assert response.status_code == 201

    async def test_list_images(self, async_client: AsyncClient, admin_headers, created_product):
        """GET /v1/products/variants/{id}/images - List images for a variant."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg"}
        )

        response = await async_client.get(f"/v1/products/variants/{variant_id}/images/")
        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    async def test_get_image(self, async_client: AsyncClient, admin_headers, created_product):
        """GET /v1/products/images/{id} - Get a specific image."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        created = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg"}
        )
        image_id = created.json()["data"]["id"]

        response = await async_client.get(f"/v1/products/images/{image_id}/")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == image_id

    async def test_get_image_not_found(self, async_client: AsyncClient):
        """GET /v1/products/images/{id} - Unknown ID returns 404."""
        response = await async_client.get(f"/v1/products/images/{uuid4()}/")
        assert response.status_code == 404

    async def test_update_image(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/images/{id} - Update image (admin)."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        created = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg"}
        )
        image_id = created.json()["data"]["id"]

        response = await async_client.patch(f"/v1/products/images/{image_id}/",
            headers=admin_headers, json={"alt_text": "Updated alt text"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["alt_text"] == "Updated alt text"

    async def test_delete_image(self, async_client: AsyncClient, admin_headers, created_product):
        """DELETE /v1/products/images/{id} - Delete image (admin)."""
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        created = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/img.jpg"}
        )
        image_id = created.json()["data"]["id"]

        response = await async_client.delete(f"/v1/products/images/{image_id}/", headers=admin_headers)
        assert response.status_code == 200

        get_after = await async_client.get(f"/v1/products/images/{image_id}/")
        assert get_after.status_code == 404

    async def test_moderate(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/{id}/moderate - Moderate product (admin)."""
        response = await async_client.patch(f"/v1/products/{created_product['id']}/moderate/",
            headers=admin_headers, json={"status": "approved"}
        )
        assert response.status_code == 200

    async def test_moderate_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.patch(f"/v1/products/{created_product['id']}/moderate/",
            headers=auth_headers, json={"status": "approved"}
        )
        assert response.status_code == 403

    async def test_feature(self, async_client: AsyncClient, admin_headers, created_product):
        """PATCH /v1/products/{id}/feature - Feature product (admin)."""
        response = await async_client.patch(f"/v1/products/{created_product['id']}/feature/",
            headers=admin_headers, params={"featured": True}
        )
        assert response.status_code == 200
        assert response.json()["data"]["is_featured"] is True

    async def test_feature_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        response = await async_client.patch(f"/v1/products/{created_product['id']}/feature/",
            headers=auth_headers, params={"featured": True}
        )
        assert response.status_code == 403

    async def test_create_image_requires_admin(self, async_client: AsyncClient, auth_headers, created_product):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        response = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=auth_headers, json={"url": "https://example.com/img.jpg"}
        )
        assert response.status_code == 403

    async def test_update_image_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.patch(f"/v1/products/images/{uuid4()}/",
            headers=admin_headers, json={"alt_text": "Nowhere"}
        )
        assert response.status_code == 404

    async def test_delete_image_not_found(self, async_client: AsyncClient, admin_headers):
        response = await async_client.delete(f"/v1/products/images/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 404


@pytest.mark.api
class TestErrorHandlingBranches:
    """Every endpoint wraps a lower-level call in try/except APIException/HTTPException/
    Exception. The known-error paths (404s etc) are exercised elsewhere via real service
    behavior; these tests drive the pass-through and generic-500 branches, which need a
    genuinely unexpected failure - simulated here by monkeypatching the service method,
    the same pattern used in tests/api/commerce/test_payments.py."""


    async def test_list_wraps_http_exception(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "list", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get("/v1/products/")
        assert response.status_code == 403

    async def test_list_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "list", _async_raiser(RuntimeError("boom")))
        response = await async_client.get("/v1/products/")
        assert response.status_code == 500


    async def test_recommended_wraps_http_exception(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "recommended", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get(f"/v1/products/{uuid4()}/recommendations/")
        assert response.status_code == 403

    async def test_recommended_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "recommended", _async_raiser(RuntimeError("boom")))
        response = await async_client.get(f"/v1/products/{uuid4()}/recommendations/")
        assert response.status_code == 500

    async def test_get_product_wraps_http_exception(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "get", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get(f"/v1/products/{uuid4()}/")
        assert response.status_code == 403

    async def test_get_product_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "get", _async_raiser(RuntimeError("boom")))
        response = await async_client.get(f"/v1/products/{uuid4()}/")
        assert response.status_code == 500

    async def test_create_wraps_api_exception(self, async_client: AsyncClient, admin_headers, sample_product_data, created_category, monkeypatch):
        sample_product_data["category_id"] = created_category["id"]
        monkeypatch.setattr(ProductService, "create", _async_raiser(APIException(status_code=418, message="teapot")))
        response = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
        assert response.status_code == 418

    async def test_create_wraps_http_exception(self, async_client: AsyncClient, admin_headers, sample_product_data, created_category, monkeypatch):
        sample_product_data["category_id"] = created_category["id"]
        monkeypatch.setattr(ProductService, "create", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
        assert response.status_code == 403

    async def test_create_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, sample_product_data, created_category, monkeypatch):
        sample_product_data["category_id"] = created_category["id"]
        monkeypatch.setattr(ProductService, "create", _async_raiser(RuntimeError("boom")))
        response = await async_client.post("/v1/products/", headers=admin_headers, json=sample_product_data)
        assert response.status_code == 500

    async def test_update_wraps_api_exception(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "update", _async_raiser(APIException(status_code=418, message="teapot")))
        response = await async_client.patch(f"/v1/products/{created_product['id']}/", headers=admin_headers, json={"name": "X"})
        assert response.status_code == 418

    async def test_update_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "update", _async_raiser(RuntimeError("boom")))
        response = await async_client.patch(f"/v1/products/{created_product['id']}/", headers=admin_headers, json={"name": "X"})
        assert response.status_code == 500

    async def test_delete_wraps_api_exception(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "delete", _async_raiser(APIException(status_code=418, message="teapot")))
        response = await async_client.delete(f"/v1/products/{created_product['id']}/", headers=admin_headers)
        assert response.status_code == 418

    async def test_delete_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "delete", _async_raiser(RuntimeError("boom")))
        response = await async_client.delete(f"/v1/products/{created_product['id']}/", headers=admin_headers)
        assert response.status_code == 500


    async def test_featured_wraps_http_exception(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "featured", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get("/v1/products/featured/")
        assert response.status_code == 403

    async def test_featured_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "featured", _async_raiser(RuntimeError("boom")))
        response = await async_client.get("/v1/products/featured/")
        assert response.status_code == 500

    async def test_deals_wraps_http_exception(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "list", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get("/v1/products/deals/")
        assert response.status_code == 403

    async def test_deals_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "list", _async_raiser(RuntimeError("boom")))
        response = await async_client.get("/v1/products/deals/")
        assert response.status_code == 500

    async def test_create_variant_unknown_product_is_404(self, async_client: AsyncClient, admin_headers):
        """Real trigger: ProductService.create_variant() raises a genuine APIException(404)."""
        response = await async_client.post(f"/v1/products/{uuid4()}/variants/",
            headers=admin_headers, json={"name": "Large", "base_price": 10.0, "sale_price": 8.0}
        )
        assert response.status_code == 404

    async def test_create_variant_wraps_http_exception(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "create_variant", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.post(f"/v1/products/{created_product['id']}/variants/",
            headers=admin_headers, json={"name": "Large", "base_price": 10.0, "sale_price": 8.0}
        )
        assert response.status_code == 403

    async def test_create_variant_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "create_variant", _async_raiser(RuntimeError("boom")))
        response = await async_client.post(f"/v1/products/{created_product['id']}/variants/",
            headers=admin_headers, json={"name": "Large", "base_price": 10.0, "sale_price": 8.0}
        )
        assert response.status_code == 500

    async def test_get_variant_wraps_http_exception(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "get_variant", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get(f"/v1/products/variants/{uuid4()}/")
        assert response.status_code == 403

    async def test_get_variant_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "get_variant", _async_raiser(RuntimeError("boom")))
        response = await async_client.get(f"/v1/products/variants/{uuid4()}/")
        assert response.status_code == 500

    async def test_list_variants_wraps_http_exception(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "list_variants", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get(f"/v1/products/{uuid4()}/variants/")
        assert response.status_code == 403

    async def test_list_variants_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "list_variants", _async_raiser(RuntimeError("boom")))
        response = await async_client.get(f"/v1/products/{uuid4()}/variants/")
        assert response.status_code == 500

    async def test_patch_variant_unknown_is_404(self, async_client: AsyncClient, admin_headers):
        """Real trigger: ProductService.update_variant() raises a genuine APIException(404)."""
        response = await async_client.patch(f"/v1/products/variants/{uuid4()}/",
            headers=admin_headers, json={"name": "X"}
        )
        assert response.status_code == 404

    async def test_patch_variant_wraps_http_exception(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        monkeypatch.setattr(ProductService, "update_variant", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.patch(f"/v1/products/variants/{variant_id}/", headers=admin_headers, json={"name": "X"})
        assert response.status_code == 403

    async def test_patch_variant_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        monkeypatch.setattr(ProductService, "update_variant", _async_raiser(RuntimeError("boom")))
        response = await async_client.patch(f"/v1/products/variants/{variant_id}/", headers=admin_headers, json={"name": "X"})
        assert response.status_code == 500

    async def test_delete_variant_wraps_http_exception(self, async_client: AsyncClient, admin_headers, monkeypatch):
        monkeypatch.setattr(ProductService, "delete_variant", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.delete(f"/v1/products/variants/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 403

    async def test_delete_variant_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, monkeypatch):
        monkeypatch.setattr(ProductService, "delete_variant", _async_raiser(RuntimeError("boom")))
        response = await async_client.delete(f"/v1/products/variants/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 500

    async def test_create_image_unknown_variant_is_404(self, async_client: AsyncClient, admin_headers):
        """Real trigger: ProductService.create_image() raises a genuine APIException(404)."""
        response = await async_client.post(f"/v1/products/variants/{uuid4()}/images/",
            headers=admin_headers, json={"url": "https://example.com/a.jpg"}
        )
        assert response.status_code == 404

    async def test_create_image_wraps_http_exception(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        monkeypatch.setattr(ProductService, "create_image", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/a.jpg"}
        )
        assert response.status_code == 403

    async def test_create_image_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        variants_resp = await async_client.get(f"/v1/products/{created_product['id']}/variants/")
        variant_id = variants_resp.json()["data"][0]["id"]
        monkeypatch.setattr(ProductService, "create_image", _async_raiser(RuntimeError("boom")))
        response = await async_client.post(f"/v1/products/variants/{variant_id}/images/",
            headers=admin_headers, json={"url": "https://example.com/a.jpg"}
        )
        assert response.status_code == 500

    async def test_get_image_wraps_http_exception(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "get_image", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get(f"/v1/products/images/{uuid4()}/")
        assert response.status_code == 403

    async def test_get_image_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "get_image", _async_raiser(RuntimeError("boom")))
        response = await async_client.get(f"/v1/products/images/{uuid4()}/")
        assert response.status_code == 500

    async def test_list_images_wraps_http_exception(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "list_images", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.get(f"/v1/products/variants/{uuid4()}/images/")
        assert response.status_code == 403

    async def test_list_images_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(ProductService, "list_images", _async_raiser(RuntimeError("boom")))
        response = await async_client.get(f"/v1/products/variants/{uuid4()}/images/")
        assert response.status_code == 500

    async def test_patch_image_wraps_http_exception(self, async_client: AsyncClient, admin_headers, monkeypatch):
        monkeypatch.setattr(ProductService, "update_image", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.patch(f"/v1/products/images/{uuid4()}/", headers=admin_headers, json={"alt_text": "X"})
        assert response.status_code == 403

    async def test_patch_image_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, monkeypatch):
        monkeypatch.setattr(ProductService, "update_image", _async_raiser(RuntimeError("boom")))
        response = await async_client.patch(f"/v1/products/images/{uuid4()}/", headers=admin_headers, json={"alt_text": "X"})
        assert response.status_code == 500

    async def test_delete_image_wraps_http_exception(self, async_client: AsyncClient, admin_headers, monkeypatch):
        monkeypatch.setattr(ProductService, "delete_image", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.delete(f"/v1/products/images/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 403

    async def test_delete_image_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, monkeypatch):
        monkeypatch.setattr(ProductService, "delete_image", _async_raiser(RuntimeError("boom")))
        response = await async_client.delete(f"/v1/products/images/{uuid4()}/", headers=admin_headers)
        assert response.status_code == 500

    async def test_moderate_unknown_product_is_404(self, async_client: AsyncClient, admin_headers):
        """Real trigger: ProductService.moderate() raises a genuine APIException(404)."""
        response = await async_client.patch(f"/v1/products/{uuid4()}/moderate/",
            headers=admin_headers, json={"status": "approved"}
        )
        assert response.status_code == 404

    async def test_moderate_wraps_http_exception(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "moderate", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.patch(f"/v1/products/{created_product['id']}/moderate/",
            headers=admin_headers, json={"status": "approved"}
        )
        assert response.status_code == 403

    async def test_moderate_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "moderate", _async_raiser(RuntimeError("boom")))
        response = await async_client.patch(f"/v1/products/{created_product['id']}/moderate/",
            headers=admin_headers, json={"status": "approved"}
        )
        assert response.status_code == 500

    async def test_feature_unknown_product_is_404(self, async_client: AsyncClient, admin_headers):
        """Real trigger: ProductService.set_featured() raises a genuine APIException(404)."""
        response = await async_client.patch(f"/v1/products/{uuid4()}/feature/",
            headers=admin_headers, params={"featured": True}
        )
        assert response.status_code == 404

    async def test_feature_wraps_http_exception(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "set_featured", _async_raiser(HTTPException(status_code=403, detail="nope")))
        response = await async_client.patch(f"/v1/products/{created_product['id']}/feature/",
            headers=admin_headers, params={"featured": True}
        )
        assert response.status_code == 403

    async def test_feature_wraps_unexpected_exception_as_500(self, async_client: AsyncClient, admin_headers, created_product, monkeypatch):
        monkeypatch.setattr(ProductService, "set_featured", _async_raiser(RuntimeError("boom")))
        response = await async_client.patch(f"/v1/products/{created_product['id']}/feature/",
            headers=admin_headers, params={"featured": True}
        )
        assert response.status_code == 500


@pytest.mark.api
class TestShortDescriptionRoundTrip:
    """short_description is stored and accepted on update, so it must also be returned -
    otherwise an edit form that round-trips the product would wipe it."""

    async def test_returned_on_create_and_get(self, async_client: AsyncClient, created_product):
        assert created_product["short_description"] == "Test product"
        response = await async_client.get(f"/v1/products/{created_product['id']}/")
        assert response.json()["data"]["short_description"] == "Test product"

    async def test_survives_unrelated_update(self, async_client: AsyncClient, admin_headers, created_product):
        response = await async_client.patch(
            f"/v1/products/{created_product['id']}/", headers=admin_headers, json={"name": "Renamed product"}
        )
        assert response.status_code == 200
        assert response.json()["data"]["short_description"] == "Test product"


@pytest.mark.api
class TestPriceSorting:
    """sort_by=price orders by each product's cheapest current variant price (Product has no price column)."""

    async def _create(self, client, headers, category_id, data, sale_price):
        payload = {**data, "slug": f"p-{uuid4().hex[:8]}", "sku": f"SKU-{uuid4().hex[:8]}",
                   "category_id": category_id, "base_price": 100.0, "sale_price": sale_price}
        response = await client.post("/v1/products/", headers=headers, json=payload)
        return response.json()["data"]["id"]

    async def test_orders_by_current_price(self, async_client: AsyncClient, admin_headers, sample_product_data, created_category):
        cheap = await self._create(async_client, admin_headers, created_category["id"], sample_product_data, 5.0)
        pricey = await self._create(async_client, admin_headers, created_category["id"], sample_product_data, 90.0)

        async def ordered(direction):
            response = await async_client.get(f"/v1/products/?sort_by=price&sort_order={direction}&limit=1000")
            return [p["id"] for p in response.json()["data"] if p["id"] in (cheap, pricey)]

        assert await ordered("asc") == [cheap, pricey]
        assert await ordered("desc") == [pricey, cheap]


@pytest.mark.api
class TestAdminProductList:
    """Non-active products vanish from the public list, so admins need their own listing to find them again."""

    async def _draft(self, client, headers, product):
        response = await client.patch(f"/v1/products/{product['id']}/", headers=headers, json={"product_status": "draft"})
        assert response.json()["data"]["product_status"] == "draft"

    async def test_draft_hidden_publicly_but_listed_for_admin(self, async_client: AsyncClient, admin_headers, created_product):
        await self._draft(async_client, admin_headers, created_product)

        public = await async_client.get("/v1/products/?limit=1000")
        assert created_product["id"] not in [p["id"] for p in public.json()["data"]]

        admin = await async_client.get("/v1/products/admin/?limit=1000", headers=admin_headers)
        assert admin.status_code == 200
        assert created_product["id"] in [p["id"] for p in admin.json()["data"]]
        assert admin.json()["pagination"]["total"] >= 1

    async def test_status_filter(self, async_client: AsyncClient, admin_headers, created_product):
        await self._draft(async_client, admin_headers, created_product)
        response = await async_client.get("/v1/products/admin/?status=draft&limit=1000", headers=admin_headers)
        assert {p["product_status"] for p in response.json()["data"]} == {"draft"}

    async def test_requires_admin(self, async_client: AsyncClient, auth_headers):
        assert (await async_client.get("/v1/products/admin/")).status_code == 401
        assert (await async_client.get("/v1/products/admin/", headers=auth_headers)).status_code == 403



@pytest.mark.api
class TestVariantAndImageEndpoints:
    """The admin editor saves each variant and image through its own endpoint."""

    async def test_variant_lifecycle(self, async_client: AsyncClient, admin_headers, created_product):
        pid = created_product["id"]
        created = await async_client.post(f"/v1/products/{pid}/variants/", headers=admin_headers,
                                          json={"name": "2 kg bag", "base_price": 9.5, "sale_price": 8.0, "stock": 12})
        assert created.status_code in (200, 201), created.text
        vid = created.json()["data"]["id"]

        updated = await async_client.patch(f"/v1/products/variants/{vid}/", headers=admin_headers, json={"sale_price": None, "stock": 30})
        assert updated.status_code == 200
        assert updated.json()["data"]["sale_price"] is None
        assert updated.json()["data"]["stock"] == 30

        listed = await async_client.get(f"/v1/products/{pid}/variants/")
        assert vid in [v["id"] for v in listed.json()["data"]]

        deleted = await async_client.delete(f"/v1/products/variants/{vid}/", headers=admin_headers)
        assert deleted.json()["data"]["outcome"] == "deleted"

    async def test_last_variant_is_protected(self, async_client: AsyncClient, admin_headers, created_product):
        only = (await async_client.get(f"/v1/products/{created_product['id']}/variants/")).json()["data"]
        if len(only) == 1:
            response = await async_client.delete(f"/v1/products/variants/{only[0]['id']}/", headers=admin_headers)
            assert response.status_code == 400

    async def test_image_lifecycle(self, async_client: AsyncClient, admin_headers, created_product):
        vid = (await async_client.get(f"/v1/products/{created_product['id']}/variants/")).json()["data"][0]["id"]
        first = await async_client.post(f"/v1/products/variants/{vid}/images/", headers=admin_headers,
                                        json={"url": "https://img.example/1.jpg", "is_primary": True})
        second = await async_client.post(f"/v1/products/variants/{vid}/images/", headers=admin_headers,
                                         json={"url": "https://img.example/2.jpg", "alt_text": "Side"})
        second_id = second.json()["data"]["id"]
        made_primary = await async_client.patch(f"/v1/products/images/{second_id}/", headers=admin_headers, json={"is_primary": True})
        assert made_primary.json()["data"]["is_primary"] is True
        images = (await async_client.get(f"/v1/products/variants/{vid}/images/")).json()["data"]
        assert [i["id"] for i in images if i["is_primary"]] == [second_id]
        await async_client.delete(f"/v1/products/images/{second_id}/", headers=admin_headers)
        remaining = await async_client.get(f"/v1/products/images/{first.json()['data']['id']}/")
        assert remaining.json()["data"]["is_primary"] is True

    async def test_moderation_and_featuring(self, async_client: AsyncClient, admin_headers, created_product):
        pid = created_product["id"]
        rejected = await async_client.patch(f"/v1/products/{pid}/moderate/", headers=admin_headers, json={"status": "rejected", "notes": "Blurry photos"})
        assert rejected.status_code == 200
        assert rejected.json()["data"]["product_status"] == "inactive"
        invalid = await async_client.patch(f"/v1/products/{pid}/moderate/", headers=admin_headers, json={"status": "maybe"})
        assert invalid.status_code == 422
        featured = await async_client.patch(f"/v1/products/{pid}/feature/?featured=true", headers=admin_headers)
        assert featured.json()["data"]["is_featured"] is True

    async def test_product_update_ignores_nested_variants(self, async_client: AsyncClient, admin_headers, created_product):
        before = (await async_client.get(f"/v1/products/{created_product['id']}/variants/")).json()["data"]
        await async_client.patch(f"/v1/products/{created_product['id']}/", headers=admin_headers,
                                 json={"name": "Renamed", "variants": [{"name": "Sneaky", "base_price": 1}]})
        after = (await async_client.get(f"/v1/products/{created_product['id']}/variants/")).json()["data"]
        assert [v["id"] for v in after] == [v["id"] for v in before]
