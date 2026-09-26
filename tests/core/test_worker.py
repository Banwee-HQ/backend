"""Tests for core/worker.py - scheduled jobs and the scheduler loop."""

import asyncio
from datetime import datetime, timedelta, timezone
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
    async def test_runs_renewals_and_reminders_under_the_lock(self, mocker):
        mock_session_cm = mocker.MagicMock()
        mock_session_cm.__aenter__ = mocker.AsyncMock(return_value=mocker.AsyncMock())
        mock_session_cm.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("core.db.db_manager", mocker.Mock(session_factory=mocker.Mock(return_value=mock_session_cm)))
        mocker.patch("core.worker.renewal_lock", return_value=lock(True, mocker))

        scheduler = mocker.AsyncMock()
        scheduler.process_due_subscriptions = mocker.AsyncMock(return_value={"paid": 3, "declined": 1, "pending": 0, "skipped": 2, "error": 0})
        scheduler.send_upcoming_reminders = mocker.AsyncMock(return_value=4)
        mocker.patch("core.worker.SubscriptionScheduler", return_value=scheduler)

        result = await worker.process_subscription_orders_task()
        assert result == "subscriptions: 3 paid, 1 declined, 0 pending, 2 skipped, 0 errors, 4 reminders"

    @pytest.mark.asyncio
    async def test_skips_when_another_process_holds_the_lock(self, mocker):
        mock_session_cm = mocker.MagicMock()
        mock_session_cm.__aenter__ = mocker.AsyncMock(return_value=mocker.AsyncMock())
        mock_session_cm.__aexit__ = mocker.AsyncMock(return_value=False)
        mocker.patch("core.db.db_manager", mocker.Mock(session_factory=mocker.Mock(return_value=mock_session_cm)))
        mocker.patch("core.worker.renewal_lock", return_value=lock(False, mocker))
        scheduler = mocker.patch("core.worker.SubscriptionScheduler")

        assert "another process" in await worker.process_subscription_orders_task()
        scheduler.assert_not_called()


def lock(acquired, mocker):
    cm = mocker.MagicMock()
    cm.__aenter__ = mocker.AsyncMock(return_value=acquired)
    cm.__aexit__ = mocker.AsyncMock(return_value=False)
    return cm


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


class TestSchedules:

    @pytest.mark.parametrize("local, expected", [
        ("2026-03-10 08:30", "2026-03-10 14:00"),
        ("2026-03-10 08:00", "2026-03-10 14:00"),
        ("2026-03-10 21:15", "2026-03-11 02:00"),
        ("2026-03-10 01:59", "2026-03-10 02:00"),
    ])
    def test_renewals_run_at_2_8_14_20_store_time(self, local, expected):
        after = datetime.fromisoformat(local).replace(tzinfo=worker.STORE_TZ)
        assert worker.at_hours(worker.SUBSCRIPTION_HOURS)(after) == datetime.fromisoformat(expected).replace(tzinfo=worker.STORE_TZ)

    def test_every_adds_minutes(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert worker.every(10)(start) == start + timedelta(minutes=10)


class TestRunScheduler:

    @staticmethod
    async def run(mocker, jobs, start, until):
        """Run the loop on a fake clock that jumps ahead by each requested sleep, until a point in time."""
        clock = {"now": start}
        sleeps = []
        async def fake_sleep(seconds):
            sleeps.append(seconds)
            clock["now"] += timedelta(seconds=seconds)
            if clock["now"] >= until:
                raise asyncio.CancelledError
        mocker.patch("core.worker.asyncio.sleep", side_effect=fake_sleep)
        with pytest.raises(asyncio.CancelledError):
            await worker._run_scheduler(jobs=jobs, now=lambda: clock["now"])
        return sleeps

    @pytest.mark.asyncio
    async def test_runs_at_startup_then_only_at_the_set_hours(self, mocker):
        renewals = mocker.AsyncMock(return_value="ok", __name__="renewals")
        start = datetime(2026, 3, 10, 9, 0, tzinfo=worker.STORE_TZ)
        sleeps = await self.run(mocker, ((renewals, worker.at_hours(worker.SUBSCRIPTION_HOURS)),), start, start + timedelta(hours=24))
        # 09:00 startup, then 14:00, 20:00, 02:00, 08:00
        assert renewals.await_count == 5
        assert len(sleeps) <= 30  # sleeps until the next run instead of polling

    @pytest.mark.asyncio
    async def test_a_failing_job_is_logged_and_the_loop_continues(self, mocker):
        failing = mocker.AsyncMock(side_effect=RuntimeError("boom"), __name__="failing")
        other = mocker.AsyncMock(return_value="ok", __name__="other")
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        await self.run(mocker, ((failing, worker.every(10)), (other, worker.every(10))), start, start + timedelta(minutes=25))
        assert failing.await_count == 3 and other.await_count == 3


class TestStartScheduler:

    @pytest.mark.asyncio
    async def test_schedules_the_scheduler_loop_on_the_running_event_loop(self, mocker):
        mocker.patch("core.worker._run_scheduler", new=mocker.AsyncMock(return_value=None))
        worker.start_scheduler()
        # Let the scheduled task actually run before the test tears down.
        await asyncio.sleep(0)


class TestEnqueueSyncProductAvailability:

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
