"""Tests for core/dependencies.py - the shared auth dependencies used by every protected route.

require_admin used to crash with an unhandled AttributeError (-> 500) for anonymous
requests instead of a clean 401, because it read `current_user.role` before checking
`current_user is None`. These tests pin that fix down.
"""

import pytest
from types import SimpleNamespace
from fastapi import HTTPException

from core.dependencies import require_admin, require_auth, get_current_auth_user
from core.exceptions import APIException
from services.accounts.auth import AuthService


def make_user(role: str):
    return SimpleNamespace(role=role)


class TestGetCurrentAuthUser:
    """No token at all is the majority path (covered implicitly by every
    unauthenticated-request test elsewhere); these focus on the two error
    branches, which nothing else in this suite reaches since every real request
    either has no token or a token AuthService accepts cleanly."""

    async def test_no_token_returns_none_without_touching_auth_service(self, mocker):
        mock_current_user = mocker.patch.object(AuthService, "current_user")
        result = await get_current_auth_user(token=None, db=mocker.Mock())
        assert result is None
        mock_current_user.assert_not_called()

    async def test_expired_or_invalid_token_returns_none(self, mocker):
        """AuthService.current_user raises HTTPException(401) for a bad token -
        that's an expected, everyday case and must resolve to "not authenticated",
        not blow up the request."""
        mocker.patch.object(AuthService, "current_user", side_effect=HTTPException(status_code=401, detail="expired"))
        result = await get_current_auth_user(token="some-token", db=mocker.Mock())
        assert result is None

    async def test_unexpected_failure_is_logged_and_treated_as_unauthenticated(self, mocker):
        """A genuine bug or DB error resolving the user must not be silently
        confused with "no token provided" - it's logged, but still resolves to
        None rather than crashing every route that depends on this."""
        mock_logger = mocker.patch("core.dependencies.logger")
        mocker.patch.object(AuthService, "current_user", side_effect=RuntimeError("db exploded"))
        result = await get_current_auth_user(token="some-token", db=mocker.Mock())
        assert result is None
        mock_logger.error.assert_called_once()


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
