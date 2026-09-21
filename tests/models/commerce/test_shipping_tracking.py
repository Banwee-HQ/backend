"""Tests for models/commerce/shipping_tracking.py."""

from datetime import datetime, timezone

from core.utils.uuid_utils import uuid7
from models.commerce.carriers import Carrier
from models.commerce.shipping_tracking import (
    ShippingProvider, ShipmentTracking, ShipmentTrackingEvent, ShippingWebhook,
    TrackingStatus, ShipmentType,
)


def make_carrier() -> Carrier:
    return Carrier(id=uuid7(), code="ups", name="UPS", is_active=True)


def make_provider(carrier=None) -> ShippingProvider:
    provider = ShippingProvider(
        id=uuid7(), name="UPS Provider", carrier_id=uuid7(), api_url="https://example.com",
        tracking_url_template="https://example.com/track/{tracking_number}", is_active=True,
    )
    provider.carrier = carrier or make_carrier()
    return provider


def make_shipment(provider=None, carrier=None) -> ShipmentTracking:
    shipment = ShipmentTracking(
        id=uuid7(), order_id=uuid7(), provider_id=uuid7(), tracking_number="TRACK123",
        carrier_id=uuid7(), status=TrackingStatus.PENDING, shipment_type=ShipmentType.STANDARD,
        created_at=datetime.now(timezone.utc),
    )
    shipment.carrier = carrier or make_carrier()
    shipment.provider = provider
    shipment.tracking_events = []
    return shipment


class TestShippingProviderToDict:

    def test_serializes_carrier_code(self):
        provider = make_provider()
        data = provider.to_dict()
        assert data["carrier"] == "ups"

    def test_null_carrier_serializes_as_none(self):
        provider = make_provider()
        provider.carrier = None
        assert provider.to_dict()["carrier"] is None


class TestShipmentTrackingGetTrackingUrl:

    def test_builds_url_from_provider_template(self):
        shipment = make_shipment(provider=make_provider())
        assert shipment.get_tracking_url() == "https://example.com/track/TRACK123"

    def test_returns_none_without_provider(self):
        shipment = make_shipment(provider=None)
        assert shipment.get_tracking_url() is None

    def test_returns_none_without_tracking_number(self):
        shipment = make_shipment(provider=make_provider())
        shipment.tracking_number = None
        assert shipment.get_tracking_url() is None

    def test_returns_none_when_template_is_empty(self):
        provider = make_provider()
        provider.tracking_url_template = ""
        shipment = make_shipment(provider=provider)
        assert shipment.get_tracking_url() is None


class TestShipmentTrackingToDict:

    def test_includes_tracking_url_and_status_value(self):
        shipment = make_shipment(provider=make_provider())
        data = shipment.to_dict()
        assert data["status"] == "pending"
        assert data["external_tracking_url"] == "https://example.com/track/TRACK123"
        assert data["tracking_events"] == []

    def test_includes_serialized_tracking_events(self):
        shipment = make_shipment(provider=make_provider())
        event = ShipmentTrackingEvent(
            id=uuid7(), shipment_id=shipment.id, event_timestamp=datetime.now(timezone.utc),
            event_type="shipped", event_description="Left warehouse",
        )
        shipment.tracking_events = [event]
        data = shipment.to_dict()
        assert len(data["tracking_events"]) == 1
        assert data["tracking_events"][0]["event_description"] == "Left warehouse"


class TestShippingWebhookToDict:

    def test_serializes_counters(self):
        webhook = ShippingWebhook(
            id=uuid7(), provider_id=uuid7(), webhook_url="https://example.com/hook",
            is_active=True, retry_count=1, success_count=5, error_count=0,
        )
        data = webhook.to_dict()
        assert data["success_count"] == 5
        assert data["last_triggered"] is None
