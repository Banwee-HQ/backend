"""Tests for core/worker.py - task dispatch and enqueue stubs."""

import asyncio
import pytest

from core import worker


class TestGetRetryingDbSession:

    def test_returns_none_when_db_manager_missing(self, mocker):
        mocker.patch("core.db.db_manager", None)
        assert worker._get_retrying_db_session() is None

    def test_returns_session_from_db_manager(self, mocker):
        mock_session_ctx = object()
        mock_manager = mocker.Mock()
        mock_manager.get_session_with_retry.return_value = mock_session_ctx
        mocker.patch("core.db.db_manager", mock_manager)
        assert worker._get_retrying_db_session() is mock_session_ctx


class TestGetPlainSessionFactory:

    def test_returns_none_when_db_manager_missing(self, mocker):
        mocker.patch("core.db.db_manager", None)
        assert worker._get_plain_session_factory() is None

    def test_returns_session_factory_from_db_manager(self, mocker):
        mock_manager = mocker.Mock(session_factory="the-factory")
        mocker.patch("core.db.db_manager", mock_manager)
        assert worker._get_plain_session_factory() == "the-factory"


class TestSendEmailTask:

    @pytest.mark.asyncio
    async def test_returns_failed_when_no_session(self, mocker):
        mocker.patch("core.worker._get_retrying_db_session", return_value=None)
        result = await worker.send_email_task("verification", "a@example.com")
        assert result == "failed"

    @pytest.mark.asyncio
    async def test_dispatches_verification_email(self, mocker):
        mock_db = mocker.AsyncMock()
        mock_session = mocker.MagicMock()
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_db)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("core.worker._get_retrying_db_session", return_value=mock_session)

        mock_email_service = mocker.AsyncMock()
        mock_email_service_cls = mocker.patch("services.accounts.email.EmailService", return_value=mock_email_service)

        result = await worker.send_email_task("verification", "a@example.com", firstname="Ada", verification_token="tok")

        mock_email_service.send_verification_email.assert_awaited_once_with("a@example.com", "Ada", "tok")
        assert result == "sent: verification → a@example.com"

    @pytest.mark.asyncio
    async def test_unknown_email_type_returns_unknown(self, mocker):
        mock_db = mocker.AsyncMock()
        mock_session = mocker.MagicMock()
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_db)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("core.worker._get_retrying_db_session", return_value=mock_session)
        mocker.patch("services.accounts.email.EmailService", return_value=mocker.AsyncMock())

        result = await worker.send_email_task("bogus_type", "a@example.com")
        assert result == "unknown: bogus_type"


class TestProcessSubscriptionOrdersTask:

    @pytest.mark.asyncio
    async def test_returns_failed_when_db_manager_missing(self, mocker):
        mocker.patch("core.db.db_manager", None)
        result = await worker.process_subscription_orders_task()
        assert result == "failed: db not initialized"

    @pytest.mark.asyncio
    async def test_returns_failed_when_no_session_factory(self, mocker):
        mock_manager = mocker.Mock(session_factory=None)
        mocker.patch("core.db.db_manager", mock_manager)
        result = await worker.process_subscription_orders_task()
        assert result == "failed: db not initialized"

    @pytest.mark.asyncio
    async def test_reports_processed_and_failed_counts(self, mocker):
        mock_db = mocker.AsyncMock()
        mock_session_cm = mocker.MagicMock()
        mock_session_cm.__aenter__ = mocker.AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_manager = mocker.Mock(session_factory=mocker.Mock(return_value=mock_session_cm))
        mocker.patch("core.db.db_manager", mock_manager)

        mock_scheduler = mocker.AsyncMock()
        mock_scheduler.process_due_subscriptions = mocker.AsyncMock(return_value={"processed_count": 3, "failed_count": 1})
        mocker.patch("services.commerce.subscriptions_scheduler.SubscriptionScheduler", return_value=mock_scheduler)

        result = await worker.process_subscription_orders_task()
        assert result == "subscriptions: 3 ok, 1 failed"


