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

    def test_returns_none_when_get_session_with_retry_raises(self, mocker):
        """The try/except around the db_manager access is defensive - even if
        get_session_with_retry() itself blows up, callers should just see None,
        not an unhandled exception."""
        mock_manager = mocker.Mock()
        mock_manager.get_session_with_retry.side_effect = RuntimeError("not ready")
        mocker.patch("core.db.db_manager", mock_manager)
        assert worker._get_retrying_db_session() is None


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
        mock_email_service_cls = mocker.patch("core.worker.EmailService", return_value=mock_email_service)

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
        mocker.patch("core.worker.EmailService", return_value=mocker.AsyncMock())

        result = await worker.send_email_task("bogus_type", "a@example.com")
        assert result == "unknown: bogus_type"

    @staticmethod
    def _session_returning(mocker, mock_db):
        mock_session = mocker.MagicMock()
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_db)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
        return mock_session

    @pytest.mark.asyncio
    @pytest.mark.parametrize("email_type, service_method, extra_kwargs", [
        ("thank_you", "send_thank_you_email", {"customer_name": "Ada", "order_number": "O1"}),
        ("review_request", "send_review_request_email", {"customer_name": "Ada", "order_number": "O1"}),
        ("order_confirmation", "send_order_confirmation_email", {"customer_name": "Ada", "order_number": "O1"}),
        ("password_reset", "send_password_reset_email", {"reset_token": "t", "reset_link": "l"}),
        ("low_stock_alert", "send_low_stock_alert", {"product_name": "P", "current_stock": 1, "threshold": 5}),
        ("shipping_update", "send_shipping_update_email", {"customer_name": "Ada", "order_number": "O1", "tracking_number": "T1"}),
        ("order_delivered", "send_order_delivered_email", {"customer_name": "Ada", "order_id": "1", "order_number": "O1"}),
    ])
    async def test_dispatches_each_email_type_to_its_service_method(
        self, mocker, email_type, service_method, extra_kwargs
    ):
        mock_db = mocker.AsyncMock()
        mock_session = self._session_returning(mocker, mock_db)
        mocker.patch("core.worker._get_retrying_db_session", return_value=mock_session)

        mock_email_service = mocker.AsyncMock()
        mocker.patch("core.worker.EmailService", return_value=mock_email_service)

        result = await worker.send_email_task(email_type, "a@example.com", **extra_kwargs)

        getattr(mock_email_service, service_method).assert_awaited_once()
        assert result == f"sent: {email_type} → a@example.com"

    @pytest.mark.asyncio
    async def test_service_failure_is_logged_and_reraised(self, mocker):
        mock_db = mocker.AsyncMock()
        mock_session = self._session_returning(mocker, mock_db)
        mocker.patch("core.worker._get_retrying_db_session", return_value=mock_session)

        mock_email_service = mocker.AsyncMock()
        mock_email_service.send_verification_email.side_effect = RuntimeError("smtp down")
        mocker.patch("core.worker.EmailService", return_value=mock_email_service)

        with pytest.raises(RuntimeError, match="smtp down"):
            await worker.send_email_task("verification", "a@example.com")


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
        mocker.patch("core.worker.SubscriptionScheduler", return_value=mock_scheduler)

        result = await worker.process_subscription_orders_task()
        assert result == "subscriptions: 3 ok, 1 failed"


class TestRunScheduledJobFailure:

    @pytest.mark.asyncio
    async def test_job_exception_is_logged_and_reraised(self, mocker):
        """Both process_subscription_orders_task and update_promocode_statuses_task
        route through _run_scheduled_job - force the wrapped job itself to fail and
        confirm the failure isn't swallowed."""
        mock_manager = mocker.Mock(session_factory=mocker.Mock(side_effect=RuntimeError("pool exhausted")))
        mocker.patch("core.db.db_manager", mock_manager)

        with pytest.raises(RuntimeError, match="pool exhausted"):
            await worker.process_subscription_orders_task()


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
        mocker.patch("core.worker.PromoCodeScheduler", return_value=mock_scheduler)

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
    async def test_subscription_job_error_is_logged_not_raised(self, mocker):
        """The scheduler loop must survive a failing job - it logs and keeps ticking,
        rather than crashing the whole background scheduler."""
        mock_now = mocker.Mock(hour=2, minute=0)
        mocker.patch("core.worker.datetime", mocker.Mock(now=mocker.Mock(return_value=mock_now)))
        mocker.patch("core.worker.asyncio.sleep", side_effect=StopAsyncIteration)
        mocker.patch("core.worker.process_subscription_orders_task", new=mocker.AsyncMock(side_effect=RuntimeError("boom")))
        mock_promocode_task = mocker.patch("core.worker.update_promocode_statuses_task", new=mocker.AsyncMock(return_value="ok"))

        with pytest.raises(StopAsyncIteration):
            await worker._run_scheduler()

        mock_promocode_task.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_promocode_job_error_is_logged_not_raised(self, mocker):
        mock_now = mocker.Mock(hour=0, minute=0)
        mocker.patch("core.worker.datetime", mocker.Mock(now=mocker.Mock(return_value=mock_now)))
        mocker.patch("core.worker.asyncio.sleep", side_effect=StopAsyncIteration)
        mock_subscription_task = mocker.patch("core.worker.process_subscription_orders_task", new=mocker.AsyncMock(return_value="ok"))
        mocker.patch("core.worker.update_promocode_statuses_task", new=mocker.AsyncMock(side_effect=RuntimeError("boom")))

        with pytest.raises(StopAsyncIteration):
            await worker._run_scheduler()

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

    @pytest.mark.asyncio
    async def test_enqueue_sync_product_availability_syncs_with_given_id(self, mocker):
        mock_db = mocker.AsyncMock()
        mock_session = mocker.MagicMock()
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_db)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("core.worker._get_retrying_db_session", return_value=mock_session)

        mock_inventory_service = mocker.AsyncMock()
        mocker.patch("services.catalog.inventory.InventoryService", return_value=mock_inventory_service)

        from uuid import uuid4
        product_id = str(uuid4())
        await worker.enqueue_sync_product_availability(product_id)

        mock_inventory_service.sync.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueue_sync_product_availability_syncs_with_no_id(self, mocker):
        mock_db = mocker.AsyncMock()
        mock_session = mocker.MagicMock()
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_db)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("core.worker._get_retrying_db_session", return_value=mock_session)

        mock_inventory_service = mocker.AsyncMock()
        mocker.patch("services.catalog.inventory.InventoryService", return_value=mock_inventory_service)

        await worker.enqueue_sync_product_availability(None)

        mock_inventory_service.sync.assert_awaited_once_with(None)

    @pytest.mark.asyncio
    async def test_enqueue_sync_product_availability_logs_and_swallows_errors(self, mocker):
        """A sync failure (e.g. transient DB error) must not propagate and crash
        whatever background path triggered the availability sync."""
        mock_db = mocker.AsyncMock()
        mock_session = mocker.MagicMock()
        mock_session.__aenter__ = mocker.AsyncMock(return_value=mock_db)
        mock_session.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("core.worker._get_retrying_db_session", return_value=mock_session)

        mocker.patch("services.catalog.inventory.InventoryService", side_effect=RuntimeError("boom"))

        # Must not raise.
        assert await worker.enqueue_sync_product_availability("some-id") is None
