"""
Shipping Tracking Service
Integrates with multiple shipping carriers (UPS, Canada Express, Royal Mail, etc.)
"""

import asyncio
import aiohttp
import json
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_
from sqlalchemy.orm import selectinload

from models.shipping_tracking import (
    ShipmentTracking, TrackingEvent, ShippingProvider, 
    ShippingCarrier, TrackingStatus, ShipmentType
)
from core.errors import APIException
from core.config import settings

class ShippingTrackingService:
    """Service for managing shipping tracking across multiple carriers"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.carrier_integrations = {
            ShippingCarrier.UPS: UPSIntegration(),
            ShippingCarrier.CANADA_EXPRESS: CanadaExpressIntegration(),
            ShippingCarrier.ROYAL_MAIL: RoyalMailIntegration(),
            ShippingCarrier.FEDEX: FedExIntegration(),
            ShippingCarrier.DHL: DHLIntegration(),
            ShippingCarrier.USPS: USPSIntegration(),
            ShippingCarrier.CANADA_POST: CanadaPostIntegration(),
            ShippingCarrier.PUROLATOR: PurolatorIntegration(),
        }

    async def create_shipment(self, shipment_data: Dict[str, Any]) -> ShipmentTracking:
        """Create a new shipment tracking record"""
        try:
            # Get provider
            provider_result = await self.db.execute(
                select(ShippingProvider).where(
                    and_(
                        ShippingProvider.carrier == shipment_data['carrier'],
                        ShippingProvider.is_active == True
                    )
                )
            )
            provider = provider_result.scalar_one_or_none()
            
            if not provider:
                raise APIException(
                    message=f"Shipping provider {shipment_data['carrier']} not found or inactive"
                )

            # Create shipment
            shipment = ShipmentTracking(
                order_id=shipment_data['order_id'],
                order_item_id=shipment_data.get('order_item_id'),
                provider_id=provider.id,
                tracking_number=shipment_data['tracking_number'],
                carrier=shipment_data['carrier'],
                shipment_type=shipment_data.get('shipment_type', ShipmentType.STANDARD),
                origin_address=shipment_data.get('origin_address'),
                destination_address=shipment_data.get('destination_address'),
                current_location=shipment_data.get('origin_address'),
                delivery_instructions=shipment_data.get('delivery_instructions'),
                package_weight=shipment_data.get('package_weight'),
                package_dimensions=shipment_data.get('package_dimensions'),
                package_value=shipment_data.get('package_value'),
                insurance_amount=shipment_data.get('insurance_amount'),
                service_level=shipment_data.get('service_level'),
                delivery_signature_required=shipment_data.get('delivery_signature_required', False),
                delivery_confirmation=shipment_data.get('delivery_confirmation'),
                notes=shipment_data.get('notes'),
                internal_notes=shipment_data.get('internal_notes')
            )

            self.db.add(shipment)
            await self.db.flush()

            # Create initial tracking event
            if shipment_data.get('shipped_at'):
                await self._create_tracking_event(
                    shipment.id,
                    "shipped",
                    "Package shipped",
                    shipment_data.get('origin_address'),
                    shipment_data['shipped_at']
                )

            await self.db.commit()
            return shipment

        except Exception as e:
            await self.db.rollback()
            raise APIException(message=f"Failed to create shipment: {str(e)}")

    async def track_shipment(self, tracking_number: str, carrier: ShippingCarrier) -> Dict[str, Any]:
        """Track a shipment using carrier-specific integration"""
        try:
            # Get shipment record
            shipment_result = await self.db.execute(
                select(ShipmentTracking).where(
                    and_(
                        ShipmentTracking.tracking_number == tracking_number,
                        ShipmentTracking.carrier == carrier
                    )
                ).options(selectinload(ShipmentTracking.tracking_events))
            )
            shipment = shipment_result.scalar_one_or_none()

            if not shipment:
                raise APIException(message="Shipment not found")

            # Get carrier integration
            integration = self.carrier_integrations.get(carrier)
            if not integration:
                raise APIException(message=f"Carrier integration not available for {carrier}")

            # Get provider configuration
            provider_result = await self.db.execute(
                select(ShippingProvider).where(ShippingProvider.id == shipment.provider_id)
            )
            provider = provider_result.scalar_one_or_none()

            # Track shipment using carrier API
            tracking_data = await integration.track_shipment(
                tracking_number, 
                provider.configuration if provider else {}
            )

            # Update shipment with latest data
            await self._update_shipment_from_tracking_data(shipment, tracking_data)

            # Create tracking events for new updates
            await self._process_tracking_events(shipment, tracking_data.get('events', []))

            # Update sync status
            shipment.last_api_sync = datetime.now(timezone.utc)
            shipment.sync_status = "success"
            shipment.external_tracking_data = tracking_data

            await self.db.commit()

            return {
                "shipment": shipment.to_dict(),
                "tracking_data": tracking_data
            }

        except Exception as e:
            # Update sync status on error
            if shipment:
                shipment.sync_status = "error"
                shipment.last_api_sync = datetime.now(timezone.utc)
                await self.db.commit()
            
            raise APIException(message=f"Failed to track shipment: {str(e)}")

    async def get_shipment_tracking(self, shipment_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed tracking information for a shipment"""
        try:
            shipment_result = await self.db.execute(
                select(ShipmentTracking).where(
                    ShipmentTracking.id == shipment_id
                ).options(selectinload(ShipmentTracking.tracking_events))
            )
            shipment = shipment_result.scalar_one_or_none()

            if not shipment:
                return None

            return shipment.to_dict()

        except Exception as e:
            raise APIException(message=f"Failed to get shipment tracking: {str(e)}")

    async def get_order_shipments(self, order_id: str) -> List[Dict[str, Any]]:
        """Get all shipments for an order"""
        try:
            shipments_result = await self.db.execute(
                select(ShipmentTracking).where(
                    ShipmentTracking.order_id == order_id
                ).options(selectinload(ShipmentTracking.tracking_events))
            )
            shipments = shipments_result.scalars().all()

            return [shipment.to_dict() for shipment in shipments]

        except Exception as e:
            raise APIException(message=f"Failed to get order shipments: {str(e)}")

    async def update_shipment_status(self, shipment_id: str, status: TrackingStatus, 
                                   event_data: Dict[str, Any] = None) -> ShipmentTracking:
        """Update shipment status and create tracking event"""
        try:
            shipment_result = await self.db.execute(
                select(ShipmentTracking).where(ShipmentTracking.id == shipment_id)
            )
            shipment = shipment_result.scalar_one_or_none()

            if not shipment:
                raise APIException(message="Shipment not found")

            old_status = shipment.status
            shipment.status = status

            # Update delivery timestamps
            if status == TrackingStatus.DELIVERED and not shipment.actual_delivery:
                shipment.actual_delivery = datetime.now(timezone.utc)

            # Create tracking event
            await self._create_tracking_event(
                shipment.id,
                status.value,
                event_data.get('description', f"Status updated to {status.value}"),
                event_data.get('location'),
                datetime.now(timezone.utc),
                event_data
            )

            await self.db.commit()
            return shipment

        except Exception as e:
            await self.db.rollback()
            raise APIException(message=f"Failed to update shipment status: {str(e)}")

    async def _update_shipment_from_tracking_data(self, shipment: ShipmentTracking, 
                                                tracking_data: Dict[str, Any]):
        """Update shipment with data from carrier API"""
        # Update status
        if 'status' in tracking_data:
            try:
                shipment.status = TrackingStatus(tracking_data['status'].lower())
            except ValueError:
                pass  # Keep existing status if invalid

        # Update location
        if 'current_location' in tracking_data:
            shipment.current_location = tracking_data['current_location']

        # Update estimated delivery
        if 'estimated_delivery' in tracking_data:
            try:
                shipment.estimated_delivery = datetime.fromisoformat(
                    tracking_data['estimated_delivery'].replace('Z', '+00:00')
                )
            except (ValueError, AttributeError):
                pass

        # Update delivery info
        if 'actual_delivery' in tracking_data:
            try:
                shipment.actual_delivery = datetime.fromisoformat(
                    tracking_data['actual_delivery'].replace('Z', '+00:00')
                )
            except (ValueError, AttributeError):
                pass

    async def _process_tracking_events(self, shipment: ShipmentTracking, 
                                       events: List[Dict[str, Any]]):
        """Process tracking events from carrier API"""
        existing_events = {event.event_timestamp.isoformat(): event for event in shipment.tracking_events}
        
        for event_data in events:
            try:
                event_timestamp = datetime.fromisoformat(
                    event_data['timestamp'].replace('Z', '+00:00')
                )
                
                # Skip if event already exists
                if event_timestamp.isoformat() in existing_events:
                    continue

                await self._create_tracking_event(
                    shipment.id,
                    event_data.get('event_type', 'unknown'),
                    event_data.get('description', ''),
                    event_data.get('location'),
                    event_timestamp,
                    event_data
                )

            except (ValueError, KeyError) as e:
                print(f"Error processing tracking event: {e}")
                continue

    async def _create_tracking_event(self, shipment_id: str, event_type: str, 
                                    description: str, location: Dict[str, Any] = None,
                                    timestamp: datetime = None, additional_data: Dict[str, Any] = None):
        """Create a tracking event"""
        event = TrackingEvent(
            shipment_id=shipment_id,
            event_timestamp=timestamp or datetime.now(timezone.utc),
            event_type=event_type,
            event_description=description,
            event_location=location,
            carrier_event_code=additional_data.get('carrier_event_code') if additional_data else None,
            carrier_event_data=additional_data.get('carrier_event_data') if additional_data else None,
            estimated_delivery=additional_data.get('estimated_delivery') if additional_data else None,
            delay_reason=additional_data.get('delay_reason') if additional_data else None,
            exception_details=additional_data.get('exception_details') if additional_data else None,
            contact_name=additional_data.get('contact_name') if additional_data else None,
            contact_phone=additional_data.get('contact_phone') if additional_data else None,
            source=additional_data.get('source', 'api') if additional_data else 'api',
            raw_data=additional_data if additional_data else {}
        )

        self.db.add(event)


