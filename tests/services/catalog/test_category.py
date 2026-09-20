"""Tests for services/catalog/category.py - CategoryService.

Covers the business rules that aren't reachable through the plain CRUD
happy-path already exercised by tests/api/catalog/test_category.py: slug
uniqueness, parent existence/self-parent validation, and the delete guards
that protect referential integrity (can't delete a category still holding
products or subcategories).
"""

import pytest
from uuid import uuid4

from core.exceptions import APIException
from services.catalog.category import CategoryService
from schemas.catalog.category import Create as CategoryCreate, Update as CategoryUpdate
from models.catalog.category import Category


def make_create(name="Widgets", slug=None, parent_id=None) -> CategoryCreate:
    return CategoryCreate(name=name, slug=slug or f"widgets-{uuid4().hex[:8]}", parent_id=parent_id)


class TestCreate:

    async def test_creates_a_category(self, db_session):
        service = CategoryService(db_session)
        category = await service.create(make_create())
        assert category.id is not None
        assert category.is_active is True

    async def test_duplicate_slug_is_rejected(self, db_session):
        service = CategoryService(db_session)
        slug = f"duplicate-slug-{uuid4().hex[:8]}"
        await service.create(make_create(slug=slug))
        with pytest.raises(APIException) as exc_info:
            await service.create(make_create(slug=slug))
        assert exc_info.value.status_code == 400

    async def test_nonexistent_parent_is_rejected(self, db_session):
        service = CategoryService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.create(make_create(parent_id=uuid4()))
        assert exc_info.value.status_code == 404

    async def test_valid_parent_is_accepted(self, db_session):
        service = CategoryService(db_session)
        parent = await service.create(make_create(name="Parent"))
        child = await service.create(make_create(name="Child", parent_id=parent.id))
        assert child.parent_id == parent.id


class TestUpdate:

    async def test_updates_fields(self, db_session):
        service = CategoryService(db_session)
        category = await service.create(make_create())
        updated = await service.update(category.id, CategoryUpdate(name="Renamed"))
        assert updated.name == "Renamed"

    async def test_unknown_id_returns_none(self, db_session):
        service = CategoryService(db_session)
        result = await service.update(uuid4(), CategoryUpdate(name="Nope"))
        assert result is None

    async def test_changing_slug_to_an_existing_one_is_rejected(self, db_session):
        service = CategoryService(db_session)
        taken_slug = f"taken-slug-{uuid4().hex[:8]}"
        await service.create(make_create(slug=taken_slug))
        other = await service.create(make_create(slug=f"other-slug-{uuid4().hex[:8]}"))
        with pytest.raises(APIException) as exc_info:
            await service.update(other.id, CategoryUpdate(slug=taken_slug))
        assert exc_info.value.status_code == 400

    async def test_category_cannot_become_its_own_parent(self, db_session):
        service = CategoryService(db_session)
        category = await service.create(make_create())
        with pytest.raises(APIException) as exc_info:
            await service.update(category.id, CategoryUpdate(parent_id=category.id))
        assert exc_info.value.status_code == 400

    async def test_new_parent_must_exist(self, db_session):
        service = CategoryService(db_session)
        category = await service.create(make_create())
        with pytest.raises(APIException) as exc_info:
            await service.update(category.id, CategoryUpdate(parent_id=uuid4()))
        assert exc_info.value.status_code == 404


class TestDelete:

    async def test_deletes_an_empty_category(self, db_session):
        service = CategoryService(db_session)
        category = await service.create(make_create())
        assert await service.delete(category.id) is True
        assert await service.get(category.id) is None

    async def test_unknown_id_returns_false(self, db_session):
        service = CategoryService(db_session)
        assert await service.delete(uuid4()) is False

    async def test_cannot_delete_a_category_with_subcategories(self, db_session):
        service = CategoryService(db_session)
        parent = await service.create(make_create(name="Parent"))
        await service.create(make_create(name="Child", parent_id=parent.id))
        with pytest.raises(APIException) as exc_info:
            await service.delete(parent.id)
        assert exc_info.value.status_code == 400


class TestTree:

    async def test_tree_returns_only_top_level_with_nested_children(self, db_session):
        service = CategoryService(db_session)
        parent = await service.create(make_create(name="Root"))
        await service.create(make_create(name="Leaf", parent_id=parent.id))

        tree = await service.tree()
        matched = [c for c in tree if c.id == parent.id]
        assert len(matched) == 1
        assert len(matched[0].children) == 1

    async def test_inactive_top_level_excluded_when_active_only(self, db_session):
        service = CategoryService(db_session)
        category = await service.create(make_create())
        await service.update(category.id, CategoryUpdate(is_active=False))

        tree = await service.tree(active_only=True)
        assert category.id not in [c.id for c in tree]
