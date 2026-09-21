"""Tests for models/commerce/shipping.py - ShippingMethod.

No to_dict()/properties on this model - just field storage worth pinning.
"""

from decimal import Decimal

from core.utils.uuid_utils import uuid7
from models.commerce.shipping import ShippingMethod


class TestShippingMethodFields:

    def test_stores_core_fields(self):
        method = ShippingMethod(id=uuid7(), name="Standard", price=Decimal("10.00"), estimated_days=5, is_active=True)
        assert method.name == "Standard"
        assert method.price == Decimal("10.00")
        assert method.estimated_days == 5

    def test_stores_optional_carrier_metadata(self):
        method = ShippingMethod(
            id=uuid7(), name="UPS Ground", price=Decimal("15.00"), estimated_days=3,
            carrier="ups", tracking_url_template="https://example.com/{tracking_number}",
        )
        assert method.carrier == "ups"
        assert method.tracking_url_template == "https://example.com/{tracking_number}"
