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
from schemas.accounts.user import Create as UserCreate


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


class TestExplicitExpiresDelta:
    """make_access_token/make_refresh_token accept an explicit expires_delta override,
    used instead of the settings-derived default expiry."""

    def test_access_token_with_explicit_expires_delta(self, db_session):
        service = AuthService(db_session)
        token = service.make_access_token({"sub": "user-1"}, expires_delta=timedelta(minutes=5))
        payload = service.verify_token(token, "access")
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        # Should expire in ~5 minutes, not the default 60.
        assert exp < datetime.now(timezone.utc) + timedelta(minutes=6)

    async def test_refresh_token_with_explicit_expires_delta(self, db_session):
        service = AuthService(db_session)
        token = await service.make_refresh_token({"sub": "user-1"}, expires_delta=timedelta(days=1))
        payload = service.verify_token(token, "refresh")
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp < datetime.now(timezone.utc) + timedelta(days=2)


class TestVerifyTokenExpiry:

    def test_expired_access_token_is_rejected(self, db_session):
        """python-jose validates `exp` itself during jwt.decode(), so an actually-expired
        token is rejected as a JWTError before the service's own manual expiry check ever
        runs - it surfaces as the generic "could not validate credentials" message."""
        service = AuthService(db_session)
        token = service.make_access_token({"sub": "user-1"}, expires_delta=timedelta(seconds=-10))
        with pytest.raises(HTTPException) as exc_info:
            service.verify_token(token, "access")
        assert exc_info.value.status_code == 401

    def test_token_with_no_exp_claim_hits_manual_expiry_check(self, db_session):
        """The manual `exp is None` branch in verify_token() is reachable only for a token
        that never had an `exp` claim at all (jose only validates exp when it's present) -
        crafted directly here since make_access_token() always sets one."""
        from jose import jwt as jose_jwt
        from core.config import settings
        service = AuthService(db_session)
        token = jose_jwt.encode(
            {"sub": "user-1", "type": "access"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )
        with pytest.raises(HTTPException) as exc_info:
            service.verify_token(token, "access")
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()


class TestGetHelper:

    async def test_get_with_neither_id_nor_email_returns_none(self, db_session):
        service = AuthService(db_session)
        assert await service.get() is None


class TestRefreshTokenService:
    """refresh_token() - the higher-level token-rotation method (distinct from the API
    endpoint tests, which only exercise the success/invalid-token-string cases)."""

    async def test_missing_sub_in_payload_is_rejected(self, db_session):
        service = AuthService(db_session)
        # A refresh token whose payload never included "sub".
        token = await service.make_refresh_token({})
        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_token(token)
        assert exc_info.value.status_code == 401
        assert "Invalid refresh token payload" in exc_info.value.detail

    async def test_unknown_user_id_is_rejected(self, db_session):
        service = AuthService(db_session)
        token = await service.make_refresh_token({"sub": str(uuid4())})
        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_token(token)
        assert exc_info.value.status_code == 401
        assert "not found or inactive" in exc_info.value.detail

    async def test_inactive_user_is_rejected(self, db_session):
        user = await make_user(db_session, account_status="inactive")
        service = AuthService(db_session)
        token = await service.make_refresh_token({"sub": str(user.id)})
        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_token(token)
        assert exc_info.value.status_code == 401

    async def test_malformed_sub_hits_generic_exception_path(self, db_session):
        """A "sub" that isn't a valid UUID causes a real DB-level error (invalid input
        syntax for type uuid) when querying by User.id, exercising refresh_token()'s
        generic `except Exception` fallback - not a mocked failure."""
        service = AuthService(db_session)
        token = await service.make_refresh_token({"sub": "not-a-valid-uuid"})
        with pytest.raises(HTTPException) as exc_info:
            await service.refresh_token(token)
        assert exc_info.value.status_code == 401
        assert "Could not refresh token" in exc_info.value.detail

    async def test_valid_refresh_token_issues_new_access_token(self, db_session):
        user = await make_user(db_session)
        service = AuthService(db_session)
        token = await service.make_refresh_token({"sub": str(user.id)})
        result = await service.refresh_token(token)
        assert result["token_type"] == "bearer"
        assert result["access_token"]


class TestCurrentUser:
    """AuthService.current_user() - used by get_current_auth_user() to resolve the
    authenticated user from a bearer token."""

    async def test_valid_access_token_returns_the_user(self, db_session):
        user = await make_user(db_session)
        service = AuthService(db_session)
        token = service.make_access_token({"sub": str(user.id)})
        found = await service.current_user(token)
        assert found.id == user.id

    async def test_refresh_token_type_is_rejected(self, db_session):
        """current_user() only accepts access tokens."""
        user = await make_user(db_session)
        service = AuthService(db_session)
        token = await service.make_refresh_token({"sub": str(user.id)})
        with pytest.raises(HTTPException) as exc_info:
            await service.current_user(token)
        assert exc_info.value.status_code == 401
        assert "Invalid token type" in exc_info.value.detail

    async def test_missing_sub_is_rejected(self, db_session):
        service = AuthService(db_session)
        token = service.make_access_token({})
        with pytest.raises(HTTPException) as exc_info:
            await service.current_user(token)
        assert exc_info.value.status_code == 401

    async def test_expired_token_is_rejected(self, db_session):
        """As with verify_token(), python-jose rejects an actually-expired token via
        JWTError before reaching current_user()'s own manual expiry check."""
        user = await make_user(db_session)
        service = AuthService(db_session)
        token = service.make_access_token({"sub": str(user.id)}, expires_delta=timedelta(seconds=-10))
        with pytest.raises(HTTPException) as exc_info:
            await service.current_user(token)
        assert exc_info.value.status_code == 401

    async def test_token_with_no_exp_claim_hits_manual_expiry_check(self, db_session):
        from jose import jwt as jose_jwt
        from core.config import settings
        user = await make_user(db_session)
        service = AuthService(db_session)
        token = jose_jwt.encode(
            {"sub": str(user.id), "type": "access"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )
        with pytest.raises(HTTPException) as exc_info:
            await service.current_user(token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    async def test_garbage_token_is_rejected(self, db_session):
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.current_user("not-a-real-token")
        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in exc_info.value.detail

    async def test_unknown_user_id_is_rejected(self, db_session):
        service = AuthService(db_session)
        token = service.make_access_token({"sub": str(uuid4())})
        with pytest.raises(HTTPException) as exc_info:
            await service.current_user(token)
        assert exc_info.value.status_code == 401

    async def test_deactivated_user_is_rejected(self, db_session):
        user = await make_user(db_session, account_status="inactive")
        service = AuthService(db_session)
        token = service.make_access_token({"sub": str(user.id)})
        with pytest.raises(HTTPException) as exc_info:
            await service.current_user(token)
        assert exc_info.value.status_code == 401
        assert "deactivated" in exc_info.value.detail.lower()


class TestSendReset:

    async def test_unknown_email_returns_silently(self, db_session):
        """No account enumeration: an unknown email is a silent no-op, not an error."""
        service = AuthService(db_session)
        await service.send_reset(f"nobody_{uuid4().hex[:8]}@example.com", BackgroundTasks())

    async def test_known_email_sets_reset_token_and_queues_email(self, db_session):
        user = await make_user(db_session)
        service = AuthService(db_session)
        background_tasks = BackgroundTasks()
        await service.send_reset(user.email, background_tasks)
        await db_session.refresh(user)
        assert user.reset_token is not None
        assert user.reset_token_expires is not None
        assert len(background_tasks.tasks) == 1


class TestResetPwd:

    async def test_unknown_token_is_rejected(self, db_session):
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.reset_pwd(f"no-such-token-{uuid4().hex}", "NewPassword123!")
        assert exc_info.value.status_code == 400

    async def test_expired_token_is_rejected(self, db_session):
        user = await make_user(db_session)
        service = AuthService(db_session)
        user.reset_token = f"reset-{uuid4().hex}"
        user.reset_token_expires = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.add(user)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await service.reset_pwd(user.reset_token, "NewPassword123!")
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail.lower()

    async def test_valid_token_updates_password_and_clears_token(self, db_session):
        user = await make_user(db_session, password="OldPassword123!")
        service = AuthService(db_session)
        user.reset_token = f"reset-{uuid4().hex}"
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        db_session.add(user)
        await db_session.commit()

        await service.reset_pwd(user.reset_token, "NewPassword123!")
        await db_session.refresh(user)
        assert user.reset_token is None
        assert user.reset_token_expires is None
        assert service.verify_password("NewPassword123!", user.hashed_password)
        assert not service.verify_password("OldPassword123!", user.hashed_password)


class TestRevokeToken:

    async def test_revoke_always_reports_success(self, db_session):
        """Stateless JWTs can't be truly revoked server-side; this is documented as a
        client-side no-op, so even garbage input reports success."""
        service = AuthService(db_session)
        assert await service.revoke_token("anything-at-all") is True


class TestAuthServiceCreate:
    """AuthService.create() - the duplicate-email precheck that UserService.create() itself
    lacks (see services/accounts/user.py, which relies on this wrapper for that check)."""

    async def test_duplicate_email_is_rejected(self, db_session):
        user = await make_user(db_session)
        service = AuthService(db_session)
        with pytest.raises(HTTPException) as exc_info:
            await service.create(
                UserCreate(email=user.email, firstname="Dup", lastname="User", password="Secret123!"),
                BackgroundTasks(),
            )
        assert exc_info.value.status_code == 400
        assert "already registered" in exc_info.value.detail.lower()

    async def test_creates_a_new_user(self, db_session):
        service = AuthService(db_session)
        result = await service.create(
            UserCreate(
                email=f"created_{uuid4().hex[:8]}@example.com",
                firstname="New", lastname="User", password="Secret123!",
            ),
            BackgroundTasks(),
        )
        assert result.email.startswith("created_")


class TestSendResetBackgroundTask:

    async def test_failed_send_is_logged_not_raised(self, db_session, mocker):
        """The queued _send_reset_email_safely() background task must swallow a send
        failure - an unhandled exception there would break the ASGI response cycle."""
        mocker.patch("services.accounts.auth.send_email_by_type", side_effect=Exception("SMTP down"))
        user = await make_user(db_session)
        service = AuthService(db_session)
        background_tasks = BackgroundTasks()
        await service.send_reset(user.email, background_tasks)

        # Actually run the queued task, as FastAPI would after sending the response.
        task = background_tasks.tasks[0]
        await task()  # must not raise
