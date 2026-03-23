"""
Shipping Tracking Models
Integrates with multiple shipping companies (UPS, Canada Express, Royal Mail, etc.)
"""

from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Text, Integer, Float, Index
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM, JSONB
from sqlalchemy.orm import relationship
from core.db import BaseModel, GUID
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, Optional

class ShippingCarrier(str, Enum):
    """Supported shipping carriers"""
    UPS = "ups"
    CANADA_EXPRESS = "canada_express"
    ROYAL_MAIL = "royal_mail"
    FEDEX = "fedex"
    DHL = "dhl"
    USPS = "usps"
    CANADA_POST = "canada_post"
    PUROLATOR = "purolator"
    TNT = "tnt"
    ARAMEX = "aramex"

    # Added carriers
    LASERSHIP = "lasership"
    ONTRAC = "ontrac"
    HERMES = "hermes"
    EVRI = "evri"              # UK (formerly Hermes)
    DPD = "dpd"
    DPD_LOCAL = "dpd_local"
    GLS = "gls"
    POSTNL = "postnl"
    BPOST = "bpost"
    SWISS_POST = "swiss_post"
    AUSTRALIA_POST = "australia_post"
    NZ_POST = "nz_post"
    JAPAN_POST = "japan_post"
    KOREA_POST = "korea_post"
    CHINA_POST = "china_post"
    SF_EXPRESS = "sf_express"
    YANWEN = "yanwen"
    CAINIAO = "cainiao"
    LAPOSTE = "laposte"
    COLISSIMO = "colissimo"
    CORREOS = "correos"
    POSTE_ITALIANE = "poste_italiane"
    POSTNORD = "postnord"
    BRING = "bring"
    BLUE_DART = "blue_dart"
    DELHIVERY = "delhivery"
    DTDC = "dtdc"
    XPRESSBEES = "xpressbees"

    OTHER = "other"


class TrackingStatus(str, Enum):
    """Tracking status levels"""
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELAYED = "delayed"
    EXCEPTION = "exception"
    RETURNED = "returned"
    CANCELLED = "cancelled"

class ShipmentType(str, Enum):
    """Types of shipments"""
    STANDARD = "standard"
    EXPRESS = "express"
    OVERNIGHT = "overnight"
    INTERNATIONAL = "international"
    FREIGHT = "freight"

