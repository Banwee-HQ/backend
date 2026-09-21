"""Tests for schemas/commerce/shipping_tracking.py."""

import pytest
from pydantic import ValidationError

from schemas.commerce.shipping_tracking import Create, Update, Track
from models.commerce.shipping_tracking import TrackingStatus, ShipmentType


class TestCreate:

    def test_requires_order_and_carrier_and_tracking_number(self):
        with pytest.raises(ValidationError):
            Create(order_id="order-1")

    def test_defaults_shipment_type_standard(self):
        record = Create(order_id="order-1", carrier="ups", tracking_number="1Z999")
        assert record.shipment_type == ShipmentType.STANDARD


class TestUpdate:

    def test_requires_status(self):
        with pytest.raises(ValidationError):
            Update()

    def test_accepts_valid_status(self):
        update = Update(status=TrackingStatus.IN_TRANSIT)
        assert update.status == TrackingStatus.IN_TRANSIT


class TestTrack:

    def test_requires_tracking_number_and_carrier(self):
        with pytest.raises(ValidationError):
            Track(tracking_number="1Z999")
