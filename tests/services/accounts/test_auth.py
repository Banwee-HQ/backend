"""Tests for services/accounts/auth.py - JWT issuance and the login/lockout flow.

authenticate() is the highest-value target here: it's what enforces the
brute-force lockout (failed_login_attempts / locked_until), which has no
other direct test coverage - the API-level tests don't attempt 5 wrong
passwords in a row against the same account.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi import BackgroundTasks, HTTPException

from services.accounts.auth import AuthService, MAX_FAILED_LOGIN_ATTEMPTS
from models.accounts.user import User, UserRole


async def make_user(db_session, password="CorrectPassword123!", **overrides) -> User:
    service = AuthService(db_session)
    fields = {
        "id": uuid4(),
        "email": f"auth_test_{uuid4().hex[:8]}@example.com",
        "firstname": "Test",
        "lastname": "User",
        "hashed_password": service.get_password_hash(password),
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


class TestPasswordHashRoundTrip:

    def test_hash_then_verify_succeeds(self, db_session):
        service = AuthService(db_session)
        hashed = service.get_password_hash("a-password")
        assert service.verify_password("a-password", hashed) is True

    def test_wrong_password_fails_verification(self, db_session):
        service = AuthService(db_session)
        hashed = service.get_password_hash("a-password")
        assert service.verify_password("not-it", hashed) is False


class TestTokens:

    def test_access_token_round_trips_through_verify(self, db_session):
        service = AuthService(db_session)
        token = service.make_access_token({"sub": "user-123"})
        payload = service.verify_token(token, "access")
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"

    async def test_refresh_token_round_trips_through_verify(self, db_session):
        service = AuthService(db_session)
        token = await service.make_refresh_token({"sub": "user-123"})
        payload = service.verify_token(token, "refresh")
        assert payload["type"] == "refresh"

    def test_verify_token_rejects_wrong_type(self, db_session):
        service = AuthService(db_session)
        access_token = service.make_access_token({"sub": "user-123"})
        with pytest.raises(HTTPException) as exc_info:
            service.verify_token(access_token, "refresh")
        assert exc_info.value.status_code == 401

    def test_verify_token_rejects_garbage(self, db_session):
        service = AuthService(db_session)
        with pytest.raises(HTTPException):
            service.verify_token("not-a-real-token", "access")


class TestAuthenticate:

    async def test_correct_credentials_return_tokens(self, db_session):
        user = await make_user(db_session, password="CorrectPassword123!")
        service = AuthService(db_session)
        result = await service.authenticate(user.email, "CorrectPassword123!", BackgroundTasks())
        assert result.access_token
        assert result.refresh_token

    async def test_unknown_email_is_rejected(self, db_session):
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.authenticate("nobody@example.com", "whatever", BackgroundTasks())
        assert exc_info.value.status_code == 401

    async def test_wrong_password_is_rejected(self, db_session):
        user = await make_user(db_session, password="CorrectPassword123!")
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.authenticate(user.email, "WrongPassword!", BackgroundTasks())
        assert exc_info.value.status_code == 401

    async def test_deactivated_account_is_rejected(self, db_session):
        user = await make_user(db_session, password="CorrectPassword123!", account_status="inactive")
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.authenticate(user.email, "CorrectPassword123!", BackgroundTasks())
        assert exc_info.value.status_code == 401

    async def test_wrong_password_increments_failed_attempts(self, db_session):
        user = await make_user(db_session, password="CorrectPassword123!")
        service = AuthService(db_session)
        with pytest.raises(HTTPException):
            await service.authenticate(user.email, "wrong", BackgroundTasks())
        await db_session.refresh(user)
        assert user.failed_login_attempts == 1

    async def test_successful_login_resets_failed_attempts(self, db_session):
        user = await make_user(db_session, password="CorrectPassword123!")
        service = AuthService(db_session)
        with pytest.raises(HTTPException):
            await service.authenticate(user.email, "wrong", BackgroundTasks())
        await db_session.refresh(user)
        assert user.failed_login_attempts == 1

        await service.authenticate(user.email, "CorrectPassword123!", BackgroundTasks())
        await db_session.refresh(user)
        assert user.failed_login_attempts == 0
        assert user.locked_until is None

    async def test_account_locks_after_max_failed_attempts(self, db_session):
        user = await make_user(db_session, password="CorrectPassword123!")
        service = AuthService(db_session)

        for _ in range(MAX_FAILED_LOGIN_ATTEMPTS):
            with pytest.raises(HTTPException):
                await service.authenticate(user.email, "wrong", BackgroundTasks())

        await db_session.refresh(user)
        assert user.failed_login_attempts == MAX_FAILED_LOGIN_ATTEMPTS
        assert user.locked_until is not None
        assert user.locked_until > datetime.now(timezone.utc)

    async def test_locked_account_rejects_even_the_correct_password(self, db_session):
        """Once locked, the correct password must not bypass the lockout."""
        user = await make_user(
            db_session, password="CorrectPassword123!",
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.authenticate(user.email, "CorrectPassword123!", BackgroundTasks())
        assert exc_info.value.status_code == 423

    async def test_expired_lockout_allows_login_again(self, db_session):
        """A locked_until in the past must not block login."""
        user = await make_user(
            db_session, password="CorrectPassword123!",
            locked_until=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        service = AuthService(db_session)
        result = await service.authenticate(user.email, "CorrectPassword123!", BackgroundTasks())
        assert result.access_token
