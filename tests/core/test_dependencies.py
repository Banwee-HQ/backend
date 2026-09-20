"""Tests for core/dependencies.py - the shared auth dependencies used by every protected route.

require_admin used to crash with an unhandled AttributeError (-> 500) for anonymous
requests instead of a clean 401, because it read `current_user.role` before checking
`current_user is None`. These tests pin that fix down.
"""

import pytest
from types import SimpleNamespace

from core.dependencies import require_admin, require_auth
from core.exceptions import APIException


def make_user(role: str):
    return SimpleNamespace(role=role)


class TestRequireAdmin:

    def test_anonymous_request_raises_401_not_500(self):
        """The regression this file exists to guard against."""
        with pytest.raises(APIException) as exc_info:
            require_admin(current_user=None)
        assert exc_info.value.status_code == 401

    def test_admin_role_is_allowed(self):
        user = make_user("admin")
        assert require_admin(current_user=user) is user

    def test_manager_role_is_allowed(self):
        user = make_user("manager")
        assert require_admin(current_user=user) is user

    def test_customer_role_is_rejected_with_403(self):
        with pytest.raises(APIException) as exc_info:
            require_admin(current_user=make_user("customer"))
        assert exc_info.value.status_code == 403

    def test_role_check_is_case_insensitive(self):
        """Roles come back from the DB as plain strings - don't assume casing."""
        user = make_user("ADMIN")
        assert require_admin(current_user=user) is user

    def test_guest_role_is_rejected(self):
        with pytest.raises(APIException) as exc_info:
            require_admin(current_user=make_user("guest"))
        assert exc_info.value.status_code == 403


class TestRequireAuth:

    async def test_anonymous_raises_401(self):
        with pytest.raises(APIException) as exc_info:
            await require_auth(current_user=None)
        assert exc_info.value.status_code == 401

    async def test_authenticated_user_passes_through(self):
        user = make_user("customer")
        assert await require_auth(current_user=user) is user
