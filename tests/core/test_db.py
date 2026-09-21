"""Tests for core/db.py - GUID type decorator and DatabaseManager."""

import uuid
import pytest
from sqlalchemy.exc import OperationalError

from core.db import GUID, DatabaseManager
from core.exceptions import DatabaseException


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
