from sqlalchemy import String, Boolean, ForeignKey, DateTime, Integer, func, Index, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from core.db import Base, CHAR_LENGTH, GUID
from core.utils.uuid_utils import uuid7
from enum import Enum
import uuid
from datetime import datetime

class UserRole(str, Enum):
    GUEST = "guest"
    ADMIN = "admin"
    MANAGER = "manager"
    SUPPORT = "support"
    CUSTOMER = "customer"
class Gender(str, Enum):
    MALE = "male"
    FEMALE ="female"


class AccountStatus(str, Enum):
    """User account status types"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class VerificationStatus(str, Enum):
    """User verification status types"""
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    PENDING = "pending"


class AddressKind(str, Enum):
    """Address type kinds"""
    SHIPPING = "shipping"
    BILLING = "billing"


class User(Base):
    """Optimized User model with hard delete only"""
    __tablename__ = "users"
    __table_args__ = (
        # Optimized indexes for common queries
        Index('idx_users_email_account_status', 'email', 'account_status'),
        Index('idx_users_role_verification_status', 'role', 'verification_status'),
        Index('idx_users_country_language', 'country', 'language'),
        Index('idx_users_last_login', 'last_login'),
        Index('idx_users_stripe_customer', 'stripe_customer_id'),
        Index('idx_users_age', 'age'),
        Index('idx_users_gender', 'gender'),
        {'schema': 'auth'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Core identity fields - frequently queried
    email: Mapped[str] = mapped_column(String(CHAR_LENGTH), unique=True)
    firstname: Mapped[str] = mapped_column(String(CHAR_LENGTH))
    lastname: Mapped[str] = mapped_column(String(CHAR_LENGTH))
    hashed_password: Mapped[str] = mapped_column(String(CHAR_LENGTH))

    # Status fields as columns for fast filtering
    role: Mapped[UserRole] = mapped_column(String(50), default=UserRole.CUSTOMER)
    account_status: Mapped[AccountStatus] = mapped_column(String(50), default=AccountStatus.ACTIVE)
    verification_status: Mapped[VerificationStatus] = mapped_column(String(50), default=VerificationStatus.UNVERIFIED)

    # Contact information
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Profile information - frequently accessed
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    timezone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Optional profile fields
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Activity tracking
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Core identity fields
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # External integrations
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(CHAR_LENGTH), nullable=True, unique=True)

    # Use JSON for complex user preferences that need querying (cross-platform compatible)
    preferences: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # User settings, notification prefs

    # Simple fields as text for better performance
    verification_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    token_expiration: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Password reset fields
    reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reset_token_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships with optimized lazy loading
    addresses = relationship("Address", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    cart = relationship("Cart", back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="select")
    orders = relationship("Order", back_populates="user", lazy="select")  # Don't eager load orders
    reviews = relationship("Review", back_populates="user", lazy="select")
    wishlists = relationship("Wishlist", back_populates="user", lazy="select")
    subscriptions = relationship("Subscription", back_populates="user", lazy="select")
    payment_methods = relationship("PaymentMethod", back_populates="user", lazy="select")
    transactions = relationship("Transaction", back_populates="user", lazy="select")
    payment_intents = relationship("PaymentIntent", back_populates="user", lazy="select")
    sessions = relationship("UserSession", back_populates="user", lazy="select")
    lifecycle_metrics = relationship("CustomerLifecycleMetrics", back_populates="user", lazy="select")
    
    # Refund relationships - using string references to avoid circular imports
    created_refunds = relationship("Refund", foreign_keys="[Refund.user_id]", back_populates="user", lazy="select")
    reviewed_refunds = relationship("Refund", foreign_keys="[Refund.reviewed_by]", back_populates="reviewer", lazy="select")
    processed_refunds = relationship("Refund", foreign_keys="[Refund.processed_by]", back_populates="processor", lazy="select")
    
    # Inventory and tracking relationships
    stock_adjustments = relationship("StockAdjustment", back_populates="adjusted_by", lazy="select")
    variant_price_changes = relationship("VariantPriceHistory", back_populates="changed_by", lazy="select")

    @property
    def full_name(self) -> str:
        """Get user's full name"""
        return f"{self.firstname} {self.lastname}"

    @property
    def verified(self) -> bool:
        """Compatibility property — True when verification_status is 'verified'."""
        return self.verification_status == VerificationStatus.VERIFIED

    @property
    def is_active(self) -> bool:
        """Compatibility property — True when account_status is 'active'."""
        return self.account_status == AccountStatus.ACTIVE

    @property
    def default_address(self):
        """Get user's default address"""
        return next((addr for addr in self.addresses if addr.is_default), None)


    


    def to_dict(self) -> dict:
        """Convert user to dictionary for API responses"""
        return {
            "id": str(self.id),
            "email": self.email,
            "firstname": self.firstname,
            "lastname": self.lastname,
            "full_name": self.full_name,
            "role": self.role.value,
            "account_status": self.account_status.value,
            "verification_status": self.verification_status.value,
            "phone": self.phone,
            "phone_verified": self.phone_verified,
            "avatar_url": self.avatar_url,
            "country": self.country,
            "language": self.language,
            "timezone": self.timezone,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Address(Base):
    """Address model - no soft delete needed, addresses are typically replaced"""
    __tablename__ = "addresses"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_addresses_user_id', 'user_id'),
        Index('idx_addresses_city', 'city'),
        Index('idx_addresses_state', 'state'),
        Index('idx_addresses_country', 'country'),
        Index('idx_addresses_post_code', 'post_code'),
        Index('idx_addresses_kind', 'kind'),
        Index('idx_addresses_default', 'is_default'),
        # Composite indexes for common queries
        Index('idx_addresses_user_default', 'user_id', 'is_default'),
        Index('idx_addresses_user_kind', 'user_id', 'kind'),
        Index('idx_addresses_country_city', 'country', 'city'),
        {'schema': 'auth'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"))
    street: Mapped[str] = mapped_column(String(CHAR_LENGTH))
    city: Mapped[str] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(100))
    country: Mapped[str] = mapped_column(String(100))
    post_code: Mapped[str] = mapped_column(String(20))
    kind: Mapped[AddressKind] = mapped_column(String(50), default=AddressKind.SHIPPING)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    user = relationship("User", back_populates="addresses")

    def to_dict(self) -> dict:
        """Convert address to dictionary for API responses"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "street": self.street,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "post_code": self.post_code,
            "kind": self.kind,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
