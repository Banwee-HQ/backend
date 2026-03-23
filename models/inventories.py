"""
Consolidated inventory models with atomic stock operations
Includes: WarehouseLocation, Inventory, StockAdjustment
"""
from sqlalchemy import Column, String, Integer, ForeignKey, Text, DateTime, Boolean, Index, select, update
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from core.db import BaseModel, CHAR_LENGTH, GUID
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID as UUIDType
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)


class WarehouseLocation(BaseModel):
    """Warehouse locations for inventory management"""
    __tablename__ = "warehouse_locations"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_warehouse_locations_name', 'name'),
        {'extend_existing': True}
    )

    name = Column(String(CHAR_LENGTH), nullable=False)
    address = Column(String(CHAR_LENGTH), nullable=True)
    description = Column(Text, nullable=True)

    inventories = relationship("Inventory", back_populates="location")


class Inventory(BaseModel):
    """Product variant inventory tracking with atomic operations"""
    __tablename__ = "inventory"
    __table_args__ = (
        # Optimized indexes for atomic operations
        Index('idx_inventory_variant_id', 'variant_id'),
        Index('idx_inventory_location_id', 'location_id'),
        Index('idx_inventory_quantity_available', 'quantity_available'),
        Index('idx_inventory_low_stock', 'low_stock_threshold'),
        Index('idx_inventory_status', 'inventory_status'),
        # Composite indexes for common atomic queries
        Index('idx_inventory_variant_status', 'variant_id', 'inventory_status'),
        Index('idx_inventory_location_quantity', 'location_id', 'quantity_available'),
        {'extend_existing': True}
    )

    variant_id = Column(GUID(), ForeignKey("product_variants.id"), nullable=False, unique=True)
    location_id = Column(GUID(), ForeignKey("warehouse_locations.id"), nullable=False)
    
    # Atomic stock tracking fields
    quantity_available = Column(Integer, default=0, nullable=False)  # Available for sale
    
    # Thresholds
    low_stock_threshold = Column(Integer, default=10, nullable=False)
    reorder_point = Column(Integer, default=5, nullable=False)
    
    # Status tracking
    inventory_status = Column(String(50), default="active", nullable=False)
    
    # Timestamps for tracking
    last_restocked_at = Column(DateTime(timezone=True), nullable=True)
    last_sold_at = Column(DateTime(timezone=True), nullable=True)
    
    # Optimistic locking for atomic operations
    version = Column(Integer, default=1, nullable=False)
    
    # Legacy field for backward compatibility
    quantity = Column(Integer, default=0, nullable=False)

    # Relationships
    variant = relationship("ProductVariant", back_populates="inventory")
    location = relationship("WarehouseLocation", back_populates="inventories")
    adjustments = relationship("StockAdjustment", back_populates="inventory", cascade="all, delete-orphan")
    
    @classmethod
    async def get_with_lock(cls, db: AsyncSession, variant_id: UUIDType) -> Optional['Inventory']:
        """
        Get inventory record with SELECT ... FOR UPDATE lock
        Prevents concurrent modifications during stock operations
        """
        try:
            query = select(cls).where(cls.variant_id == variant_id).with_for_update()
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting inventory with lock for variant {variant_id}: {e}")
            raise

    @classmethod
    async def get_multiple_with_lock(cls, db: AsyncSession, variant_ids: List[UUIDType]) -> List['Inventory']:
        """
        Get multiple inventory records with locks in consistent order
        Orders by variant_id to prevent deadlocks
        """
        try:
            query = select(cls).where(
                cls.variant_id.in_(variant_ids)
            ).order_by(cls.variant_id).with_for_update()
            
            result = await db.execute(query)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"Error getting multiple inventories with lock: {e}")
            raise

    async def atomic_update_stock(
        self, 
        db: AsyncSession,
        quantity_change: int, 
        reason: str,
        user_id: Optional[UUIDType] = None,
        notes: Optional[str] = None
    ) -> 'StockAdjustment':
        """
        Atomically update stock with proper validation and audit trail
        Must be called within a transaction with the inventory already locked
        
        Args:
            db: Database session
            quantity_change: Positive for increase, negative for decrease
            reason: Reason for stock change
            user_id: User making the change
            notes: Additional notes
        
        Returns:
            Created StockAdjustment record
        """
        # Calculate new quantities
        new_available = self.quantity_available + quantity_change
        
        # Validate stock levels
        if new_available < 0:
            from core.errors import APIException
            raise APIException(
                status_code=400,
                message=f"Insufficient stock. Available: {self.quantity_available}, Requested: {abs(quantity_change)}"
            )
        
        # Update inventory atomically
        old_quantity = self.quantity_available
        self.quantity_available = new_available
        self.quantity = new_available  # Update legacy field
        self.version += 1  # Optimistic locking
        
        # Update timestamps
        if quantity_change < 0:
            self.last_sold_at = datetime.utcnow()
        elif quantity_change > 0:
            self.last_restocked_at = datetime.utcnow()
        
        # Create audit record
        adjustment = StockAdjustment(
            inventory_id=self.id,
            quantity_change=quantity_change,
            reason=reason,
            adjusted_by_user_id=user_id,
            notes=notes or f"Stock changed from {old_quantity} to {new_available}"
        )
        
        db.add(adjustment)
        
        logger.info(f"Stock updated atomically: variant={self.variant_id}, change={quantity_change}, new_stock={new_available}")
        
        return adjustment



    @property
    def stock_status(self) -> str:
        """Determine stock status based on available quantity"""
        if self.quantity_available <= 0:
            return "out_of_stock"
        elif self.quantity_available <= self.low_stock_threshold:
            return "low_stock"
        else:
            return "in_stock"

    def to_dict(self) -> Dict[str, Any]:
        """Convert inventory to dictionary for API responses"""
        return {
            "id": str(self.id),
            "variant_id": str(self.variant_id),
            "location_id": str(self.location_id),
            "quantity_available": self.quantity_available,
            "low_stock_threshold": self.low_stock_threshold,
            "reorder_point": self.reorder_point,
            "inventory_status": self.inventory_status,
            "stock_status": self.stock_status,
            "last_restocked_at": self.last_restocked_at.isoformat() if self.last_restocked_at else None,
            "last_sold_at": self.last_sold_at.isoformat() if self.last_sold_at else None,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class StockAdjustment(BaseModel):
    """Stock adjustment records for audit trail"""
    __tablename__ = "stock_adjustments"
    __table_args__ = (
        # Indexes for search and performance
        Index('idx_stock_adjustments_inventory_id', 'inventory_id'),
        Index('idx_stock_adjustments_reason', 'reason'),
        Index('idx_stock_adjustments_user_id', 'adjusted_by_user_id'),
        Index('idx_stock_adjustments_created_at', 'created_at'),
        # Composite indexes for common queries
        Index('idx_stock_adjustments_inventory_created', 'inventory_id', 'created_at'),
        {'extend_existing': True}
    )

    inventory_id = Column(GUID(), ForeignKey("inventory.id"), nullable=False)
    quantity_change = Column(Integer, nullable=False)  # Positive for add, negative for remove
    reason = Column(String(CHAR_LENGTH), nullable=False)  # e.g., "initial_stock", "received", "sold", "returned", "damaged"
    adjusted_by_user_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    inventory = relationship("Inventory", back_populates="adjustments")
    adjusted_by = relationship("User", back_populates="stock_adjustments")

# Utility functions for atomic operations
async def atomic_stock_operation(
    db: AsyncSession,
    variant_id: UUIDType,
    operation: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Perform atomic stock operations with proper locking
    
    Args:
        db: Database session
        variant_id: Product variant ID
        operation: Operation type ('update')
        **kwargs: Operation-specific parameters
    
    Returns:
        Operation result dictionary
    """
    try:
        # Get inventory with lock
        inventory = await Inventory.get_with_lock(db, variant_id)
        
        if not inventory:
            from core.errors import APIException
            raise APIException(
                status_code=404,
                message=f"Inventory not found for variant {variant_id}"
            )
        
        if operation == "update":
            adjustment = await inventory.atomic_update_stock(
                db=db,
                quantity_change=kwargs['quantity_change'],
                reason=kwargs['reason'],
                user_id=kwargs.get('user_id'),
                notes=kwargs.get('notes')
            )
            await db.commit()
            return {
                "operation": "update",
                "inventory": inventory.to_dict(),
                "adjustment_id": str(adjustment.id)
            }
        
        else:
            from core.errors import APIException
            raise APIException(
                status_code=400,
                message=f"Unknown operation: {operation}"
            )
    
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in atomic stock operation {operation}: {e}")
        raise


async def atomic_bulk_stock_update(
    db: AsyncSession,
    stock_changes: List[Dict],
    reason: str,
    user_id: Optional[UUIDType] = None
) -> List[Dict]:
    """
    Atomically update multiple stock levels in a single transaction
    
    Args:
        db: Database session
        stock_changes: List of dicts with 'variant_id', 'quantity_change', 'notes'
        reason: Reason for stock changes
        user_id: User making the changes
    
    Returns:
        List of operation results
    """
    try:
        # Extract variant IDs and get locks in consistent order
        variant_ids = [change['variant_id'] for change in stock_changes]
        inventories = await Inventory.get_multiple_with_lock(db, variant_ids)
        
        # Create lookup for faster access
        inventory_map = {inv.variant_id: inv for inv in inventories}
        
        results = []
        
        # Process each stock change atomically
        for change in stock_changes:
            variant_id = change['variant_id']
            quantity_change = change['quantity_change']
            notes = change.get('notes')
            
            inventory = inventory_map.get(variant_id)
            if not inventory:
                from core.errors import APIException
                raise APIException(
                    status_code=404,
                    message=f"Inventory not found for variant {variant_id}"
                )
            
            # Perform atomic update
            adjustment = await inventory.atomic_update_stock(
                db=db,
                quantity_change=quantity_change,
                reason=reason,
                user_id=user_id,
                notes=notes
            )
            
            results.append({
                "variant_id": str(variant_id),
                "quantity_change": quantity_change,
                "new_quantity": inventory.quantity_available,
                "adjustment_id": str(adjustment.id)
            })
        
        # Commit all changes atomically
        await db.commit()
        
        logger.info(f"Bulk stock update completed: {len(stock_changes)} variants updated")
        
        return results
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error in bulk stock update: {e}")
        raise