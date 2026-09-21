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

    async def test_no_active_provider_raises_error(self, db_session, carrier, provider, order):
        provider.is_active = False
        await db_session.commit()
        service = ShippingTrackingService(db_session)
        with pytest.raises(APIException):
            await service.create({
                "order_id": order.id, "carrier": carrier.code, "tracking_number": "TRACK123",
            })


class TestGet:

    async def test_returns_shipment_with_carrier_loaded(self, db_session, shipment):
        service = ShippingTrackingService(db_session)
        result = await service.get(str(shipment.id))
        assert result["id"] == str(shipment.id)
        assert result["carrier"]

    async def test_unknown_id_returns_none(self, db_session):
        service = ShippingTrackingService(db_session)
        assert await service.get(str(uuid4())) is None


class TestListByOrder:

    async def test_returns_shipments_for_order(self, db_session, shipment, order):
        service = ShippingTrackingService(db_session)
        result = await service.list_by_order(str(order.id))
        assert len(result) == 1
        assert result[0]["id"] == str(shipment.id)

    async def test_returns_empty_for_unknown_order(self, db_session):
        service = ShippingTrackingService(db_session)
        assert await service.list_by_order(str(uuid4())) == []


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
