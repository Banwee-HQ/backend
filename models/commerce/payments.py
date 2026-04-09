"""
Consolidated payment models
Includes: PaymentMethod, PaymentIntent, Transaction
"""
from sqlalchemy import String, Boolean, ForeignKey, Float, Text, Integer, DateTime, func, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from typing import Dict, Any, Optional
from enum import Enum
from datetime import datetime as dt
import uuid as uuid_module

# Enums for Payment Method fields
class PaymentType(str, Enum):
    CARD = "card"
    BANK_ACCOUNT = "bank_account"
    MOBILE_MONEY = "mobile_money"
    OTHER = "other" # Generic for future expansion

class PaymentProvider(str, Enum):
    STRIPE = "stripe"
    PAYPAL = "paypal"
    MOMO = "momo" # Mobile Money provider (e.g., M-Pesa, MTN Mobile Money)
    GOOGLE_PAY = "google_pay"
    APPLE_PAY = "apple_pay"
    BANK_TRANSFER = "bank_transfer"
    UNKNOWN = "unknown" # For methods where provider isn't explicitly known

class CardBrand(str, Enum):
    VISA = "visa"
    VERVE = "verve"
    MASTERCARD = "mastercard"
    AMEX = "amex"
    DISCOVER = "discover"
    JCB = "jcb"
    DINERS_CLUB = "diners_club"
    UNIONPAY = "unionpay"
    UNKNOWN = "unknown"
    OTHER = "other" # For less common or newly introduced card brands


