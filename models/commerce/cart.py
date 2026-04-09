from sqlalchemy import ForeignKey, Integer, Numeric, DateTime, func, event, DDL, Index
from sqlalchemy.orm import relationship, validates, Mapped, mapped_column
from core.db import Base, GUID
from core.utils.uuid_utils import uuid7
from decimal import Decimal
from datetime import datetime as dt
from typing import Optional
import uuid

class Cart(Base):
    __tablename__ = "carts"
    __table_args__ = (
        Index('idx_carts_user_id', 'user_id', unique=True),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey('users.id'))
    
    items = relationship("CartItem", back_populates="cart", cascade="all, delete-orphan")
    user = relationship("User", back_populates="cart")

    @property
    def subtotal(self) -> Decimal:
        return sum(item.total_price for item in self.items)

    @property
    def total_items(self) -> int:
        return sum(item.quantity for item in self.items)

class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        Index('idx_cart_items_cart_id', 'cart_id'),
        Index('idx_cart_items_product_id', 'product_id'),
        Index('idx_cart_items_variant_id', 'variant_id'),
        Index('idx_cart_items_cart_product_variant', 'cart_id', 'product_id', 'variant_id', unique=True),
        {'schema': 'commerce'}
    )

    # Common fields (previously from BaseModel)
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    cart_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey('carts.id'))
    product_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey('products.id'))
    variant_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey('product_variants.id'))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price_per_unit: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    cart = relationship("Cart", back_populates="items")
    product = relationship("Product")
    variant = relationship("ProductVariant")

    @property
    def total_price(self) -> Decimal:
        return Decimal(str(self.price_per_unit)) * Decimal(str(self.quantity))

    @validates('quantity')
    def validate_quantity(self, key, quantity):
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")
        return quantity

# DDL statement for the function
update_cart_updated_at_function = DDL("""
CREATE OR REPLACE FUNCTION update_cart_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE carts
    SET updated_at = NOW()
    WHERE id = NEW.cart_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")

# DDL statement for the trigger
update_cart_updated_at_trigger_ddl = DDL("""
CREATE TRIGGER trigger_update_cart_updated_at
AFTER INSERT OR UPDATE OR DELETE ON cart_items
FOR EACH ROW
EXECUTE FUNCTION update_cart_updated_at();
""")

# Associate the function DDL with the CartItem table's creation
event.listen(CartItem.__table__, 'after_create', update_cart_updated_at_function)
# Associate the trigger DDL with the CartItem table's creation
event.listen(CartItem.__table__, 'after_create', update_cart_updated_at_trigger_ddl)