class ShippingProvider(BaseModel):
    """Shipping provider configuration"""
    __tablename__ = "shipping_providers"
    __table_args__ = (
        Index('idx_shipping_providers_carrier', 'carrier'),
        Index('idx_shipping_providers_active', 'is_active'),
        {'extend_existing': True}
    )

    name = Column(String(100), nullable=False)
    carrier = Column(PG_ENUM(ShippingCarrier, name="shipping_carrier"), nullable=False)
    api_key = Column(String(255), nullable=True)  # Encrypted in production
    api_secret = Column(String(255), nullable=True)  # Encrypted in production
    api_url = Column(String(255), nullable=False)
    tracking_url_template = Column(String(500), nullable=False)  # Template for tracking URLs
    webhook_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    configuration = Column(JSONB, nullable=True)  # Provider-specific config
    rate_limits = Column(JSONB, nullable=True)  # API rate limiting config

    # Relationships
    shipments = relationship("ShipmentTracking", back_populates="provider")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "carrier": self.carrier.value,
            "api_url": self.api_url,
            "tracking_url_template": self.tracking_url_template,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class ShipmentTracking(BaseModel):
    """Main shipment tracking model"""
    __tablename__ = "shipment_tracking"
    __table_args__ = (
        Index('idx_shipment_tracking_order_id', 'order_id'),
        Index('idx_shipment_tracking_carrier', 'carrier'),
        Index('idx_shipment_tracking_tracking_number', 'tracking_number'),
        Index('idx_shipment_tracking_status', 'status'),
        Index('idx_shipment_tracking_created_at', 'created_at'),
        Index('idx_shipment_tracking_estimated_delivery', 'estimated_delivery'),
        {'extend_existing': True}
    )

    # Core shipment information
    order_id = Column(GUID(), ForeignKey("orders.id"), nullable=False)
    order_item_id = Column(GUID(), ForeignKey("order_items.id"), nullable=True)  # For multi-item shipments
    provider_id = Column(GUID(), ForeignKey("shipping_providers.id"), nullable=False)
    
    # Tracking details
    tracking_number = Column(String(100), nullable=False, unique=True)
    carrier = Column(PG_ENUM(ShippingCarrier, name="shipment_carrier"), nullable=False)
    status = Column(PG_ENUM(TrackingStatus, name="tracking_status"), default=TrackingStatus.PENDING)
    shipment_type = Column(PG_ENUM(ShipmentType, name="shipment_type"), default=ShipmentType.STANDARD)
    
    # Timeline information
    shipped_at = Column(DateTime(timezone=True), nullable=True)
    estimated_delivery = Column(DateTime(timezone=True), nullable=True)
    actual_delivery = Column(DateTime(timezone=True), nullable=True)
    
    # Location information
    origin_address = Column(JSONB, nullable=True)  # Pickup address
    destination_address = Column(JSONB, nullable=True)  # Delivery address
    current_location = Column(JSONB, nullable=True)  # Current location
    delivery_instructions = Column(Text, nullable=True)
    
    # Package information
    package_weight = Column(Float, nullable=True)  # Weight in kg
    package_dimensions = Column(JSONB, nullable=True)  # {length, width, height} in cm
    package_value = Column(Float, nullable=True)  # Declared value
    insurance_amount = Column(Float, nullable=True)
    
    # Service details
    service_level = Column(String(50), nullable=True)  # Express, Standard, etc.
    delivery_signature_required = Column(Boolean, default=False)
    delivery_confirmation = Column(String(100), nullable=True)
    
    # External tracking data
    external_tracking_data = Column(JSONB, nullable=True)  # Raw data from carrier API
    last_api_sync = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String(50), default="pending")  # pending, success, error
    
    # Customer notifications
    customer_notified = Column(Boolean, default=False)
    notification_preferences = Column(JSONB, nullable=True)
    
    # Metadata
    notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="shipments")
    order_item = relationship("OrderItem", back_populates="shipment")
    provider = relationship("ShippingProvider", back_populates="shipments")
    tracking_events = relationship("ShipmentTrackingEvent", back_populates="shipment", cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "order_id": str(self.order_id),
            "tracking_number": self.tracking_number,
            "carrier": self.carrier.value,
            "status": self.status.value,
            "shipment_type": self.shipment_type.value,
            "shipped_at": self.shipped_at.isoformat() if self.shipped_at else None,
            "estimated_delivery": self.estimated_delivery.isoformat() if self.estimated_delivery else None,
            "actual_delivery": self.actual_delivery.isoformat() if self.actual_delivery else None,
            "current_location": self.current_location,
            "delivery_instructions": self.delivery_instructions,
            "package_weight": self.package_weight,
            "package_dimensions": self.package_dimensions,
            "service_level": self.service_level,
            "delivery_signature_required": self.delivery_signature_required,
            "external_tracking_url": self.get_tracking_url(),
            "tracking_events": [event.to_dict() for event in self.tracking_events],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_tracking_url(self) -> Optional[str]:
        """Generate carrier-specific tracking URL"""
        if not self.provider or not self.tracking_number:
            return None
            
        template = self.provider.tracking_url_template
        if not template:
            return None
            
        return template.replace("{tracking_number}", self.tracking_number)

class ShipmentTrackingEvent(BaseModel):
    """Individual tracking events for a shipment"""
    __tablename__ = "shipment_tracking_events"
    __table_args__ = (
        Index('idx_tracking_events_shipment_id', 'shipment_id'),
        Index('idx_tracking_events_timestamp', 'event_timestamp'),
        Index('idx_tracking_events_event_type', 'event_type'),
        {'extend_existing': True}
    )

    shipment_id = Column(GUID(), ForeignKey("shipment_tracking.id"), nullable=False)
    event_timestamp = Column(DateTime(timezone=True), nullable=False)
    event_type = Column(String(50), nullable=False)  # picked_up, in_transit, out_for_delivery, delivered, etc.
    event_description = Column(Text, nullable=False)
    event_location = Column(JSONB, nullable=True)  # {city, state, country, coordinates}
    
    # Carrier-specific data
    carrier_event_code = Column(String(50), nullable=True)
    carrier_event_data = Column(JSONB, nullable=True)
    
    # Additional details
    estimated_delivery = Column(DateTime(timezone=True), nullable=True)
    delay_reason = Column(String(255), nullable=True)
    exception_details = Column(JSONB, nullable=True)
    
    # Contact information
    contact_name = Column(String(100), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    
    # Metadata
    source = Column(String(50), default="api")  # api, webhook, manual
    raw_data = Column(JSONB, nullable=True)

    # Relationships
    shipment = relationship("ShipmentTracking", back_populates="tracking_events")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "shipment_id": str(self.shipment_id),
            "event_timestamp": self.event_timestamp.isoformat(),
            "event_type": self.event_type,
            "event_description": self.event_description,
            "event_location": self.event_location,
            "carrier_event_code": self.carrier_event_code,
            "estimated_delivery": self.estimated_delivery.isoformat() if self.estimated_delivery else None,
            "delay_reason": self.delay_reason,
            "contact_name": self.contact_name,
            "contact_phone": self.contact_phone,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class ShippingWebhook(BaseModel):
    """Webhook configurations for shipping updates"""
    __tablename__ = "shipping_webhooks"
    __table_args__ = (
        Index('idx_shipping_webhooks_provider', 'provider_id'),
        Index('idx_shipping_webhooks_active', 'is_active'),
        {'extend_existing': True}
    )

    provider_id = Column(GUID(), ForeignKey("shipping_providers.id"), nullable=False)
    webhook_url = Column(String(500), nullable=False)
    webhook_secret = Column(String(255), nullable=True)
    event_types = Column(JSONB, nullable=True)  # Which events to trigger on
    is_active = Column(Boolean, default=True)
    retry_count = Column(Integer, default=0)
    last_triggered = Column(DateTime(timezone=True), nullable=True)
    success_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)

    # Relationships
    provider = relationship("ShippingProvider")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "provider_id": str(self.provider_id),
            "webhook_url": self.webhook_url,
            "event_types": self.event_types,
            "is_active": self.is_active,
            "retry_count": self.retry_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "last_triggered": self.last_triggered.isoformat() if self.last_triggered else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
