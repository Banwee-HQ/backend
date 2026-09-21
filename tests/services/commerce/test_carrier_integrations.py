"""Tests for services/commerce/carrier_integrations.py.

Each carrier integration is currently a mock returning fixed tracking data
(no real HTTP calls) - these tests verify the response shape every consumer
(services/commerce/shipping_tracking.py) relies on: status, current_location,
estimated_delivery, and a non-empty events list.
"""

import pytest

from services.commerce.carrier_integrations import (
    BaseCarrierIntegration, UPSIntegration, CanadaExpressIntegration, RoyalMailIntegration,
    FedExIntegration, DHLIntegration, USPSIntegration, CanadaPostIntegration, PurolatorIntegration,
)

ALL_INTEGRATIONS = [
    (UPSIntegration, "US"),
    (CanadaExpressIntegration, "CA"),
    (RoyalMailIntegration, "GB"),
    (FedExIntegration, "US"),
    (DHLIntegration, "DE"),
    (USPSIntegration, "US"),
    (CanadaPostIntegration, "CA"),
    (PurolatorIntegration, "CA"),
]


class TestBaseCarrierIntegration:

    async def test_track_shipment_is_not_implemented(self):
        base = BaseCarrierIntegration()
        with pytest.raises(NotImplementedError):
            await base.track_shipment("TRACK123", {})

    def test_make_api_request_is_a_stub(self):
        base = BaseCarrierIntegration()
        assert base._make_api_request("https://example.com") is None


@pytest.mark.parametrize("integration_cls,expected_country", ALL_INTEGRATIONS)
class TestCarrierIntegrations:

    async def test_returns_expected_shape(self, integration_cls, expected_country):
        integration = integration_cls()
        result = await integration.track_shipment("TRACK123", config={})

        assert result["status"] == "in_transit"
        assert result["current_location"]["country"] == expected_country
        assert "estimated_delivery" in result
        assert len(result["events"]) >= 1
        assert result["events"][0]["event_type"] == "picked_up"

    async def test_ignores_tracking_number_and_config_contents(self, integration_cls, expected_country):
        """These are mocks - any tracking number/config should return the same shape."""
        integration = integration_cls()
        result = await integration.track_shipment("", config={"unexpected": "value"})
        assert result["status"] == "in_transit"
