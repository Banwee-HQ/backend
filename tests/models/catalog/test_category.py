"""Tests for models/catalog/category.py - the Category tree replacing the old free-text field."""

import uuid

from models.catalog.category import Category


def make_category(name: str, slug: str, parent_id=None, is_active=True, sort_order=0) -> Category:
    cat = Category()
    cat.id = uuid.uuid4()
    cat.name = name
    cat.slug = slug
    cat.parent_id = parent_id
    cat.is_active = is_active
    cat.sort_order = sort_order
    cat.description = None
    cat.created_at = None
    cat.updated_at = None
    cat.children = []
    return cat


class TestToDict:

    def test_basic_fields(self):
        cat = make_category("Grains & Pulses", "grains-pulses")
        data = cat.to_dict()
        assert data["name"] == "Grains & Pulses"
        assert data["slug"] == "grains-pulses"
        assert data["id"] == str(cat.id)
        assert data["is_active"] is True
        assert data["parent_id"] is None

    def test_parent_id_is_stringified_when_present(self):
        parent_id = uuid.uuid4()
        cat = make_category("Rice", "rice", parent_id=parent_id)
        assert cat.to_dict()["parent_id"] == str(parent_id)

    def test_children_omitted_by_default(self):
        cat = make_category("Grains", "grains")
        assert "children" not in cat.to_dict()

    def test_children_included_when_requested(self):
        parent = make_category("Grains", "grains")
        child = make_category("Rice", "rice", parent_id=parent.id)
        parent.children = [child]

        data = parent.to_dict(include_children=True)
        assert len(data["children"]) == 1
        assert data["children"][0]["slug"] == "rice"

    def test_nested_children_recurse(self):
        grandparent = make_category("Food", "food")
        parent = make_category("Grains", "grains", parent_id=grandparent.id)
        child = make_category("Rice", "rice", parent_id=parent.id)
        parent.children = [child]
        grandparent.children = [parent]

        data = grandparent.to_dict(include_children=True)
        assert data["children"][0]["children"][0]["slug"] == "rice"
