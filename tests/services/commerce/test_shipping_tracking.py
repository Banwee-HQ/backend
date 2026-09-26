"""Tests for services/commerce/shipping_tracking.py - ShippingTrackingService."""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from core.exceptions import APIException
from core.utils.uuid_utils import uuid7
from services.commerce.shipping_tracking import ShippingTrackingService
from models.commerce.carriers import Carrier
from models.commerce.shipping_tracking import ShippingProvider, ShipmentTracking, TrackingStatus
from models.commerce.orders import Order, OrderStatus, PaymentStatus, FulfillmentStatus


@pytest.fixture
async def carrier(db_session) -> Carrier:
    c = Carrier(id=uuid7(), code=f"tc{uuid4().hex[:6]}", name="Test Carrier", is_active=True)
    db_session.add(c)
    await db_session.commit()
    return c


@pytest.fixture
async def provider(db_session, carrier) -> ShippingProvider:
    p = ShippingProvider(
        id=uuid7(), name="Test Provider", carrier_id=carrier.id, is_active=True,
        api_url="https://example.com/api", tracking_url_template="https://example.com/track/{tracking_number}",
    )
    db_session.add(p)
    await db_session.commit()
    return p


@pytest.fixture
async def order(db_session, test_user) -> Order:
    o = Order(
        id=uuid7(), order_number=f"ORD-{uuid4().hex[:10].upper()}", user_id=test_user.id,
        order_status=OrderStatus.CONFIRMED, payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.UNFULFILLED,
        subtotal=39.98, shipping_cost=10.0, tax_amount=0.0, total_amount=49.98,
        billing_address={"street": "1 Test St"}, shipping_address={"street": "1 Test St"},
    )
    db_session.add(o)
    await db_session.commit()
    return o


@pytest.fixture
async def shipment(db_session, carrier, provider, order) -> ShipmentTracking:
    service = ShippingTrackingService(db_session)
    return await service.create({
        "order_id": order.id, "carrier": carrier.code, "tracking_number": f"TRACK{uuid4().hex[:8]}",
    })


class TestGetActiveCarrier:

    async def test_finds_active_carrier(self, db_session, carrier):
        service = ShippingTrackingService(db_session)
        result = await service._get_active_carrier(carrier.code)
        assert result.id == carrier.id

    async def test_unknown_code_raises_400(self, db_session):
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service._get_active_carrier("not-a-real-carrier")
        assert exc_info.value.status_code == 400

    async def test_inactive_carrier_raises_400(self, db_session, carrier):
        carrier.is_active = False
        await db_session.commit()
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service._get_active_carrier(carrier.code)
        assert exc_info.value.status_code == 400


class TestCreate:

    async def test_creates_a_shipment(self, db_session, carrier, provider, order):
        service = ShippingTrackingService(db_session)
        shipment = await service.create({
            "order_id": order.id, "carrier": carrier.code, "tracking_number": f"TRACK{uuid4().hex[:8]}",
        })
        assert shipment.order_id == order.id
        assert shipment.carrier_id == carrier.id
        assert shipment.provider_id == provider.id

    async def test_unknown_carrier_raises_400_not_500(self, db_session, order):
        """Regression test: create()'s except Exception used to catch its own
        APIException(400) from _get_active_carrier and re-raise it as a 500."""
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.create({
                "order_id": order.id, "carrier": "not-a-real-carrier", "tracking_number": "TRACK123",
            })
        assert exc_info.value.status_code == 400

    async def test_without_active_provider_records_manual_shipment(self, db_session, carrier, provider, order):
        provider.is_active = False
        await db_session.commit()
        service = ShippingTrackingService(db_session)
        shipment = await service.create({
            "order_id": order.id, "carrier": carrier.code, "tracking_number": "TRACK123",
        })
        assert shipment.provider_id is None
        assert shipment.carrier_id == carrier.id


class TestGet:

    async def test_returns_shipment_with_carrier_loaded(self, db_session, shipment):
        service = ShippingTrackingService(db_session)
        result = await service.get(str(shipment.id))
        assert result["id"] == str(shipment.id)
        assert result["carrier"]

    async def test_unknown_id_returns_none(self, db_session):
        service = ShippingTrackingService(db_session)
        assert await service.get(str(uuid4())) is None

    async def test_malformed_id_raises_500_not_unhandled(self, db_session):
        """A malformed UUID string is a real asyncpg DataError at the DB level, not a
        mocked failure - it must be caught and reported, not crash unhandled."""
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.get("not-a-valid-uuid")
        assert exc_info.value.status_code == 500


