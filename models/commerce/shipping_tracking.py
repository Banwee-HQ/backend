"""
Shipping Tracking Models
Integrates with multiple shipping companies (UPS, Canada Express, Royal Mail, etc.)
"""

from sqlalchemy import String, Boolean, ForeignKey, DateTime, func, Text, Integer, Float, Index
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from enum import Enum
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import uuid

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


class SyncStatus(str, Enum):
    """API sync status types"""
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"


class ShipmentEventType(str, Enum):
    """Shipment tracking event types"""
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    EXCEPTION = "exception"
    RETURNED = "returned"
    CANCELLED = "cancelled"

class ShippingProvider(Base):
    """Shipping provider configuration"""
    __tablename__ = "shipping_providers"
    __table_args__ = (
        Index('idx_shipping_providers_carrier', 'carrier'),
        Index('idx_shipping_providers_active', 'is_active'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    name: Mapped[str] = mapped_column(String(100))
    carrier: Mapped[ShippingCarrier] = mapped_column(PG_ENUM(ShippingCarrier, name="shipping_carrier"))
    api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Encrypted in production
    api_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Encrypted in production
    api_url: Mapped[str] = mapped_column(String(255))
    tracking_url_template: Mapped[str] = mapped_column(String(500))  # Template for tracking URLs
    webhook_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Provider-specific config
    rate_limits: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

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

class ShipmentTracking(Base):
    """Main shipment tracking model"""
    __tablename__ = "shipment_tracking"
    __table_args__ = (
        Index('idx_shipment_tracking_order_id', 'order_id'),
        Index('idx_shipment_tracking_carrier', 'carrier'),
        Index('idx_shipment_tracking_tracking_number', 'tracking_number'),
        Index('idx_shipment_tracking_status', 'status'),
        Index('idx_shipment_tracking_created_at', 'created_at'),
        Index('idx_shipment_tracking_estimated_delivery', 'estimated_delivery'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Core shipment information
    order_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("orders.id"))
    order_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), ForeignKey("order_items.id"), nullable=True)  # For multi-item shipments
    provider_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("shipping_providers.id"))

    # Tracking details
    tracking_number: Mapped[str] = mapped_column(String(100), unique=True)
    carrier: Mapped[ShippingCarrier] = mapped_column(PG_ENUM(ShippingCarrier, name="shipment_carrier"))
    status: Mapped[TrackingStatus] = mapped_column(PG_ENUM(TrackingStatus, name="tracking_status"), default=TrackingStatus.PENDING)
    shipment_type: Mapped[ShipmentType] = mapped_column(PG_ENUM(ShipmentType, name="shipment_type"), default=ShipmentType.STANDARD)

    # Timeline information
    shipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_delivery: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_delivery: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Location information
    origin_address: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Pickup address
    destination_address: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Delivery address
    current_location: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Current location
    delivery_instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Package information
    package_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Weight in kg
    package_dimensions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {length, width, height} in cm
    package_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Declared value
    insurance_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Service details
    service_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # Express, Standard, etc.
    delivery_signature_required: Mapped[bool] = mapped_column(Boolean, default=False)
    delivery_confirmation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # External tracking data
    external_tracking_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Raw data from carrier API
    last_api_sync: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[SyncStatus] = mapped_column(String(50), default=SyncStatus.PENDING)

    # Customer notifications
    customer_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_preferences: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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

class ShipmentTrackingEvent(Base):
    """Individual tracking events for a shipment"""
    __tablename__ = "shipment_tracking_events"
    __table_args__ = (
        Index('idx_tracking_events_shipment_id', 'shipment_id'),
        Index('idx_tracking_events_timestamp', 'event_timestamp'),
        Index('idx_tracking_events_event_type', 'event_type'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    shipment_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("shipment_tracking.id"))
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_type: Mapped[ShipmentEventType] = mapped_column(String(50))
    event_description: Mapped[str] = mapped_column(Text)
    event_location: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # {city, state, country, coordinates}

    # Carrier-specific data
    carrier_event_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    carrier_event_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Additional details
    estimated_delivery: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delay_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    exception_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Contact information
    contact_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Metadata
    source: Mapped[SourceType] = mapped_column(String(50), default=SourceType.API)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

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

class ShippingWebhook(Base):
    """Webhook configurations for shipping updates"""
    __tablename__ = "shipping_webhooks"
    __table_args__ = (
        Index('idx_shipping_webhooks_provider', 'provider_id'),
        Index('idx_shipping_webhooks_active', 'is_active'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    provider_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("shipping_providers.id"))
    webhook_url: Mapped[str] = mapped_column(String(500))
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    event_types: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # Which events to trigger on
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_triggered: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

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
