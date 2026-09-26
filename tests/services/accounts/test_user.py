"""Tests for services/accounts/user.py - UserService.

reset_password/deactivate/activate previously raised NameError on the
"user not found" path (HTTPException was used but never imported in this
module) - the API layer's blanket except-Exception masked it as a 500
instead of the intended 404. Fixed to use the already-imported APIException;
the not-found tests below are the regression coverage for that.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi import BackgroundTasks

from core.exceptions import APIException
from services.accounts.user import UserService
from services.accounts.auth import AuthService
from schemas.accounts.user import Create as UserCreate, Update as UserUpdate
from models.accounts.user import User, UserRole, AccountStatus, VerificationStatus


async def make_user(db_session, **overrides) -> User:
    auth = AuthService(db_session)
    fields = {
        "id": uuid4(),
        "email": f"user_test_{uuid4().hex[:8]}@example.com",
        "firstname": "Test",
        "lastname": "User",
        "hashed_password": auth.get_password_hash("Password123!"),
        "role": UserRole.CUSTOMER,
        "account_status": "active",
        "verification_status": "verified",
    }
    fields.update(overrides)
    user = User(**fields)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestCreate:

    async def test_creates_a_user_with_hashed_password(self, db_session):
        service = UserService(db_session)
        data = UserCreate(email=f"new_{uuid4().hex[:8]}@example.com", firstname="A", lastname="B", password="Secret123!")
        user = await service.create(data, BackgroundTasks())
        assert user.id is not None
        assert user.hashed_password != "Secret123!"
        assert user.verification_token is not None


class TestVerify:

    async def test_valid_token_marks_user_verified(self, db_session):
        token = f"tok-{uuid4().hex}"
        user = await make_user(db_session, verification_status="pending",
                                verification_token=token, token_expiration=datetime.now(timezone.utc) + timedelta(hours=1))
        service = UserService(db_session)
        await service.verify(token)
        await db_session.refresh(user)
        assert user.verification_status == "verified"
        assert user.verification_token is None

    async def test_unknown_token_is_rejected(self, db_session):
        service = UserService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.verify(f"no-such-token-{uuid4().hex}")
        assert exc_info.value.status_code == 400

    async def test_expired_token_is_rejected(self, db_session):
        token = f"tok-expired-{uuid4().hex}"
        await make_user(db_session, verification_status="pending",
                         verification_token=token, token_expiration=datetime.now(timezone.utc) - timedelta(hours=1))
        service = UserService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.verify(token)
        assert exc_info.value.status_code == 400


class TestGet:

    async def test_gets_by_id(self, db_session):
        user = await make_user(db_session)
        service = UserService(db_session)
        found = await service.get(user.id)
        assert found.id == user.id

    async def test_unknown_id_returns_none(self, db_session):
        service = UserService(db_session)
        assert await service.get(uuid4()) is None


class TestUpdate:

    async def test_updates_from_pydantic_model(self, db_session):
        user = await make_user(db_session)
        service = UserService(db_session)
        updated = await service.update(user.id, UserUpdate(firstname="Renamed"))
        assert updated.firstname == "Renamed"

    async def test_updates_from_plain_dict(self, db_session):
        user = await make_user(db_session)
        service = UserService(db_session)
        updated = await service.update(user.id, {"firstname": "FromDict"})
        assert updated.firstname == "FromDict"

    async def test_allowed_fields_restricts_which_fields_apply(self, db_session):
        user = await make_user(db_session)
        service = UserService(db_session)
        updated = await service.update(user.id, {"firstname": "Blocked", "lastname": "Allowed"}, allowed_fields=["lastname"])
        assert updated.firstname == user.firstname
        assert updated.lastname == "Allowed"

    async def test_unknown_id_returns_none(self, db_session):
        service = UserService(db_session)
        result = await service.update(uuid4(), {"firstname": "Nope"})
        assert result is None


class TestList:

    async def test_lists_with_pagination_envelope(self, db_session):
        await make_user(db_session)
        service = UserService(db_session)
        result = await service.list(page=1, limit=5)
        assert "users" in result
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["limit"] == 5

    async def test_filters_by_role(self, db_session):
        marker = uuid4().hex[:8]
        await make_user(db_session, role=UserRole.CUSTOMER, firstname=f"RoleTest{marker}")
        service = UserService(db_session)
        result = await service.list(role=UserRole.CUSTOMER.value, query=f"RoleTest{marker}")
        assert result["pagination"]["total"] == 1

    async def test_filters_by_account_status(self, db_session):
        marker = uuid4().hex[:8]
        await make_user(db_session, account_status="inactive", firstname=f"StatusTest{marker}")
        service = UserService(db_session)
        result = await service.list(status="inactive", query=f"StatusTest{marker}")
        assert result["pagination"]["total"] == 1

    async def test_filters_by_verification_status(self, db_session):
        marker = uuid4().hex[:8]
        await make_user(db_session, verification_status="pending", firstname=f"VerifyTest{marker}")
        service = UserService(db_session)
        result = await service.list(status="pending", query=f"VerifyTest{marker}")
        assert result["pagination"]["total"] == 1

    async def test_search_query_matches_email(self, db_session):
        user = await make_user(db_session)
        service = UserService(db_session)
        result = await service.list(query=user.email)
        assert result["pagination"]["total"] == 1


class TestSearch:

    async def test_short_query_returns_empty(self, db_session):
        service = UserService(db_session)
        assert await service.search("a") == []
        assert await service.search("") == []

    async def test_finds_active_user_by_partial_name(self, db_session):
        marker = uuid4().hex[:8]
        user = await make_user(db_session, firstname=f"Findme{marker}")
        service = UserService(db_session)
        results = await service.search(f"findme{marker}")
        assert any(r["id"] == str(user.id) for r in results)

    async def test_simple_fallback_finds_active_user(self, db_session):
        marker = uuid4().hex[:8]
        user = await make_user(db_session, firstname=f"Fallback{marker}")
        service = UserService(db_session)
        results = await service._search_simple(f"fallback{marker}".lower(), limit=20)
        assert any(r["id"] == str(user.id) for r in results)

    async def test_role_filter_excludes_other_roles(self, db_session):
        marker = uuid4().hex[:8]
        await make_user(db_session, firstname=f"Roled{marker}", role=UserRole.CUSTOMER)
        service = UserService(db_session)
        results = await service._search_simple(f"roled{marker}".lower(), limit=20, role_filter=UserRole.ADMIN.value)
        assert results == []

    async def test_search_with_role_filter_falls_back_cleanly(self, db_session):
        """search() -> _search_with_similarity(role_filter=...) builds its role_filter SQL
        fragment (base_conditions.append(...)) before the pg_trgm-dependent query runs;
        this DB has no pg_trgm extension installed (verified via pg_extension), so the
        query itself always fails and search() falls back to _search_simple - but the
        role_filter branch inside _search_with_similarity must still run first."""
        marker = uuid4().hex[:8]
        await make_user(db_session, firstname=f"RoleSearch{marker}", role=UserRole.CUSTOMER)
        service = UserService(db_session)
        results = await service.search(f"rolesearch{marker}", role_filter=UserRole.CUSTOMER.value)
        assert any(r["firstname"] == f"RoleSearch{marker}" for r in results)

        no_results = await service.search(f"rolesearch{marker}", role_filter=UserRole.ADMIN.value)
        assert no_results == []


class TestAdminStatusManagement:

    async def test_deactivate_then_activate(self, db_session):
        user = await make_user(db_session, account_status="active")
        service = UserService(db_session)
        await service.deactivate(user.id)
        await db_session.refresh(user)
        assert user.account_status == AccountStatus.INACTIVE
        await service.activate(user.id)
        await db_session.refresh(user)
        assert user.account_status == AccountStatus.ACTIVE

    async def test_verify_user_account_sets_verified(self, db_session):
        user = await make_user(db_session, verification_status="pending")
        service = UserService(db_session)
        verified = await service.verify_user_account(user.id)
        assert verified.verification_status == VerificationStatus.VERIFIED

    async def test_verify_user_account_unknown_id_raises_404(self, db_session):
        """Matches activate()/deactivate()'s behavior for an unknown user."""
        service = UserService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.verify_user_account(uuid4())
        assert exc_info.value.status_code == 404

    async def test_update_role_changes_role(self, db_session):
        user = await make_user(db_session, role=UserRole.CUSTOMER)
        service = UserService(db_session)
        updated = await service.update_role(user.id, UserRole.ADMIN)
        assert updated.role == UserRole.ADMIN

    async def test_update_role_unknown_id_returns_none(self, db_session):
        service = UserService(db_session)
        assert await service.update_role(uuid4(), UserRole.ADMIN) is None