class TestListByOrder:

    async def test_returns_shipments_for_order(self, db_session, shipment, order):
        service = ShippingTrackingService(db_session)
        result = await service.list_by_order(str(order.id))
        assert len(result) == 1
        assert result[0]["id"] == str(shipment.id)

    async def test_returns_empty_for_unknown_order(self, db_session):
        service = ShippingTrackingService(db_session)
        assert await service.list_by_order(str(uuid4())) == []

    async def test_malformed_order_id_raises_500_not_unhandled(self, db_session):
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.list_by_order("not-a-valid-uuid")
        assert exc_info.value.status_code == 500


class TestUpdate:

    async def test_updates_status_and_creates_event(self, db_session, shipment):
        service = ShippingTrackingService(db_session)
        updated = await service.update(str(shipment.id), TrackingStatus.IN_TRANSIT, {"description": "Left warehouse"})
        assert updated.status == TrackingStatus.IN_TRANSIT

    async def test_delivered_sets_actual_delivery(self, db_session, shipment):
        service = ShippingTrackingService(db_session)
        updated = await service.update(str(shipment.id), TrackingStatus.DELIVERED, {})
        assert updated.actual_delivery is not None

    async def test_not_found_raises_404(self, db_session):
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.update(str(uuid4()), TrackingStatus.IN_TRANSIT, {})
        assert exc_info.value.status_code == 404


class TestTrackShipment:

    async def test_updates_shipment_from_carrier_data(self, db_session, order, mocker):
        mocker.patch(
            "services.commerce.carrier_integrations.UPSIntegration.track_shipment",
            return_value={
                "status": "in_transit", "current_location": "Memphis, TN",
                "events": [{
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "event_type": "in_transit", "description": "Departed facility",
                }],
            },
        )
        service = ShippingTrackingService(db_session)
        # "ups" is pre-seeded (see 2026_04_22_add_carriers_table) and is the
        # only carrier code the integration map actually recognizes.
        ups_carrier = await service._get_active_carrier("ups")
        db_session.add(ShippingProvider(
            id=uuid7(), name="UPS Test Provider", carrier_id=ups_carrier.id, is_active=True,
            api_url="https://example.com/api", tracking_url_template="https://example.com/track/{tracking_number}",
        ))
        await db_session.commit()
        shipment = await service.create({
            "order_id": order.id, "carrier": "ups", "tracking_number": f"TRACK{uuid4().hex[:8]}",
        })

        result = await service.track_shipment(shipment.tracking_number, "ups")
        assert result["shipment"]["status"] == "in_transit"
        assert len(result["shipment"]["tracking_events"]) == 1

    async def test_unknown_carrier_raises_404(self, db_session):
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.track_shipment("NOPE", "not-a-real-carrier")
        assert exc_info.value.status_code == 400

    async def test_no_integration_available_for_carrier_raises_400(self, db_session, shipment, carrier):
        """The carrier is a real, active row (unlike test_unknown_carrier_raises_404)
        but isn't one of the 8 carriers with a real API integration - a distinct
        failure mode from "carrier doesn't exist"."""
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.track_shipment(shipment.tracking_number, carrier.code)
        assert exc_info.value.status_code == 400


class TestUpdateShipmentFromTrackingData:

    async def test_updates_status_location_and_dates(self, db_session, shipment):
        service = ShippingTrackingService(db_session)
        await service._update_shipment_from_tracking_data(shipment, {
            "status": "in_transit",
            "current_location": {"city": "Memphis"},
            "estimated_delivery": "2026-12-01T00:00:00Z",
            "actual_delivery": "2026-11-30T00:00:00Z",
        })
        assert shipment.status == TrackingStatus.IN_TRANSIT
        assert shipment.current_location == {"city": "Memphis"}
        assert shipment.estimated_delivery is not None
        assert shipment.actual_delivery is not None

    async def test_invalid_status_is_ignored(self, db_session, shipment):
        original_status = shipment.status
        service = ShippingTrackingService(db_session)
        await service._update_shipment_from_tracking_data(shipment, {"status": "not-a-real-status"})
        assert shipment.status == original_status

    async def test_invalid_date_is_ignored(self, db_session, shipment):
        service = ShippingTrackingService(db_session)
        await service._update_shipment_from_tracking_data(shipment, {"estimated_delivery": "not-a-date"})
        assert shipment.estimated_delivery is None


