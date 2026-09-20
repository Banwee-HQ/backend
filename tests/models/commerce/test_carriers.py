"""Tests for models/commerce/carriers.py - the Carrier table replacing the old ShippingCarrier enum."""

import uuid

from models.commerce.carriers import Carrier


def make_carrier(code: str, name: str, is_active=True, tracking_url_template=None) -> Carrier:
    carrier = Carrier()
    carrier.id = uuid.uuid4()
    carrier.code = code
    carrier.name = name
    carrier.is_active = is_active
    carrier.tracking_url_template = tracking_url_template
    carrier.created_at = None
    carrier.updated_at = None
    return carrier


class TestToDict:

    def test_basic_fields(self):
        carrier = make_carrier("ups", "UPS")
        data = carrier.to_dict()
        assert data["code"] == "ups"
        assert data["name"] == "UPS"
        assert data["id"] == str(carrier.id)
        assert data["is_active"] is True

    def test_tracking_url_template_included(self):
        carrier = make_carrier("fedex", "FedEx", tracking_url_template="https://fedex.com/track/{tracking_number}")
        assert carrier.to_dict()["tracking_url_template"] == "https://fedex.com/track/{tracking_number}"

    def test_inactive_carrier_reflected_in_dict(self):
        carrier = make_carrier("old_carrier", "Old Carrier", is_active=False)
        assert carrier.to_dict()["is_active"] is False