class PaymentMethod(Base):
    """User payment methods - hard delete only"""
    __tablename__ = "payment_methods"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_payment_methods_user_id', 'user_id'),
        Index('idx_payment_methods_type', 'type'),
        Index('idx_payment_methods_provider', 'provider'),
        Index('idx_payment_methods_stripe_id', 'stripe_payment_method_id'),
        Index('idx_payment_methods_default', 'is_default'),
        Index('idx_payment_methods_active', 'is_active'),
        # Composite indexes for common queries
        Index('idx_payment_methods_user_active', 'user_id', 'is_active'),
        Index('idx_payment_methods_user_default', 'user_id', 'is_default'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid_module.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    user_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("users.id"))
    # Use PG_ENUM for type to map to PostgreSQL enum type
    type: Mapped[PaymentType] = mapped_column(PG_ENUM(PaymentType, name="payment_type"))
    provider: Mapped[PaymentProvider] = mapped_column(PG_ENUM(PaymentProvider, name="payment_provider"))  # stripe, paypal, momo
    last_four: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    expiry_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expiry_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    brand: Mapped[Optional[CardBrand]] = mapped_column(PG_ENUM(CardBrand, name="card_brand"), nullable=True)  # visa, mastercard, etc.
    stripe_payment_method_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Only use JSONB for complex payment method data that needs querying
    payment_method_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Store complex payment data

    # Relationships
    user = relationship("User", back_populates="payment_methods")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "type": self.type.value,
            "provider": self.provider.value,
            "last_four": self.last_four,
            "expiry_month": self.expiry_month,
            "expiry_year": self.expiry_year,
            "brand": self.brand.value if self.brand else None,
            "stripe_payment_method_id": self.stripe_payment_method_id,
            "is_default": self.is_default,
            "is_active": self.is_active,
            "payment_method_metadata": self.payment_method_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PaymentIntent(Base):
    """Payment intent tracking with hard delete only"""
    __tablename__ = "payment_intents"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_payment_intents_stripe_id', 'stripe_payment_intent_id'),
        Index('idx_payment_intents_user_id', 'user_id'),
        Index('idx_payment_intents_subscription_id', 'subscription_id'),
        Index('idx_payment_intents_order_id', 'order_id'),
        Index('idx_payment_intents_status', 'status'),
        Index('idx_payment_intents_currency', 'currency'),
        Index('idx_payment_intents_created_at', 'created_at'),
        Index('idx_payment_intents_expires_at', 'expires_at'),
        # Composite indexes for common queries
        Index('idx_payment_intents_user_status', 'user_id', 'status'),
        Index('idx_payment_intents_status_created', 'status', 'created_at'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid_module.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Stripe payment intent ID
    stripe_payment_intent_id: Mapped[str] = mapped_column(String(255), unique=True)

    # User and subscription references
    user_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("users.id"))
    subscription_id: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)  # May be null for one-time payments
    order_id: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), ForeignKey("orders.id"), nullable=True)  # For order payments

    # Amount breakdown (JSONB for complex cost structure that may need querying)
    amount_breakdown: Mapped[dict] = mapped_column(JSONB)

    # Currency
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # Payment status
    status: Mapped[str] = mapped_column(String(50), default="requires_payment_method")

    # Stripe verification details (JSONB for structured data)
    stripe_verification: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Payment method details
    payment_method_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payment_method_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "card", "bank_account", etc.

    # 3D Secure and SCA handling
    requires_action: Mapped[bool] = mapped_column(Boolean, default=False)
    client_secret: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Expiration
    expires_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Completion details
    confirmed_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata for additional tracking (JSONB for structured payment data)
    payment_intent_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    user = relationship("User", back_populates="payment_intents")
    order = relationship("Order", back_populates="payment_intents")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert payment intent to dictionary"""
        return {
            "id": str(self.id),
            "stripe_payment_intent_id": self.stripe_payment_intent_id,
            "user_id": str(self.user_id),
            "subscription_id": str(self.subscription_id) if self.subscription_id else None,
            "order_id": str(self.order_id) if self.order_id else None,
            "amount_breakdown": self.amount_breakdown,
            "currency": self.currency,
            "status": self.status,
            "stripe_verification": self.stripe_verification,
            "payment_method_id": self.payment_method_id,
            "payment_method_type": self.payment_method_type,
            "requires_action": self.requires_action,
            "client_secret": self.client_secret,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "failure_reason": self.failure_reason,
            "metadata": self.payment_intent_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @property
    def amount(self) -> float:
        """Return a simple numeric total for compatibility with schemas.

        The database stores an `amount_breakdown` JSONB for flexibility; many
        API schemas expect a top-level `amount` attribute. Expose it here as a
        read-only property so Pydantic's `from_orm` can access it.
        """
        try:
            if isinstance(self.amount_breakdown, dict):
                return float(self.amount_breakdown.get("total", 0.0) or 0.0)
        except Exception:
            pass
        return 0.0


class Transaction(Base):
    """Financial transaction records - hard delete only"""
    __tablename__ = "transactions"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_transactions_user_id', 'user_id'),
        Index('idx_transactions_order_id', 'order_id'),
        Index('idx_transactions_payment_intent_id', 'payment_intent_id'),
        Index('idx_transactions_stripe_id', 'stripe_payment_intent_id'),
        Index('idx_transactions_status', 'status'),
        Index('idx_transactions_type', 'transaction_type'),
        Index('idx_transactions_currency', 'currency'),
        Index('idx_transactions_amount', 'amount'),
        Index('idx_transactions_idempotency_key', 'idempotency_key'),
        Index('idx_transactions_request_id', 'request_id'),
        Index('idx_transactions_created_at', 'created_at'),
        # Composite indexes for common queries
        Index('idx_transactions_user_status', 'user_id', 'status'),
        Index('idx_transactions_user_type', 'user_id', 'transaction_type'),
        Index('idx_transactions_status_created', 'status', 'created_at'),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid_module.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[dt] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[dt]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    user_id: Mapped[uuid_module.UUID] = mapped_column(GUID(), ForeignKey("users.id"))
    order_id: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), ForeignKey("orders.id"), nullable=True)
    payment_intent_id: Mapped[Optional[uuid_module.UUID]] = mapped_column(GUID(), ForeignKey("payment_intents.id"), nullable=True)
    stripe_payment_intent_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    # pending, succeeded, failed, cancelled, refunded
    status: Mapped[str] = mapped_column(String(50))
    # payment, refund, payout, chargeback
    transaction_type: Mapped[str] = mapped_column(String(50))

    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # GOLDEN RULE 2: Idempotency for payments
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # For tracking

    # Additional transaction metadata (Text for simple key-value storage)
    transaction_metadata: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Simple string metadata

    # Relationships
    user = relationship("User", back_populates="transactions")
    order = relationship("Order", back_populates="transactions")
    payment_intent = relationship("PaymentIntent")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "order_id": str(self.order_id) if self.order_id else None,
            "payment_intent_id": str(self.payment_intent_id) if self.payment_intent_id else None,
            "stripe_payment_intent_id": self.stripe_payment_intent_id,
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status,
            "transaction_type": self.transaction_type,
            "description": self.description,
            "failure_reason": self.failure_reason,
            "idempotency_key": self.idempotency_key,
            "request_id": self.request_id,
            "metadata": self.transaction_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }