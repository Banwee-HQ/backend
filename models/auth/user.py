from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from core.db import BaseModel, CHAR_LENGTH, GUID, Index
from enum import Enum

class UserRole(str, Enum):
    GUEST = "guest"
    ADMIN = "admin"
    MANAGER = "manager"
    SUPPORT = "support"
    CUSTOMER = "customer"
    SUPPLIER = "supplier"

class User(BaseModel):
    """Optimized User model with hard delete only"""
    __tablename__ = "users"
    __table_args__ = (
        # Optimized indexes for common queries
        Index('idx_users_email_is_active', 'email', 'is_active'),
        Index('idx_users_role_verified', 'role', 'verified'),
        Index('idx_users_country_language', 'country', 'language'),
        Index('idx_users_last_login', 'last_login'),
        Index('idx_users_stripe_customer', 'stripe_customer_id'),
        # Partial index for active users only
        Index('idx_users_is_active_only', 'email', 'role', postgresql_where='is_active = true'),
        {'extend_existing': True}
    )

    # Core identity fields - frequently queried
    email = Column(String(CHAR_LENGTH), unique=True, nullable=False)
    firstname = Column(String(CHAR_LENGTH), nullable=False)
    lastname = Column(String(CHAR_LENGTH), nullable=False)
    hashed_password = Column(String(CHAR_LENGTH), nullable=False)
    
    # Status fields as columns for fast filtering
    role = Column(String(50), default=UserRole.CUSTOMER, nullable=False)
    account_status = Column(String(50), default="active", nullable=False)
    verification_status = Column(String(50), default="unverified", nullable=False)
    
    # Legacy fields (keep for backward compatibility)
    verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Contact information
    phone = Column(String(20), nullable=True)
    phone_verified = Column(Boolean, default=False)
    
    # Profile information - frequently accessed
    country = Column(String(100), nullable=True)
    language = Column(String(10), default="en")
    timezone = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    
    # Activity tracking
    last_login = Column(DateTime(timezone=True), nullable=True)
    last_activity_at = Column(DateTime(timezone=True), nullable=True)
    login_count = Column(Integer, default=0)
    
    # Security fields
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    
    # External integrations
    stripe_customer_id = Column(String(CHAR_LENGTH), nullable=True, unique=True)
    
    # Use JSONB only for complex user preferences that need querying
    preferences = Column(JSONB, nullable=True)  # User settings, notification prefs
    
    # Simple fields as text for better performance
    verification_token = Column(String(255), nullable=True)
    token_expiration = Column(DateTime(timezone=True), nullable=True)
    
    # Password reset fields
    reset_token = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime(timezone=True), nullable=True)
    
    # Legacy profile fields (consider moving to preferences JSONB)
    age = Column(String(10), nullable=True)
    gender = Column(String(50), nullable=True)

    # Relationships with optimized lazy loading
    addresses = relationship("Address", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    cart = relationship("Cart", back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="select")
    orders = relationship("Order", back_populates="user", lazy="select")  # Don't eager load orders
    reviews = relationship("Review", back_populates="user", lazy="select")
    wishlists = relationship("Wishlist", back_populates="user", lazy="select")
    subscriptions = relationship("Subscription", back_populates="user", lazy="select")
    payment_methods = relationship("PaymentMethod", back_populates="user", lazy="select")
    transactions = relationship("Transaction", back_populates="user", lazy="select")
    supplied_products = relationship("Product", back_populates="supplier", lazy="select")
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
    def default_address(self):
        """Get user's default address"""
        return next((addr for addr in self.addresses if addr.is_default), None)

    @property
    def is_active_verified(self) -> bool:
        """Check if user is both active and verified"""
        return self.is_active and self.verified

    @property
    def active(self) -> bool:
        """Backward compatibility property for is_active field"""
        return self.is_active

    def to_dict(self) -> dict:
        """Convert user to dictionary for API responses"""
        return {
            "id": str(self.id),
            "email": self.email,
            "firstname": self.firstname,
            "lastname": self.lastname,
            "full_name": self.full_name,
            "role": self.role.value,
            "account_status": self.account_status,
            "verification_status": self.verification_status,
            "verified": self.verified,  # Legacy field
            "is_active": self.is_active,  # Primary field
            "is_active": self.is_active,  # Legacy compatibility
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


class Address(BaseModel):
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
        {'extend_existing': True}
    )

    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    street = Column(String(CHAR_LENGTH), nullable=False)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False)
    post_code = Column(String(20), nullable=False)
    kind = Column(String(50), default="shipping", nullable=False)  # shipping, billing
    is_default = Column(Boolean, default=False)

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
