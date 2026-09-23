"""Tests for core/db.py - GUID/UTCDateTime type decorators, DatabaseManager, and
the get_db()/initialize_db() module-level dependency functions.
"""

import uuid
import pytest
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

import core.db as core_db
from core.db import GUID, UTCDateTime, DatabaseManager, get_db, get_db_health, initialize_db
from core.exceptions import DatabaseException, APIException


class TestGUIDBindParam:

    def test_none_stays_none(self):
        guid = GUID()
        assert guid.process_bind_param(None, None) is None

    def test_uuid_becomes_string(self):
        guid = GUID()
        value = uuid.uuid4()
        assert guid.process_bind_param(value, None) == str(value)


class TestGUIDResultValue:

    def test_none_stays_none(self):
        guid = GUID()
        assert guid.process_result_value(None, None) is None

    def test_string_becomes_uuid(self):
        guid = GUID()
        value = uuid.uuid4()
        result = guid.process_result_value(str(value), None)
        assert result == value
        assert isinstance(result, uuid.UUID)

    def test_uuid_passes_through_unchanged(self):
        guid = GUID()
        value = uuid.uuid4()
        assert guid.process_result_value(value, None) is value


class TestGUIDLoadDialectImpl:

    def test_postgresql_dialect_uses_native_uuid_type(self, mocker):
        """Mock's constructor treats `name=` specially (it's the mock's own repr
        name, not an attribute) - it must be set post-construction instead."""
        guid = GUID()
        dialect = mocker.Mock()
        dialect.name = "postgresql"
        guid.load_dialect_impl(dialect)
        # dialect.type_descriptor() just wraps whatever type object it's handed -
        # confirm it was handed a native postgres UUID type, not CHAR(36).
        from sqlalchemy.dialects.postgresql import UUID as PGUUID
        dialect.type_descriptor.assert_called_once()
        assert isinstance(dialect.type_descriptor.call_args[0][0], PGUUID)

    def test_non_postgresql_dialect_falls_back_to_char36(self, mocker):
        guid = GUID()
        dialect = mocker.Mock()
        dialect.name = "sqlite"
        guid.load_dialect_impl(dialect)
        from sqlalchemy import CHAR
        dialect.type_descriptor.assert_called_once()
        arg = dialect.type_descriptor.call_args[0][0]
        assert isinstance(arg, CHAR)
        assert arg.length == 36


