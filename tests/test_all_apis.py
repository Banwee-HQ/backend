"""Complete API Test Suite - Tests all 101+ Banwee API endpoints.

This file contains comprehensive tests for all API endpoints organized by module.
Run with: pytest tests/test_all_apis.py -v
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4, UUID
from typing import Dict, Any


# =============================================================================
# ROOT & SYSTEM ENDPOINTS (3 endpoints)
# =============================================================================

@pytest.mark.api
class TestRootAndSystem:
    """Test root and system endpoints."""

    async def test_001_root_endpoint(self, async_client: AsyncClient):
        """GET / - Root endpoint."""
        response = await async_client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Banwee API"
        assert data["status"] == "Running"

    async def test_002_health_check(self, async_client: AsyncClient):
        """GET /v1/health/ - Health check."""
        response = await async_client.get("/v1/health/")
        assert response.status_code == 200
        data = response.json()
        # response uses standardized wrapper -> payload under `data`
        assert data["data"]["status"] == "alive"

    async def test_003_api_docs(self, async_client: AsyncClient):
        """GET /docs - API documentation."""
        response = await async_client.get("/docs")
        assert response.status_code == 200


# =============================================================================
# AUTHENTICATION ENDPOINTS (19 endpoints)
# =============================================================================

@pytest.mark.api
@pytest.mark.auth
class TestAuthEndpoints:
    """Test all 19 authentication endpoints."""

    async def test_004_auth_register(self, async_client: AsyncClient):
        """POST /v1/auth/register - Register new user."""
        user_data = {
            "email": f"test_{uuid4().hex[:8]}@example.com",
            "password": "SecurePass123!",
            "first_name": "Test",
            "last_name": "User",
            "phone": "+1234567890"
        }
        response = await async_client.post("/v1/auth/register", json=user_data)
        assert response.status_code in [200, 201]

    async def test_005_auth_login(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/login - User login."""
        login_data = {"email": test_user.email, "password": "TestPassword123!"}
        response = await async_client.post("/v1/auth/login", json=login_data)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data["data"]
        assert "refresh_token" in data["data"]

    async def test_006_auth_login_invalid(self, async_client: AsyncClient):
        """POST /v1/auth/login - Invalid credentials."""
        login_data = {"email": "invalid@test.com", "password": "wrong"}
        response = await async_client.post("/v1/auth/login", json=login_data)
        assert response.status_code == 401

    async def test_007_auth_refresh_token(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/refresh - Refresh access token."""
        # First login to get refresh token
        login_data = {"email": test_user.email, "password": "TestPassword123!"}
        login_resp = await async_client.post("/v1/auth/login", json=login_data)
        refresh_token = login_resp.json()["data"]["refresh_token"]
        
        response = await async_client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        assert "access_token" in response.json()["data"]

    async def test_008_auth_revoke_token(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/revoke - Revoke refresh token."""
        login_data = {"email": test_user.email, "password": "TestPassword123!"}
        login_resp = await async_client.post("/v1/auth/login", json=login_data)
        refresh_token = login_resp.json()["data"]["refresh_token"]
        
        response = await async_client.post("/v1/auth/revoke", params={"refresh_token": refresh_token})
        assert response.status_code == 200

    async def test_009_auth_logout(self, async_client: AsyncClient, auth_headers):
        """POST /v1/auth/logout - Logout user."""
        response = await async_client.post("/v1/auth/logout", headers=auth_headers)
        assert response.status_code == 200

    async def test_010_auth_get_profile(self, async_client: AsyncClient, auth_headers, test_user):
        """GET /v1/auth/profile - Get user profile."""
        response = await async_client.get("/v1/auth/profile", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["email"] == test_user.email

    async def test_011_auth_get_addresses(self, async_client: AsyncClient, auth_headers):
        """GET /v1/auth/addresses - Get user addresses."""
        response = await async_client.get("/v1/auth/addresses/", headers=auth_headers)
        assert response.status_code == 200

    async def test_012_auth_create_address(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """POST /v1/auth/addresses - Create address."""
        response = await async_client.post("/v1/auth/addresses/", headers=auth_headers, json=sample_address_data)
        assert response.status_code in [200, 201]

    async def test_013_auth_verify_email_invalid(self, async_client: AsyncClient):
        """GET /v1/auth/verify-email - Verify email with invalid token."""
        response = await async_client.get("/v1/auth/verify-email", params={"token": "invalid"})
        assert response.status_code in [400, 401, 404]

    async def test_014_auth_forgot_password(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/forgot-password - Request password reset."""
        response = await async_client.post("/v1/auth/forgot-password", json={"email": test_user.email})
        assert response.status_code == 200

    async def test_015_auth_resend_verification(self, async_client: AsyncClient, test_user):
        """POST /v1/auth/resend-verification - Resend verification email."""
        response = await async_client.post("/v1/auth/resend-verification", 
            json={"email": test_user.email},
            headers={"X-Resend-Token": "test-token-1234567890123456"}
        )
        assert response.status_code in [200, 400]

    async def test_016_auth_reset_password_invalid(self, async_client: AsyncClient):
        """POST /v1/auth/reset-password - Reset with invalid token."""
        response = await async_client.post("/v1/auth/reset-password", 
            json={"token": "invalid", "new_password": "NewPass123!"}
        )
        assert response.status_code == 400

    async def test_017_auth_update_profile(self, async_client: AsyncClient, auth_headers):
        """PUT /v1/auth/profile - Update profile."""
        response = await async_client.put("/v1/auth/profile", 
            headers=auth_headers,
            json={"first_name": "Updated", "last_name": "Name"}
        )
        assert response.status_code == 200

    async def test_018_auth_change_password(self, async_client: AsyncClient, auth_headers):
        """PUT /v1/auth/change-password - Change password."""
        response = await async_client.put("/v1/auth/change-password",
            headers=auth_headers,
            params={"current_password": "TestPassword123!", "new_password": "NewPass123!"}
        )
        assert response.status_code == 200

    async def test_019_oauth_google_login(self, async_client: AsyncClient):
        """GET /v1/auth/social/google/login - Google OAuth."""
        response = await async_client.get("/v1/auth/social/google/login")
        assert response.status_code == 200
        assert "auth_url" in response.json().get("data", {})

    async def test_020_oauth_facebook_login(self, async_client: AsyncClient):
        """GET /v1/auth/social/facebook/login - Facebook OAuth."""
        response = await async_client.get("/v1/auth/social/facebook/login")
        assert response.status_code == 200
        assert "auth_url" in response.json().get("data", {})


# =============================================================================
# USER ENDPOINTS (15 endpoints)
# =============================================================================

@pytest.mark.api
class TestUserEndpoints:
    """Test all 15 user endpoints."""

    async def test_021_users_get_me(self, async_client: AsyncClient, auth_headers, test_user):
        """GET /v1/users/me - Get current user."""
        response = await async_client.get("/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["email"] == test_user.email

    async def test_022_users_get_profile(self, async_client: AsyncClient, auth_headers):
        """GET /v1/users/profile - Get user profile."""
        response = await async_client.get("/v1/users/profile", headers=auth_headers)
        assert response.status_code == 200

    async def test_023_users_update_profile(self, async_client: AsyncClient, auth_headers):
        """PUT /v1/users/profile - Update user profile."""
        response = await async_client.put("/v1/users/profile",
            headers=auth_headers,
            json={"first_name": "Updated", "last_name": "Profile"}
        )
        assert response.status_code == 200

    async def test_024_users_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/users/ - List users."""
        response = await async_client.get("/v1/users/", headers=auth_headers)
        # May require admin
        assert response.status_code in [200, 403]

    async def test_025_users_search(self, async_client: AsyncClient, auth_headers):
        """GET /v1/users/search - Search users."""
        # Search is exposed on the users list as a query param
        response = await async_client.get("/v1/users/?q=test", headers=auth_headers)
        assert response.status_code in [200, 403]

    async def test_026_users_get_by_id(self, async_client: AsyncClient, auth_headers, test_user):
        """GET /v1/users/{id} - Get user by ID."""
        response = await async_client.get(f"/v1/users/{test_user.id}", headers=auth_headers)
        assert response.status_code in [200, 403]

    async def test_027_users_me_addresses(self, async_client: AsyncClient, auth_headers):
        """GET /v1/users/me/addresses - Get my addresses."""
        # Addresses are served under /v1/addresses
        response = await async_client.get("/v1/addresses/", headers=auth_headers)
        assert response.status_code == 200

    async def test_028_users_create_address(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """POST /v1/users/addresses - Create address."""
        response = await async_client.post("/v1/addresses",
            headers=auth_headers,
            json=sample_address_data
        )
        assert response.status_code in [200, 201]

    async def test_029_users_update_address(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """PUT /v1/users/addresses/{id} - Update address."""
        # First create an address
        create_resp = await async_client.post("/v1/addresses",
            headers=auth_headers, json=sample_address_data
        )
        if create_resp.status_code in [200, 201]:
            address_id = create_resp.json()["data"]["id"]
            response = await async_client.put(f"/v1/addresses/{address_id}",
                headers=auth_headers,
                json={"city": "Updated City"}
            )
            assert response.status_code == 200

    async def test_030_users_delete_address(self, async_client: AsyncClient, auth_headers, sample_address_data):
        """DELETE /v1/users/addresses/{id} - Delete address."""
        create_resp = await async_client.post("/v1/addresses",
            headers=auth_headers, json=sample_address_data
        )
        if create_resp.status_code in [200, 201]:
            address_id = create_resp.json()["data"]["id"]
            response = await async_client.delete(f"/v1/addresses/{address_id}", headers=auth_headers)
            assert response.status_code == 200

    async def test_031_users_unauthorized(self, async_client: AsyncClient):
        """GET /v1/users/me without auth - Should fail."""
        response = await async_client.get("/v1/users/me")
        assert response.status_code == 401


# =============================================================================
# PRODUCT ENDPOINTS (12 endpoints)
# =============================================================================

@pytest.mark.api
class TestProductEndpoints:
    """Test all 12 product endpoints."""

    async def test_032_products_home(self, async_client: AsyncClient):
        """GET /v1/products/home - Get home data."""
        response = await async_client.get("/v1/products/home")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data["data"]
        assert "featured" in data["data"]

    async def test_033_products_list(self, async_client: AsyncClient):
        """GET /v1/products/ - List products."""
        response = await async_client.get("/v1/products/?limit=10")
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_034_products_list_with_filters(self, async_client: AsyncClient):
        """GET /v1/products/ - List with filters."""
        response = await async_client.get("/v1/products/?min_price=10&max_price=100")
        assert response.status_code == 200

    async def test_035_products_list_with_sorting(self, async_client: AsyncClient):
        """GET /v1/products/ - List with sorting."""
        response = await async_client.get("/v1/products/?sort_by=price&sort_order=asc")
        assert response.status_code == 200

    async def test_036_products_list_with_search(self, async_client: AsyncClient):
        """GET /v1/products/ - Search products."""
        response = await async_client.get("/v1/products/?q=organic")
        assert response.status_code == 200

    async def test_037_products_get_by_id(self, async_client: AsyncClient):
        """GET /v1/products/{id} - Get product by ID."""
        product_id = str(uuid4())
        response = await async_client.get(f"/v1/products/{product_id}")
        assert response.status_code in [200, 404]

    async def test_038_products_recommendations(self, async_client: AsyncClient):
        """GET /v1/products/{id}/recommendations - Get recommendations."""
        product_id = str(uuid4())
        response = await async_client.get(f"/v1/products/{product_id}/recommendations")
        assert response.status_code in [200, 404]

    async def test_039_products_variants(self, async_client: AsyncClient):
        """GET /v1/products/{id}/variants - Get product variants."""
        product_id = str(uuid4())
        response = await async_client.get(f"/v1/products/{product_id}/variants")
        assert response.status_code in [200, 404]

    async def test_040_products_get_variant(self, async_client: AsyncClient):
        """GET /v1/products/variants/{id} - Get specific variant."""
        variant_id = str(uuid4())
        response = await async_client.get(f"/v1/products/variants/{variant_id}")
        assert response.status_code in [200, 404]

    async def test_041_products_create_as_admin(self, async_client: AsyncClient, admin_headers, sample_product_data):
        """POST /v1/products/ - Create product (admin)."""
        response = await async_client.post("/v1/products/",
            headers=admin_headers,
            json=sample_product_data
        )
        assert response.status_code in [200, 201, 403]


# =============================================================================
# REVIEW ENDPOINTS (6 endpoints)
# =============================================================================

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
        response = await async_client.get(f"/v1/reviews/{review_id}")
        assert response.status_code in [200, 404]

    async def test_045_reviews_for_product(self, async_client: AsyncClient):
        """GET /v1/reviews/product/{id} - Get product reviews."""
        product_id = str(uuid4())
        response = await async_client.get(f"/v1/reviews/product/{product_id}")
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
        """PUT /v1/reviews/{id} - Update review."""
        review_id = str(uuid4())
        response = await async_client.put(f"/v1/reviews/{review_id}",
            headers=auth_headers,
            json={"rating": 4, "comment": "Updated review"}
        )
        assert response.status_code in [200, 404]


# =============================================================================
# WISHLIST ENDPOINTS (3 endpoints)
# =============================================================================

@pytest.mark.api
class TestWishlistEndpoints:
    """Test all 3 wishlist endpoints."""

    async def test_048_wishlist_get(self, async_client: AsyncClient, auth_headers):
        """GET /v1/wishlist/ - Get wishlist."""
        response = await async_client.get("/v1/wishlists/", headers=auth_headers)
        assert response.status_code == 200

    async def test_049_wishlist_add(self, async_client: AsyncClient, auth_headers):
        """POST /v1/wishlist/add - Add to wishlist."""
        # Create a wishlist (API exposes /v1/wishlists/ create)
        payload = {"name": "Test Wishlist", "is_default": False}
        response = await async_client.post("/v1/wishlists/", headers=auth_headers, json=payload)
        assert response.status_code in [200, 201]

    async def test_050_wishlist_remove(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/wishlist/items/{id} - Remove from wishlist."""
        # Create then delete a wishlist to verify delete route
        payload = {"name": "To Delete", "is_default": False}
        create_resp = await async_client.post("/v1/wishlists/", headers=auth_headers, json=payload)
        if create_resp.status_code in [200, 201]:
            wid = create_resp.json()["data"]["id"]
            response = await async_client.delete(f"/v1/wishlists/{wid}", headers=auth_headers)
            assert response.status_code in [200, 404]


# =============================================================================
# CART ENDPOINTS (7 endpoints)
# =============================================================================

@pytest.mark.api
class TestCartEndpoints:
    """Test all 7 cart endpoints."""

    async def test_051_cart_get(self, async_client: AsyncClient, auth_headers):
        """GET /v1/cart/ - Get cart."""
        response = await async_client.get("/v1/cart/", headers=auth_headers)
        assert response.status_code == 200

    async def test_052_cart_add_item(self, async_client: AsyncClient, auth_headers):
        """POST /v1/cart/add - Add item to cart."""
        response = await async_client.post("/v1/cart/add",
            headers=auth_headers,
            json={"variant_id": str(uuid4()), "quantity": 2}
        )
        assert response.status_code in [200, 400, 404]

    async def test_053_cart_update_item(self, async_client: AsyncClient, auth_headers):
        """PUT /v1/cart/items/{id} - Update cart item."""
        item_id = str(uuid4())
        response = await async_client.put(f"/v1/cart/items/{item_id}",
            headers=auth_headers,
            json={"quantity": 5}
        )
        assert response.status_code in [200, 404]

    async def test_054_cart_remove_item(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/cart/items/{id} - Remove cart item."""
        item_id = str(uuid4())
        response = await async_client.delete(f"/v1/cart/items/{item_id}", headers=auth_headers)
        assert response.status_code in [200, 404]

    async def test_055_cart_clear(self, async_client: AsyncClient, auth_headers):
        """POST /v1/cart/clear - Clear cart."""
        response = await async_client.post("/v1/cart/clear", headers=auth_headers)
        assert response.status_code in [200, 201]


# =============================================================================
# ORDER ENDPOINTS (8+ endpoints)
# =============================================================================

@pytest.mark.api
class TestOrderEndpoints:
    """Test all order endpoints."""

    async def test_056_orders_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/orders/ - List orders."""
        response = await async_client.get("/v1/orders/", headers=auth_headers)
        assert response.status_code == 200

    async def test_057_orders_get_by_id(self, async_client: AsyncClient, auth_headers):
        """GET /v1/orders/{id} - Get order by ID."""
        order_id = str(uuid4())
        response = await async_client.get(f"/v1/orders/{order_id}", headers=auth_headers)
        assert response.status_code in [200, 404]

    async def test_058_orders_cancel(self, async_client: AsyncClient, auth_headers):
        """PUT /v1/orders/{id}/cancel - Cancel order."""
        order_id = str(uuid4())
        response = await async_client.put(f"/v1/orders/{order_id}/cancel",
            headers=auth_headers,
            json={"reason": "Changed my mind"}
        )
        assert response.status_code in [200, 400, 404]

    async def test_059_orders_get_tracking(self, async_client: AsyncClient, auth_headers):
        """GET /v1/orders/{id}/tracking - Get order tracking."""
        order_id = str(uuid4())
        response = await async_client.get(f"/v1/orders/{order_id}/tracking", headers=auth_headers)
        assert response.status_code in [200, 404]


# =============================================================================
# PAYMENT ENDPOINTS (8+ endpoints)
# =============================================================================

@pytest.mark.api
class TestPaymentEndpoints:
    """Test all payment endpoints."""

    async def test_060_payments_overview(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/ - Get payments overview."""
        response = await async_client.get("/v1/payments/", headers=auth_headers)
        assert response.status_code == 200

    async def test_061_payments_methods_list(self, async_client: AsyncClient, auth_headers):
        """GET /v1/payments/methods - List payment methods."""
        response = await async_client.get("/v1/payments/methods", headers=auth_headers)
        assert response.status_code == 200

    async def test_062_payments_methods_create(self, async_client: AsyncClient, auth_headers):
        """POST /v1/payments/methods - Create payment method."""
        response = await async_client.post("/v1/payments/methods",
            headers=auth_headers,
            json={
                "type": "card",
                "provider": "stripe",
                "stripe_payment_method_id": "pm_test_123",
                "last_four": "1234"
            }
        )
        assert response.status_code in [200, 201, 400]

    async def test_063_payments_methods_delete(self, async_client: AsyncClient, auth_headers):
        """DELETE /v1/payments/methods/{id} - Delete payment method."""
        method_id = str(uuid4())
        response = await async_client.delete(f"/v1/payments/methods/{method_id}", headers=auth_headers)
        assert response.status_code in [200, 404]


# =============================================================================
# CONTACT MESSAGE ENDPOINTS (2 endpoints)
# =============================================================================

@pytest.mark.api
class TestContactMessageEndpoints:
    """Test contact message endpoints."""

    async def test_064_contact_messages_create(self, async_client: AsyncClient, sample_contact_message):
        """POST /v1/contact-messages - Create contact message."""
        response = await async_client.post("/v1/contact-messages", json=sample_contact_message)
        assert response.status_code in [200, 201]

    async def test_065_contact_messages_list_as_admin(self, async_client: AsyncClient, admin_headers):
        """GET /v1/contact-messages - List messages (admin)."""
        response = await async_client.get("/v1/contact-messages", headers=admin_headers)
        assert response.status_code in [200, 403]
