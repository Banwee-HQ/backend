"""Tests for schemas/catalog/category.py - self-referential TreeResponse."""

import pytest
from pydantic import ValidationError

from schemas.catalog.category import Create, TreeResponse


class TestCreate:

    def test_requires_name_and_slug(self):
        with pytest.raises(ValidationError):
            Create(name="Snacks")

    def test_defaults_is_active_true(self):
        category = Create(name="Snacks", slug="snacks")
        assert category.is_active is True


class TestTreeResponseNesting:

    def test_supports_nested_children(self):
        from uuid import uuid4
        from datetime import datetime
        child = TreeResponse(id=uuid4(), name="Chips", slug="chips", is_active=True, sort_order=0, created_at=datetime.now())
        parent = TreeResponse(id=uuid4(), name="Snacks", slug="snacks", is_active=True, sort_order=0, created_at=datetime.now(), children=[child])
        assert parent.children[0].name == "Chips"