class TestUTCDateTime:

    def test_bind_param_none_passes_through(self):
        assert UTCDateTime().process_bind_param(None, None) is None

    def test_bind_param_naive_datetime_becomes_utc_aware(self):
        naive = datetime(2024, 3, 5, 12, 0, 0)
        result = UTCDateTime().process_bind_param(naive, None)
        assert result.tzinfo == timezone.utc
        assert result.replace(tzinfo=None) == naive

    def test_bind_param_already_aware_datetime_passes_through_unchanged(self):
        aware = datetime(2024, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
        assert UTCDateTime().process_bind_param(aware, None) is aware

    def test_result_value_none_passes_through(self):
        assert UTCDateTime().process_result_value(None, None) is None

    def test_result_value_naive_datetime_becomes_utc_aware(self):
        naive = datetime(2024, 3, 5, 12, 0, 0)
        result = UTCDateTime().process_result_value(naive, None)
        assert result.tzinfo == timezone.utc
        assert result.replace(tzinfo=None) == naive

    def test_result_value_already_aware_datetime_passes_through_unchanged(self):
        aware = datetime(2024, 3, 5, 12, 0, 0, tzinfo=timezone.utc)
        assert UTCDateTime().process_result_value(aware, None) is aware


class TestDatabaseManagerHealthCheck:

    @pytest.mark.asyncio
    async def test_uninitialized_returns_status(self):
        manager = DatabaseManager()
        result = await manager.health_check()
        assert result["status"] == "uninitialized"

    @pytest.mark.asyncio
    async def test_healthy_when_query_succeeds(self, mocker):
        manager = DatabaseManager()
        manager.engine = mocker.Mock()

        mock_session = mocker.AsyncMock()
        mock_session.execute = mocker.AsyncMock(return_value=mocker.Mock(fetchone=mocker.Mock(return_value=(1,))))
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
        manager.session_factory = mocker.Mock(return_value=mock_session)

        result = await manager.health_check()
        assert result["status"] == "healthy"
        assert manager._connection_failures == 0

    @pytest.mark.asyncio
    async def test_unhealthy_when_query_raises(self, mocker):
        manager = DatabaseManager()
        manager.engine = mocker.Mock()
        manager.session_factory = mocker.Mock(side_effect=RuntimeError("connection refused"))

        result = await manager.health_check()
        assert result["status"] == "unhealthy"
        assert manager._connection_failures == 1


class TestDatabaseManagerConnectionPoolStatus:

    @pytest.mark.asyncio
    async def test_uninitialized_returns_status(self):
        manager = DatabaseManager()
        result = await manager.get_connection_pool_status()
        assert result["status"] == "uninitialized"

    @pytest.mark.asyncio
    async def test_reports_pool_metrics(self, mocker):
        manager = DatabaseManager()
        pool = mocker.Mock()
        pool.size.return_value = 10
        pool.checkedin.return_value = 8
        pool.checkedout.return_value = 2
        pool.overflow.return_value = 0
        pool.invalid = mocker.Mock(return_value=0)
        manager.engine = mocker.Mock(pool=pool)

        result = await manager.get_connection_pool_status()
        assert result["pool_size"] == 10
        assert result["checked_out"] == 2

    @pytest.mark.asyncio
    async def test_falls_back_when_pool_method_raises(self, mocker):
        """Some pool types (e.g. NullPool) don't support every metric method -
        the fallback branch must still return a usable dict instead of raising."""
        manager = DatabaseManager()
        pool = mocker.Mock()
        pool.size.side_effect = NotImplementedError("not supported by this pool class")
        manager.engine = mocker.Mock(pool=pool)

        result = await manager.get_connection_pool_status()
        assert result["pool_size"] == 0
        assert result["invalid"] == 0
        assert "Pool status partially unavailable" in result["error"]


class TestDatabaseManagerGetSessionWithRetry:

    @pytest.mark.asyncio
    async def test_raises_database_exception_when_no_session_factory(self):
        manager = DatabaseManager()
        with pytest.raises(DatabaseException):
            async with manager.get_session_with_retry():
                pass

    @pytest.mark.asyncio
    async def test_yields_session_on_success(self, mocker):
        manager = DatabaseManager()
        mock_session = mocker.AsyncMock()
        manager.session_factory = mocker.Mock(return_value=mock_session)

        async with manager.get_session_with_retry() as session:
            assert session is mock_session

        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rolls_back_and_reraises_when_caller_code_fails(self, mocker):
        manager = DatabaseManager()
        mock_session = mocker.AsyncMock()
        manager.session_factory = mocker.Mock(return_value=mock_session)

        with pytest.raises(ValueError):
            async with manager.get_session_with_retry() as session:
                raise ValueError("caller failure")

        mock_session.rollback.assert_awaited_once()
        mock_session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_then_succeeds(self, mocker):
        manager = DatabaseManager()
        mocker.patch("core.db.asyncio.sleep", mocker.AsyncMock())
        bad_session = mocker.AsyncMock()
        good_session = mocker.AsyncMock()
        manager.session_factory = mocker.Mock(side_effect=[
            OperationalError("stmt", {}, Exception("down")), good_session,
        ])

        async with manager.get_session_with_retry(max_retries=2, retry_delay=0.01) as session:
            assert session is good_session

    @pytest.mark.asyncio
    async def test_raises_database_exception_after_exhausting_retries(self, mocker):
        manager = DatabaseManager()
        mocker.patch("core.db.asyncio.sleep", mocker.AsyncMock())
        manager.session_factory = mocker.Mock(side_effect=OperationalError("stmt", {}, Exception("down")))

        with pytest.raises(DatabaseException):
            async with manager.get_session_with_retry(max_retries=1, retry_delay=0.01):
                pass

    @pytest.mark.asyncio
    async def test_closes_an_already_created_session_when_caller_code_raises_a_retryable_error(self, mocker):
        """Distinct from test_raises_database_exception_after_exhausting_retries:
        there the session is never created (session_factory() itself fails). Here
        the session IS created successfully, and it's the caller's own code (the
        `yield`) that then raises a retryable error type - covering the
        `if session is not None: await session.close()` cleanup branch, which is
        only reachable once a session object actually exists."""
        manager = DatabaseManager()
        session = mocker.AsyncMock()
        manager.session_factory = mocker.Mock(return_value=session)

        with pytest.raises(DatabaseException):
            async with manager.get_session_with_retry(max_retries=0) as s:
                assert s is session
                raise OperationalError("stmt", {}, Exception("connection dropped mid-request"))

        session.rollback.assert_awaited_once()
        # Closed once in the inner `finally`, and again in the outer retry-loop cleanup.
        assert session.close.await_count == 2


class TestDatabaseManagerInitialize:
    """DatabaseManager.initialize() builds a real engine against the actual dev
    Postgres DB (per this project's convention of using the real Supabase dev DB
    rather than mocking); the engine is disposed at teardown of each test."""

    async def _dispose(self, manager):
        if manager.engine is not None:
            await manager.engine.dispose()

    @pytest.mark.asyncio
    async def test_creates_a_working_engine_and_session_factory(self):
        from core.config import settings
        manager = DatabaseManager()
        try:
            manager.initialize(settings.SQLALCHEMY_DATABASE_URI, True)
            assert manager.engine is not None
            assert manager.session_factory is not None

            # Exercise the connect-time event listener (search_path/timezone setup)
            # by actually opening a connection and running a query through it.
            async with manager.session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                assert result.scalar() == 1
        finally:
            await self._dispose(manager)

    @pytest.mark.asyncio
    async def test_is_idempotent_once_already_initialized(self):
        """A second initialize() call must be a no-op (the early-return guard),
        not replace the existing engine with a new one."""
        from core.config import settings
        manager = DatabaseManager()
        try:
            manager.initialize(settings.SQLALCHEMY_DATABASE_URI, True)
            first_engine = manager.engine
            first_factory = manager.session_factory

            manager.initialize(settings.SQLALCHEMY_DATABASE_URI, True)
            assert manager.engine is first_engine
            assert manager.session_factory is first_factory
        finally:
            await self._dispose(manager)


class TestInitializeDbFunction:
    """initialize_db() is the module-level entrypoint main.py calls at startup."""

    @pytest.mark.asyncio
    async def test_with_provided_engine_wires_it_up_without_calling_manager_initialize(self, mocker):
        fake_engine = mocker.Mock()
        mock_manager_initialize = mocker.patch.object(core_db.db_manager, "initialize")
        mock_set = mocker.patch.object(core_db.db_manager, "set_engine_and_session_factory")

        await initialize_db("postgresql://ignored", True, engine=fake_engine)

        assert core_db.engine_db is fake_engine
        mock_set.assert_called_once()
        assert mock_set.call_args[0][0] is fake_engine
        mock_manager_initialize.assert_not_called()

    @pytest.mark.asyncio
    async def test_without_an_engine_delegates_to_manager_initialize(self, mocker):
        mock_manager_initialize = mocker.patch.object(core_db.db_manager, "initialize")

        await initialize_db("postgresql://ignored", False)

        mock_manager_initialize.assert_called_once_with("postgresql://ignored", False)


class TestGetDbHealth:

    @pytest.mark.asyncio
    async def test_delegates_to_the_global_manager(self):
        result = await get_db_health()
        assert "status" in result


class TestGetDb:
    """get_db() is a FastAPI dependency generator. async_client (used by every API
    test) overrides it entirely via app.dependency_overrides, so its real body -
    every branch of the try/except here - is otherwise never exercised. Drive the
    async generator directly to cover each branch."""

    @staticmethod
    def _make_retrying_session_stub(mocker, fake_session):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _ctx(*args, **kwargs):
            yield fake_session

        return _ctx

    def _wire_healthy_manager(self, mocker, fake_session=None):
        fake_session = fake_session if fake_session is not None else mocker.Mock()
        mocker.patch.object(core_db.db_manager, "session_factory", mocker.Mock())
        mocker.patch.object(
            core_db.db_manager, "get_session_with_retry", self._make_retrying_session_stub(mocker, fake_session)
        )
        return fake_session

    @pytest.mark.asyncio
    async def test_raises_when_session_factory_not_initialized(self, mocker):
        mocker.patch.object(core_db.db_manager, "session_factory", None)
        with pytest.raises(DatabaseException):
            async for _ in get_db():
                pass

    @pytest.mark.asyncio
    async def test_yields_the_session_and_completes_cleanly(self, mocker):
        fake_session = self._wire_healthy_manager(mocker)
        gen = get_db()
        session = await gen.__anext__()
        assert session is fake_session
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    @pytest.mark.asyncio
    async def test_generator_exit_on_aclose_is_handled_cleanly(self, mocker):
        """Simulates the normal FastAPI teardown path (request done -> dependency
        generator closed), which sends GeneratorExit at the yield point."""
        self._wire_healthy_manager(mocker)
        gen = get_db()
        await gen.__anext__()
        await gen.aclose()  # must not raise

    @pytest.mark.asyncio
    async def test_database_exception_from_caller_passes_through_unwrapped(self, mocker):
        self._wire_healthy_manager(mocker)
        gen = get_db()
        await gen.__anext__()
        with pytest.raises(DatabaseException, match="already logged"):
            await gen.athrow(DatabaseException(message="already logged"))

    @pytest.mark.asyncio
    async def test_http_exception_from_caller_passes_through_unwrapped(self, mocker):
        self._wire_healthy_manager(mocker)
        gen = get_db()
        await gen.__anext__()
        with pytest.raises(HTTPException) as exc_info:
            await gen.athrow(HTTPException(status_code=403, detail="nope"))
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_api_exception_from_caller_passes_through_unwrapped(self, mocker):
        """Note: APIException(HTTPException) is itself a subclass of HTTPException,
        so this is actually caught by the earlier `except HTTPException: raise`
        (both branches do a bare re-raise, so behavior is identical either way) -
        the dedicated `except APIException: raise` right after it is therefore
        unreachable dead code under the current except ordering. Harmless (same
        outcome), so left as-is rather than "fixed" - documented in the coverage
        report as the one line of core/db.py this suite can't reach."""
        self._wire_healthy_manager(mocker)
        gen = get_db()
        await gen.__anext__()
        with pytest.raises(APIException) as exc_info:
            await gen.athrow(APIException(status_code=409, message="conflict"))
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_value_error_from_caller_passes_through_unwrapped(self, mocker):
        self._wire_healthy_manager(mocker)
        gen = get_db()
        await gen.__anext__()
        with pytest.raises(ValueError, match="bad input"):
            await gen.athrow(ValueError("bad input"))

    @pytest.mark.asyncio
    async def test_validation_error_from_caller_passes_through_unwrapped(self, mocker):
        self._wire_healthy_manager(mocker)
        gen = get_db()
        await gen.__anext__()

        class _M(__import__("pydantic").BaseModel):
            x: int

        try:
            _M(x="not-an-int")
        except ValidationError as real_validation_error:
            with pytest.raises(ValidationError):
                await gen.athrow(real_validation_error)

    @pytest.mark.asyncio
    async def test_sqlalchemy_error_from_caller_is_wrapped_as_database_exception(self, mocker):
        self._wire_healthy_manager(mocker)
        gen = get_db()
        await gen.__anext__()
        with pytest.raises(DatabaseException, match="Database error"):
            await gen.athrow(SQLAlchemyError("constraint violated"))

    @pytest.mark.asyncio
    async def test_unexpected_exception_from_caller_is_wrapped_as_database_exception(self, mocker):
        self._wire_healthy_manager(mocker)
        gen = get_db()
        await gen.__anext__()
        with pytest.raises(DatabaseException, match="Database session error"):
            await gen.athrow(RuntimeError("something weird"))
