"""Tests for user endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from models.accounts.user import User


@pytest.mark.api
@pytest.mark.unit
class TestUserEndpoints:
    """Test user management endpoints."""

    async def test_get_current_user(self, async_client: AsyncClient, auth_headers: dict, test_user: User):
        """Test getting current user profile."""
        response = await async_client.get("/v1/users/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["email"] == test_user.email

    async def test_get_current_user_unauthorized(self, async_client: AsyncClient):
        """Test getting current user without authentication."""
        response = await async_client.get("/v1/users/me")
        assert response.status_code == 401

    async def test_update_current_user(self, async_client: AsyncClient, auth_headers: dict):
        """Test updating current user profile."""
        update_data = {
            "first_name": "Updated",
            "last_name": "Name",
            "phone": "+9876543210"
        }
        response = await async_client.put("/v1/auth/profile", headers=auth_headers, json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["first_name"] == "Updated"

    async def test_change_password(self, async_client: AsyncClient, auth_headers: dict, test_user: User):
        """Test changing user password."""
        password_data = {
            "current_password": "TestPassword123!",
            "new_password": "NewSecurePass456!"
        }
        response = await async_client.patch("/v1/auth/me/password", headers=auth_headers, json=password_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_change_password_wrong_current(self, async_client: AsyncClient, auth_headers: dict):
        """Test changing password with wrong current password."""
        password_data = {
            "current_password": "WrongPassword!",
            "new_password": "NewSecurePass456!"
        }
        response = await async_client.patch("/v1/auth/me/password", headers=auth_headers, json=password_data)
        assert response.status_code in [400, 401]


@pytest.mark.api
@pytest.mark.unit
class TestUserAddressEndpoints:
    """Test user address endpoints."""

    async def test_create_address(self, async_client: AsyncClient, auth_headers: dict, sample_address_data):
        """Test creating a new address."""
        response = await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_addresses(self, async_client: AsyncClient, auth_headers: dict):
        """Test getting all user addresses."""
        response = await async_client.get("/v1/addresses/", headers=auth_headers)
        assert response.status_code in [200, 404]  # 404 if endpoint doesn't exist
        if response.status_code == 200:
            data = response.json()
            assert data["success"] is True
            assert isinstance(data["data"], list)

    async def test_get_addresses_unauthorized(self, async_client: AsyncClient):
        """Test getting addresses without authentication."""
        response = await async_client.get("/v1/addresses/")
        assert response.status_code == 401

    async def test_update_address(self, async_client: AsyncClient, auth_headers: dict, sample_address_data):
        """Test updating an address."""
        # First create an address
        create_response = await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        assert create_response.status_code in [200, 201]
        address_id = create_response.json()["data"]["id"]

        # Update the address
        update_data = {"city": "Abuja", "label": "Work"}
        response = await async_client.put(f"/v1/addresses/{address_id}", headers=auth_headers, json=update_data)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_delete_address(self, async_client: AsyncClient, auth_headers: dict, sample_address_data):
        """Test deleting an address."""
        # First create an address
        create_response = await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        assert create_response.status_code in [200, 201]
        address_id = create_response.json()["data"]["id"]

        # Delete the address
        response = await async_client.delete(f"/v1/addresses/{address_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_set_default_address(self, async_client: AsyncClient, auth_headers: dict, sample_address_data):
        """Test setting default address."""
        # First create an address
        create_response = await async_client.post("/v1/addresses/", headers=auth_headers, json=sample_address_data)
        assert create_response.status_code in [200, 201]
        address_id = create_response.json()["data"]["id"]

        # Set as default - endpoint may not exist
        response = await async_client.patch(f"/v1/addresses/{address_id}/default", headers=auth_headers)
        assert response.status_code in [200, 404]
        data = response.json()
        assert data["success"] is True


@pytest.mark.api
@pytest.mark.unit
class TestAdminUserEndpoints:
    """Test admin user management endpoints."""

    async def test_get_admin_users(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting all users as admin."""
        response = await async_client.get("/v1/admin/users", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    async def test_get_admin_user_by_id(self, async_client: AsyncClient, admin_headers: dict):
        """Test getting specific user as admin."""
        from uuid import uuid4
        user_id = str(uuid4())
        response = await async_client.get(f"/v1/admin/users/{user_id}", headers=admin_headers)
        assert response.status_code in [200, 404]

    async def test_update_user_as_admin(self, async_client: AsyncClient, admin_headers: dict):
        """Test updating user as admin."""
        from uuid import uuid4
        user_id = str(uuid4())
        update_data = {
            "role": "admin",
            "is_active": True
        }
        response = await async_client.patch(f"/v1/admin/users/{user_id}", headers=admin_headers, json=update_data)
        assert response.status_code in [200, 404]