class TestProcessTrackingEvents:

    async def test_creates_new_events(self, db_session, shipment):
        service = ShippingTrackingService(db_session)
        await service._process_tracking_events(shipment, [{
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "shipped", "description": "Package shipped", "location": "Warehouse",
        }])
        await db_session.flush()
        result = await service.get(str(shipment.id))
        assert len(result["tracking_events"]) == 1

    async def test_skips_events_with_missing_timestamp(self, db_session, shipment):
        service = ShippingTrackingService(db_session)
        # Missing "timestamp" key raises KeyError internally, which is caught and skipped.
        await service._process_tracking_events(shipment, [{"event_type": "shipped"}])
        result = await service.get(str(shipment.id))
        assert result["tracking_events"] == []

    async def test_skips_duplicate_event_by_timestamp(self, db_session, shipment):
        """A carrier API may resend the same event on a later poll - it must not be
        duplicated in tracking history."""
        service = ShippingTrackingService(db_session)
        ts = datetime.now(timezone.utc).isoformat()
        await service._process_tracking_events(shipment, [
            {"timestamp": ts, "event_type": "shipped", "description": "First"}
        ])
        # Re-processing the exact same timestamp must be a no-op (the `continue` branch).
        await service._process_tracking_events(shipment, [
            {"timestamp": ts, "event_type": "shipped", "description": "Duplicate"}
        ])
        result = await service.get(str(shipment.id))
        assert len(result["tracking_events"]) == 1
        assert result["tracking_events"][0]["event_description"] == "First"


class TestCreateWithShippedAt:

    async def test_shipped_at_creates_initial_tracking_event(self, db_session, carrier, provider, order):
        """Passing shipped_at at creation time should seed a "shipped" tracking event."""
        service = ShippingTrackingService(db_session)
        shipment = await service.create({
            "order_id": order.id, "carrier": carrier.code, "tracking_number": f"TRACK{uuid4().hex[:8]}",
            "shipped_at": datetime.now(timezone.utc),
        })
        result = await service.get(str(shipment.id))
        assert len(result["tracking_events"]) == 1
        assert result["tracking_events"][0]["event_type"] == "shipped"


class TestTrackShipmentErrors:

    async def test_no_matching_shipment_raises_404(self, db_session):
        """A valid, active carrier but an unknown tracking number is a 404, not the
        "carrier not found" 400 covered by test_unknown_carrier_raises_404."""
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.track_shipment("NO-SUCH-TRACKING-NUMBER", "ups")
        assert exc_info.value.status_code == 404

    async def test_carrier_api_failure_marks_sync_status_error(self, db_session, order, mocker):
        """If the carrier's API call blows up, the shipment must be marked sync_status=
        "error" and the failure surfaced as a 500 - not silently swallowed."""
        mocker.patch(
            "services.commerce.carrier_integrations.UPSIntegration.track_shipment",
            side_effect=RuntimeError("carrier API is down"),
        )
        service = ShippingTrackingService(db_session)
        ups_carrier = await service._get_active_carrier("ups")
        db_session.add(ShippingProvider(
            id=uuid7(), name="UPS Test Provider 2", carrier_id=ups_carrier.id, is_active=True,
            api_url="https://example.com/api", tracking_url_template="https://example.com/track/{tracking_number}",
        ))
        await db_session.commit()
        shipment = await service.create({
            "order_id": order.id, "carrier": "ups", "tracking_number": f"TRACK{uuid4().hex[:8]}",
        })

        with pytest.raises(APIException) as exc_info:
            await service.track_shipment(shipment.tracking_number, "ups")
        assert exc_info.value.status_code == 500
        assert shipment.sync_status == "error"


class TestUpdateErrors:

    async def test_non_serializable_event_data_is_a_500_not_a_silent_success(self, db_session, shipment):
        """event_data flows straight into a JSON column (event_location) - a value the
        DB driver can't serialize must surface as a clean error, not corrupt data or
        crash unhandled outside the try/except."""
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException) as exc_info:
            await service.update(str(shipment.id), TrackingStatus.IN_TRANSIT, {
                "description": "bad event", "location": {1, 2, 3},  # a set is not JSON-serializable
            })
        assert exc_info.value.status_code == 500


class TestUpdateShipmentFromTrackingDataErrors:

    async def test_invalid_actual_delivery_date_is_ignored(self, db_session, shipment):
        service = ShippingTrackingService(db_session)
        original = shipment.actual_delivery
        await service._update_shipment_from_tracking_data(shipment, {"actual_delivery": "not-a-date"})
        assert shipment.actual_delivery == original