class TestUpdatePromocodeStatusesTask:

    @pytest.mark.asyncio
    async def test_returns_failed_when_db_manager_missing(self, mocker):
        mocker.patch("core.db.db_manager", None)
        result = await worker.update_promocode_statuses_task()
        assert result == "failed: db not initialized"

    @pytest.mark.asyncio
    async def test_reports_activated_and_deactivated_counts(self, mocker):
        mock_db = mocker.AsyncMock()
        mock_session_cm = mocker.MagicMock()
        mock_session_cm.__aenter__ = mocker.AsyncMock(return_value=mock_db)
        mock_session_cm.__aexit__ = mocker.AsyncMock(return_value=False)
        mock_manager = mocker.Mock(session_factory=mocker.Mock(return_value=mock_session_cm))
        mocker.patch("core.db.db_manager", mock_manager)

        mock_scheduler = mocker.AsyncMock()
        mock_scheduler.update_promocode_statuses = mocker.AsyncMock(return_value={"activated_count": 2, "deactivated_count": 1})
        mocker.patch("services.commerce.promocode_scheduler.PromoCodeScheduler", return_value=mock_scheduler)

        result = await worker.update_promocode_statuses_task()
        assert result == "promocodes: 2 activated, 1 deactivated"


class TestRunScheduler:

    @pytest.mark.asyncio
    async def test_runs_subscription_job_at_a_trigger_hour(self, mocker):
        mock_now = mocker.Mock(hour=2, minute=0)
        mocker.patch("core.worker.datetime", mocker.Mock(now=mocker.Mock(return_value=mock_now)))
        mocker.patch("core.worker.asyncio.sleep", side_effect=StopAsyncIteration)
        mock_subscription_task = mocker.patch("core.worker.process_subscription_orders_task", new=mocker.AsyncMock(return_value="ok"))
        mock_promocode_task = mocker.patch("core.worker.update_promocode_statuses_task", new=mocker.AsyncMock(return_value="ok"))

        with pytest.raises(StopAsyncIteration):
            await worker._run_scheduler()

        mock_subscription_task.assert_awaited_once()
        mock_promocode_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_runs_promocode_job_at_midnight(self, mocker):
        mock_now = mocker.Mock(hour=0, minute=0)
        mocker.patch("core.worker.datetime", mocker.Mock(now=mocker.Mock(return_value=mock_now)))
        mocker.patch("core.worker.asyncio.sleep", side_effect=StopAsyncIteration)
        mock_subscription_task = mocker.patch("core.worker.process_subscription_orders_task", new=mocker.AsyncMock(return_value="ok"))
        mock_promocode_task = mocker.patch("core.worker.update_promocode_statuses_task", new=mocker.AsyncMock(return_value="ok"))

        with pytest.raises(StopAsyncIteration):
            await worker._run_scheduler()

        mock_promocode_task.assert_awaited_once()
        mock_subscription_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_does_not_run_jobs_outside_trigger_times(self, mocker):
        mock_now = mocker.Mock(hour=3, minute=15)
        mocker.patch("core.worker.datetime", mocker.Mock(now=mocker.Mock(return_value=mock_now)))
        mocker.patch("core.worker.asyncio.sleep", side_effect=StopAsyncIteration)
        mock_subscription_task = mocker.patch("core.worker.process_subscription_orders_task", new=mocker.AsyncMock(return_value="ok"))
        mock_promocode_task = mocker.patch("core.worker.update_promocode_statuses_task", new=mocker.AsyncMock(return_value="ok"))

        with pytest.raises(StopAsyncIteration):
            await worker._run_scheduler()

        mock_subscription_task.assert_not_awaited()
        mock_promocode_task.assert_not_awaited()


class TestStartScheduler:

    @pytest.mark.asyncio
    async def test_schedules_the_scheduler_loop_on_the_running_event_loop(self, mocker):
        mocker.patch("core.worker._run_scheduler", new=mocker.AsyncMock(return_value=None))
        worker.start_scheduler()
        # Let the scheduled task actually run before the test tears down.
        await asyncio.sleep(0)


class TestEnqueueStubs:

    @pytest.mark.asyncio
    async def test_enqueue_subscription_renewal_delegates_to_processing_task(self, mocker):
        mock_task = mocker.patch("core.worker.process_subscription_orders_task", return_value="ok")
        await worker.enqueue_subscription_renewal("sub-1")
        mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_cart_cleanup_is_a_noop(self):
        assert await worker.enqueue_cart_cleanup() is None

    @pytest.mark.asyncio
    async def test_enqueue_promocode_update_delegates_to_status_task(self, mocker):
        mock_task = mocker.patch("core.worker.update_promocode_statuses_task", return_value="ok")
        await worker.enqueue_promocode_update()
        mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_sync_product_availability_no_session_is_noop(self, mocker):
        mocker.patch("core.worker._get_retrying_db_session", return_value=None)
        assert await worker.enqueue_sync_product_availability("some-id") is None