class BaseCarrierIntegration:
    """Base class for carrier integrations"""
    
    async def track_shipment(self, tracking_number: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Track shipment - to be implemented by each carrier"""
        raise NotImplementedError

    def _make_api_request(self, url: str, headers: Dict[str, str] = None, 
                         params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make API request with error handling"""
        # Implementation for making HTTP requests
        pass


class UPSIntegration(BaseCarrierIntegration):
    """UPS shipping integration"""
    
    async def track_shipment(self, tracking_number: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Track UPS shipment"""
        # UPS API implementation
        api_url = "https://onlinetools.ups.com/track/v1/details"
        
        headers = {
            "Content-Type": "application/json",
            "AccessLicenseNumber": config.get('access_license_number'),
            "Username": config.get('username'),
            "Password": config.get('password')
        }
        
        params = {
            "locale": "en_US",
            "trackingNumber": tracking_number
        }
        
        # Make API call to UPS
        # This is a mock implementation
        return {
            "status": "in_transit",
            "current_location": {
                "city": "Louisville",
                "state": "KY",
                "country": "US"
            },
            "estimated_delivery": "2024-01-15T17:00:00Z",
            "events": [
                {
                    "timestamp": "2024-01-13T10:00:00Z",
                    "event_type": "picked_up",
                    "description": "Package picked up by UPS",
                    "location": {
                        "city": "Origin City",
                        "state": "ST",
                        "country": "US"
                    }
                }
            ]
        }


class CanadaExpressIntegration(BaseCarrierIntegration):
    """Canada Express shipping integration"""
    
    async def track_shipment(self, tracking_number: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Track Canada Express shipment"""
        # Canada Express API implementation
        return {
            "status": "in_transit",
            "current_location": {
                "city": "Toronto",
                "province": "ON",
                "country": "CA"
            },
            "estimated_delivery": "2024-01-16T12:00:00Z",
            "events": [
                {
                    "timestamp": "2024-01-13T09:00:00Z",
                    "event_type": "picked_up",
                    "description": "Package picked up by Canada Express",
                    "location": {
                        "city": "Origin City",
                        "province": "QC",
                        "country": "CA"
                    }
                }
            ]
        }


class RoyalMailIntegration(BaseCarrierIntegration):
    """Royal Mail shipping integration"""
    
    async def track_shipment(self, tracking_number: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Track Royal Mail shipment"""
        # Royal Mail API implementation
        return {
            "status": "in_transit",
            "current_location": {
                "city": "London",
                "country": "GB"
            },
            "estimated_delivery": "2024-01-17T14:00:00Z",
            "events": [
                {
                    "timestamp": "2024-01-13T08:00:00Z",
                    "event_type": "picked_up",
                    "description": "Package picked up by Royal Mail",
                    "location": {
                        "city": "Origin City",
                        "country": "GB"
                    }
                }
            ]
        }


class FedExIntegration(BaseCarrierIntegration):
    """FedEx shipping integration"""
    
    async def track_shipment(self, tracking_number: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Track FedEx shipment"""
        # FedEx API implementation
        return {
            "status": "in_transit",
            "current_location": {
                "city": "Memphis",
                "state": "TN",
                "country": "US"
            },
            "estimated_delivery": "2024-01-15T15:00:00Z",
            "events": [
                {
                    "timestamp": "2024-01-13T11:00:00Z",
                    "event_type": "picked_up",
                    "description": "Package picked up by FedEx",
                    "location": {
                        "city": "Origin City",
                        "state": "ST",
                        "country": "US"
                    }
                }
            ]
        }


class DHLIntegration(BaseCarrierIntegration):
    """DHL shipping integration"""
    
    async def track_shipment(self, tracking_number: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Track DHL shipment"""
        # DHL API implementation
        return {
            "status": "in_transit",
            "current_location": {
                "city": "Leipzig",
                "country": "DE"
            },
            "estimated_delivery": "2024-01-16T10:00:00Z",
            "events": [
                {
                    "timestamp": "2024-01-13T07:00:00Z",
                    "event_type": "picked_up",
                    "description": "Package picked up by DHL",
                    "location": {
                        "city": "Origin City",
                        "country": "DE"
                    }
                }
            ]
        }


class USPSIntegration(BaseCarrierIntegration):
    """USPS shipping integration"""
    
    async def track_shipment(self, tracking_number: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Track USPS shipment"""
        # USPS API implementation
        return {
            "status": "in_transit",
            "current_location": {
                "city": "Chicago",
                "state": "IL",
                "country": "US"
            },
            "estimated_delivery": "2024-01-16T16:00:00Z",
            "events": [
                {
                    "timestamp": "2024-01-13T12:00:00Z",
                    "event_type": "picked_up",
                    "description": "Package picked up by USPS",
                    "location": {
                        "city": "Origin City",
                        "state": "ST",
                        "country": "US"
                    }
                }
            ]
        }


class CanadaPostIntegration(BaseCarrierIntegration):
    """Canada Post shipping integration"""
    
    async def track_shipment(self, tracking_number: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Track Canada Post shipment"""
        # Canada Post API implementation
        return {
            "status": "in_transit",
            "current_location": {
                "city": "Ottawa",
                "province": "ON",
                "country": "CA"
            },
            "estimated_delivery": "2024-01-17T11:00:00Z",
            "events": [
                {
                    "timestamp": "2024-01-13T10:00:00Z",
                    "event_type": "picked_up",
                    "description": "Package picked up by Canada Post",
                    "location": {
                        "city": "Origin City",
                        "province": "QC",
                        "country": "CA"
                    }
                }
            ]
        }


class PurolatorIntegration(BaseCarrierIntegration):
    """Purolator shipping integration"""
    
    async def track_shipment(self, tracking_number: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Track Purolator shipment"""
        # Purolator API implementation
        return {
            "status": "in_transit",
            "current_location": {
                "city": "Toronto",
                "province": "ON",
                "country": "CA"
            },
            "estimated_delivery": "2024-01-16T13:00:00Z",
            "events": [
                {
                    "timestamp": "2024-01-13T09:30:00Z",
                    "event_type": "picked_up",
                    "description": "Package picked up by Purolator",
                    "location": {
                        "city": "Origin City",
                        "province": "ON",
                        "country": "CA"
                    }
                }
            ]
        }