class TestResetPasswordDeactivateActivate:
    """Regression coverage for the missing-HTTPException-import bug: the
    not-found branch must raise a clean 404 (APIException), not crash."""

    async def test_reset_password_sends_email_and_sets_token(self, db_session, mocker):
        mocker.patch("services.accounts.email.EmailService.send_password_reset_email", return_value=None)
        user = await make_user(db_session)
        service = UserService(db_session)
        result = await service.reset_password(user.id)
        assert result["success"] is True
        await db_session.refresh(user)
        assert user.reset_token is not None

    async def test_reset_password_unknown_id_raises_404(self, db_session):
        service = UserService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.reset_password(uuid4())
        assert exc_info.value.status_code == 404

    async def test_deactivate_sets_inactive(self, db_session):
        user = await make_user(db_session, account_status="active")
        service = UserService(db_session)
        result = await service.deactivate(user.id)
        assert result["success"] is True
        await db_session.refresh(user)
        assert user.account_status == AccountStatus.INACTIVE

    async def test_deactivate_unknown_id_raises_404(self, db_session):
        service = UserService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.deactivate(uuid4())
        assert exc_info.value.status_code == 404

    async def test_activate_sets_active(self, db_session):
        user = await make_user(db_session, account_status="inactive")
        service = UserService(db_session)
        result = await service.activate(user.id)
        assert result["success"] is True
        await db_session.refresh(user)
        assert user.account_status == AccountStatus.ACTIVE

    async def test_activate_unknown_id_raises_404(self, db_session):
        service = UserService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.activate(uuid4())
        assert exc_info.value.status_code == 404

    async def test_reset_password_email_failure_hits_generic_exception(self, db_session, mocker):
        """Email-sending is the one allowed-to-mock external side effect here: a real SMTP/
        Brevo outage after the token was already committed must surface as a 502 saying the email wasn't sent, not crash
        the process - exercising reset_password()'s generic exception fallback."""
        mocker.patch(
            "services.accounts.email.EmailService.send_password_reset_email",
            side_effect=Exception("Brevo is down"),
        )
        user = await make_user(db_session)
        service = UserService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.reset_password(user.id)
        assert exc_info.value.status_code == 502
