"""Tests for services/accounts/address.py - AddressService.

Note: update()'s scoped WHERE clause (id + user_id) means updating another
user's address silently affects zero rows and still returns the (unchanged)
address via get() - the API layer (api/accounts/addresses.py) guards against
this by checking ownership before calling update(), so this is documented
here rather than treated as a bug to fix in the service itself.
"""

import pytest
from uuid import uuid4

from services.accounts.address import AddressService
from services.accounts.auth import AuthService
from models.accounts.user import User, UserRole


async def make_user(db_session) -> User:
    auth = AuthService(db_session)
    user = User(
        id=uuid4(),
        email=f"address_test_{uuid4().hex[:8]}@example.com",
        firstname="Test",
        lastname="User",
        hashed_password=auth.get_password_hash("Password123!"),
        role=UserRole.CUSTOMER,
        account_status="active",
        verification_status="verified",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestCreate:

    async def test_creates_an_address(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        address = await service.create(user.id, street="123 Main St", city="Springfield", country="US")
        assert address.street == "123 Main St"
        assert address.user_id == user.id

    async def test_missing_fields_default_to_empty_string(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        address = await service.create(user.id)
        assert address.street == ""
        assert address.city == ""


class TestGet:

    async def test_gets_by_id(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        created = await service.create(user.id, street="1 St")
        found = await service.get(created.id)
        assert found.id == created.id

    async def test_unknown_id_returns_none(self, db_session):
        service = AddressService(db_session)
        assert await service.get(uuid4()) is None


class TestList:

    async def test_lists_only_the_given_users_addresses(self, db_session):
        user = await make_user(db_session)
        other = await make_user(db_session)
        service = AddressService(db_session)
        await service.create(user.id, street="Mine")
        await service.create(other.id, street="Theirs")

        result = await service.list(user.id)
        assert result["pagination"]["total"] == 1
        assert result["data"][0].street == "Mine"

    async def test_search_filters_by_city(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        marker = uuid4().hex[:8]
        await service.create(user.id, city=f"Findville{marker}")
        await service.create(user.id, city="Elsewhere")

        result = await service.list(user.id, search=f"findville{marker}")
        assert result["pagination"]["total"] == 1

    async def test_pagination(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        for i in range(3):
            await service.create(user.id, street=f"St {i}")

        page1 = await service.list(user.id, page=1, limit=2)
        assert len(page1["data"]) == 2
        assert page1["pagination"]["total"] == 3

        page2 = await service.list(user.id, page=2, limit=2)
        assert len(page2["data"]) == 1


class TestUpdate:

    async def test_updates_fields_for_the_owner(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        created = await service.create(user.id, street="Old")
        updated = await service.update(created.id, user.id, street="New")
        assert updated.street == "New"

    async def test_update_by_non_owner_changes_nothing(self, db_session):
        user = await make_user(db_session)
        other = await make_user(db_session)
        service = AddressService(db_session)
        created = await service.create(user.id, street="Original")

        result = await service.update(created.id, other.id, street="Hijacked")
        assert result.street == "Original"


class TestDelete:

    async def test_owner_can_delete(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        created = await service.create(user.id)
        assert await service.delete(created.id, user.id) is True
        assert await service.get(created.id) is None

    async def test_non_owner_delete_returns_false_and_keeps_address(self, db_session):
        user = await make_user(db_session)
        other = await make_user(db_session)
        service = AddressService(db_session)
        created = await service.create(user.id)

        assert await service.delete(created.id, other.id) is False
        assert await service.get(created.id) is not None

    async def test_delete_without_user_id_scoping(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        created = await service.create(user.id)
        assert await service.delete(created.id) is True

    async def test_unknown_id_returns_false(self, db_session):
        service = AddressService(db_session)
        assert await service.delete(uuid4()) is False


class TestDefault:

    async def test_returns_the_oldest_address(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        first = await service.create(user.id, street="First")
        await service.create(user.id, street="Second")

        default = await service.default(user.id)
        assert default.id == first.id

    async def test_no_addresses_returns_none(self, db_session):
        user = await make_user(db_session)
        service = AddressService(db_session)
        assert await service.default(user.id) is None
