# Subscription Billing Flow

## Overview

This document explains how automatic subscription billing works in the application.

**Key Points:**
- Subscriptions store **historical prices** at creation (never change)
- Subscriptions calculate **current prices** dynamically at billing time
- Payment is processed **FIRST** before creating orders
- Shipping costs are fetched from database dynamically (no hardcoded values)
- ARQ worker runs **separately** from FastAPI server

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ARQ Worker (Always Running)                  │
│                         (Separate Server from FastAPI)               │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Cron Job: Daily at 2:00 AM UTC                                │ │
│  │  Task: process_subscription_orders_task                        │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  When triggered:                                                    │
│  1. Query database for due subscriptions                           │
│  2. For each subscription:                                         │
│     ┌──────────────────────────────────────────────────────────┐  │
│     │ a. Recalculate CURRENT prices (not historical)          │  │
│     │    - Get current product variant prices                 │  │
│     │    - Fetch current shipping costs from database         │  │
│     │    - Calculate current tax based on address             │  │
│     │    - Apply any active discounts                         │  │
│     │ b. Update subscription current_* fields                 │  │
│     │ c. Process payment via Stripe (using current prices)    │  │
│     │ d. If payment succeeds:                                 │  │
│     │    - Create order with current prices                   │  │
│     │    - Create order items                                 │  │
│     │    - Update inventory (decrement stock)                 │  │
│     │    - Update subscription billing dates                  │  │
│     │    - Send order confirmation email                      │  │
│     │ e. If payment fails:                                    │  │
│     │    - Mark subscription as 'payment_failed'              │  │
│     │    - Store error message in last_payment_error          │  │
│     │    - Do NOT create order                                │  │
│     │    - Do NOT update inventory                            │  │
│     └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Step-by-Step Flow

### 1. Subscription Creation
When a user creates a subscription via `POST /v1/subscriptions/`:

**Stored Fields:**
- `status` = "active"
- `next_billing_date` = calculated based on billing cycle
- `auto_renew` = true
- `variant_ids` = list of product variant IDs (JSON array)
- `delivery_address_id` = shipping address UUID
- `billing_cycle` = "weekly", "monthly", or "yearly"

**Historical Prices (stored at creation, never change):**
- `price_at_creation` = total price at creation
- `variant_prices_at_creation` = [{"id": "uuid", "price": 10.0, "qty": 1}]
- `shipping_amount_at_creation` = shipping cost at creation
- `tax_amount_at_creation` = tax amount at creation
- `tax_rate_at_creation` = tax rate at creation

**Current Prices (updated each billing cycle):**
- `current_variant_prices` = [{"id": "uuid", "price": 12.0, "qty": 1}]
- `current_shipping_amount` = current shipping cost
- `current_tax_amount` = current tax amount
- `current_tax_rate` = current tax rate

**Discount Fields:**
- `discount_id` = UUID reference to promocode
- `discount_type` = "percentage" or "fixed"
- `discount_value` = 10 (for 10% or $10)
- `discount_code` = "SAVE10"

### 2. ARQ Worker Monitoring
The ARQ worker runs continuously on a **separate server** and checks every day at 2 AM:

```sql
SELECT * FROM subscriptions
WHERE status = 'active'
  AND next_billing_date <= NOW()
  AND auto_renew = true;
```

### 3. Recalculate Current Pricing (FIRST)
For each due subscription, the system recalculates pricing:

```python
# Get current product variant prices (not historical)
variants = get_variants(subscription.variant_ids)
for variant in variants:
    current_price = variant.current_price  # Uses sale_price if available

# Get current shipping cost from database
shipping_methods = get_active_shipping_methods()
shipping_cost = find_matching_method(subscription.delivery_type)

# Calculate current tax
tax_service = TaxService(db)
tax_rate = await tax_service.get_tax_rate(country, state)
tax_amount = (subtotal + shipping_cost) * tax_rate

# Apply discount if exists
if subscription.discount_code:
    discount = get_promocode(subscription.discount_code)
    if discount.discount_type == "percentage":
        discount_amount = subtotal * (discount.value / 100)
    else:
        discount_amount = discount.value

# Calculate total
total = subtotal + shipping_cost + tax_amount - discount_amount
```

**Update subscription current fields:**
```python
subscription.current_variant_prices = variant_prices
subscription.current_shipping_amount = shipping_cost
subscription.current_tax_amount = tax_amount
subscription.current_tax_rate = tax_rate
await db.commit()  # Save to database
```

### 4. Payment Processing (SECOND - uses current prices)
Process payment using the newly calculated current prices:

```python
# Get user's default payment method
payment_method = get_default_payment_method(user_id)

# Process payment via Stripe using CURRENT prices
payment_service = PaymentService(db)
payment_result = await payment_service.process_payment_idempotent(
    user_id=subscription.user_id,
    order_id=order_id,
    amount=current_total,  # Current price, not historical
    payment_method_id=payment_method.id,
    idempotency_key=f"subscription_{subscription.id}_{order_id}"
)
```

**If payment fails:**
- Subscription status → `payment_failed`
- Error stored in `last_payment_error`
- NO order created
- NO inventory updated
- Process stops here

**If payment succeeds:**
- Continue to order creation

### 5. Order Creation (ONLY after successful payment)
```python
order = Order(
    id=order_id,  # Same ID as payment
    order_number=f"SUB-{timestamp}-{uuid}",
    user_id=subscription.user_id,
    order_status=OrderStatus.CONFIRMED,  # Already paid
    payment_status=PaymentStatus.PAID,   # Payment succeeded
    fulfillment_status=FulfillmentStatus.UNFULFILLED,
    subtotal=current_subtotal,           # Current prices
    tax_amount=current_tax_amount,       # Current tax
    shipping_cost=current_shipping_cost, # Current shipping
    discount_amount=current_discount,    # Current discount
    total_amount=current_total,          # Current total
    subscription_id=subscription.id      # Links to subscription
)
```

### 6. Order Items Creation
```python
for variant_price in current_variant_prices:
    order_item = OrderItem(
        order_id=order.id,
        variant_id=variant_price["id"],
        quantity=variant_price["qty"],
        price_per_unit=variant_price["price"],  # Current price
        total_price=variant_price["price"] * variant_price["qty"]
    )
```

### 7. Inventory Update
For each product in the order:

```python
from services.inventory import InventoryService

inventory_service = InventoryService(db)
for variant_price in current_variant_prices:
    adjustment = StockAdjustmentCreate(
        variant_id=variant_price["id"],
        quantity_change=-variant_price["qty"],
        reason=f"Subscription order: {order.order_number}"
    )
    await inventory_service.adjust_stock(adjustment, commit=False)
```

This happens atomically in the same database transaction.

### 8. Subscription Update
```python
# Update billing dates based on cycle
if billing_cycle == "weekly":
    next_billing_date = current_date + 7 days
elif billing_cycle == "monthly":
    next_billing_date = current_date + 30 days
elif billing_cycle == "yearly":
    next_billing_date = current_date + 365 days

subscription.status = "active"
subscription.next_billing_date = next_billing_date
subscription.last_payment_error = None

# Update metadata
subscription.subscription_metadata["last_order_created"] = now
subscription.subscription_metadata["orders_created_count"] += 1
```

### 9. Email Notification
Send order confirmation email via ARQ background task:

```python
from services.email import EmailService

email_service = EmailService(db)
await email_service.send_order_confirmation(
    user_email=user.email,
    order_number=order.order_number,
    order_id=order.id
)
```

## Database Schema

### Subscriptions Table
```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- 'active', 'payment_failed', 'cancelled', 'paused'
    currency VARCHAR(3) DEFAULT 'USD',
    billing_cycle VARCHAR(20),     -- 'weekly', 'monthly', 'yearly'
    auto_renew BOOLEAN DEFAULT true,
    
    -- Billing dates
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    next_billing_date TIMESTAMP,
    cancelled_at TIMESTAMP,
    paused_at TIMESTAMP,
    pause_reason TEXT,
    last_payment_error TEXT,
    
    -- Payment info
    payment_gateway VARCHAR(50),
    payment_reference VARCHAR(255),
    
    -- Delivery info
    delivery_type VARCHAR(50) DEFAULT 'standard',
    delivery_address_id UUID,
    
    -- Historical prices (never change)
    price_at_creation FLOAT,
    variant_prices_at_creation JSONB,
    shipping_amount_at_creation FLOAT,
    tax_amount_at_creation FLOAT,
    tax_rate_at_creation FLOAT,
    
    -- Current prices (updated each billing cycle)
    current_variant_prices JSONB,
    current_shipping_amount FLOAT,
    current_tax_amount FLOAT,
    current_tax_rate FLOAT,
    
    -- Products & variants
    variant_ids JSONB,  -- ["uuid1", "uuid2"]
    subscription_metadata JSONB,  -- {"variant_quantities": {"uuid1": 2}}
    
    -- Discount fields
    discount_id UUID,
    discount_type VARCHAR(20),  -- 'percentage' or 'fixed'
    discount_value FLOAT,
    discount_code VARCHAR(50),
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (delivery_address_id) REFERENCES addresses(id),
    FOREIGN KEY (discount_id) REFERENCES promocodes(id)
);
```

### Orders Table
```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    order_number VARCHAR(50) UNIQUE,
    user_id UUID NOT NULL,
    subscription_id UUID,          -- Links to subscription if recurring
    order_status VARCHAR(50),      -- 'confirmed', 'shipped', 'delivered'
    payment_status VARCHAR(50),    -- 'paid', 'failed'
    fulfillment_status VARCHAR(50), -- 'unfulfilled', 'fulfilled'
    source VARCHAR(50),            -- 'API', 'WEB', etc.
    
    subtotal DECIMAL(10, 2),
    tax_amount DECIMAL(10, 2),
    shipping_cost DECIMAL(10, 2),
    discount_amount DECIMAL(10, 2),
    total_amount DECIMAL(10, 2),
    currency VARCHAR(3),
    
    shipping_method VARCHAR(50),
    shipping_address JSONB,
    billing_address JSONB,
    
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);
```

## Payment Flow Guarantee

The system ensures **payment happens BEFORE order creation**:

```python
# ❌ OLD WAY (WRONG)
create_order()
update_inventory()
process_payment()  # If this fails, order already exists!

# ✅ NEW WAY (CORRECT)
# Step 1: Recalculate current pricing
pricing = recalculate_current_pricing(subscription)

# Step 2: Process payment FIRST
payment_result = process_payment(pricing["total"])

# Step 3: Only proceed if payment succeeded
if payment_result.status == "succeeded":
    create_order(pricing)
    create_order_items(pricing)
    update_inventory()
    update_subscription_billing_dates()
    send_confirmation_email()
else:
    mark_subscription_failed()
    # No order created, no inventory updated
```

## Pricing Example

**At Subscription Creation (January 1st):**
```json
{
  "price_at_creation": 16.50,
  "variant_prices_at_creation": [
    {"id": "uuid1", "price": 10.00, "qty": 1}
  ],
  "shipping_amount_at_creation": 5.00,
  "tax_amount_at_creation": 1.50,
  "tax_rate_at_creation": 0.10
}
```

**At Billing Time (February 1st):**
```json
{
  "current_variant_prices": [
    {"id": "uuid1", "price": 12.00, "qty": 1}  // Price increased!
  ],
  "current_shipping_amount": 6.00,  // Shipping cost updated!
  "current_tax_amount": 2.16,       // Tax recalculated!
  "current_tax_rate": 0.12          // Tax rate changed!
}
```

**Customer is charged:** $20.16 (current prices, not historical $16.50)

## Error Handling

### Payment Failures
Common reasons:
- Insufficient funds
- Expired card
- Card declined
- Authentication required

When payment fails:
1. Subscription status → `payment_failed`
2. Error message stored in `last_payment_error`
3. User notified via email
4. Admin can see failed subscriptions in dashboard
5. User can update payment method and retry
6. **NO order is created**
7. **NO inventory is updated**

### Inventory Issues
If inventory is insufficient:
- Payment is NOT processed
- Subscription remains active
- Next billing date unchanged
- Admin notified of low stock

### System Errors
If system error occurs:
- Transaction rolled back
- No changes persisted
- Error logged
- Admin notified

## Monitoring

### Check Subscription Processing
```sql
-- View recent subscription orders
SELECT 
    o.order_number,
    o.created_at,
    o.payment_status,
    o.total_amount,
    s.billing_cycle,
    s.next_billing_date
FROM orders o
JOIN subscriptions s ON o.subscription_id = s.id
WHERE o.created_at >= NOW() - INTERVAL '7 days'
ORDER BY o.created_at DESC;
```

### Check Failed Subscriptions
```sql
SELECT 
    id,
    user_id,
    name,
    status,
    last_payment_error,
    next_billing_date
FROM subscriptions
WHERE status = 'payment_failed'
ORDER BY updated_at DESC;
```

### Check Price Differences
```sql
-- Compare historical vs current prices
SELECT 
    id,
    name,
    price_at_creation,
    (current_variant_prices::jsonb->0->>'price')::float as current_price,
    ((current_variant_prices::jsonb->0->>'price')::float - price_at_creation) as price_difference
FROM subscriptions
WHERE status = 'active';
```

### Check ARQ Worker Status
```bash
# Check if worker is running
ps aux | grep arq

# Check worker logs
tail -f backend/logs/banwee.log | grep subscription

# Check Redis connection
redis-cli ping
```

## Deployment

### Two-Server Setup

**Server 1: FastAPI Backend**
```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Server 2: ARQ Worker**
```bash
cd backend
python start_arq_worker.py
```

Both servers:
- Connect to same PostgreSQL database
- Connect to same Redis instance
- Can run on same machine or different machines

### Systemd Service (ARQ Worker)
```ini
[Unit]
Description=ARQ Worker for Subscription Processing
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/backend
ExecStart=/path/to/venv/bin/python start_arq_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Testing

### Manual Test - Process All Due Subscriptions
```python
import asyncio
from backend.services.subscriptions.scheduler import SubscriptionScheduler
from backend.core.db import get_db

async def test_subscriptions():
    async for db in get_db():
        scheduler = SubscriptionScheduler(db)
        result = await scheduler.process_due_subscriptions()
        print(result)
        break

asyncio.run(test_subscriptions())
```

### Test Specific Subscription
```python
import asyncio
from backend.services.subscriptions.scheduler import SubscriptionScheduler
from backend.core.db import get_db
from uuid import UUID

async def test_subscription(subscription_id: str):
    async for db in get_db():
        scheduler = SubscriptionScheduler(db)
        
        # Get subscription
        from models.subscriptions import Subscription
        from sqlalchemy import select
        result = await db.execute(
            select(Subscription).where(Subscription.id == UUID(subscription_id))
        )
        subscription = result.scalar_one_or_none()
        
        if subscription:
            result = await scheduler.process_subscription(subscription)
            print(result)
        break

asyncio.run(test_subscription("your-uuid-here"))
```

### Test Price Recalculation
```python
import asyncio
from backend.services.subscriptions.service import SubscriptionService
from backend.core.db import get_db
from uuid import UUID

async def test_pricing(subscription_id: str):
    async for db in get_db():
        service = SubscriptionService(db)
        
        # Get subscription
        subscription = await service.get_by_id(UUID(subscription_id))
        
        if subscription:
            print("Historical prices:")
            print(f"  Total: ${subscription.price_at_creation}")
            print(f"  Variants: {subscription.variant_prices_at_creation}")
            
            # Recalculate current pricing
            pricing = await service.recalculate_current_pricing(subscription)
            
            print("\nCurrent prices:")
            print(f"  Total: ${pricing['total']}")
            print(f"  Variants: {pricing['variant_prices']}")
            print(f"  Shipping: ${pricing['shipping']}")
            print(f"  Tax: ${pricing['tax']}")
        break

asyncio.run(test_pricing("your-uuid-here"))
```

## Configuration

### Change Processing Time
Edit `backend/core/arq_worker.py`:

```python
cron_jobs = [
    cron(
        process_subscription_orders_task,
        hour=2,    # Change this (0-23)
        minute=0,  # Change this (0-59)
        run_at_startup=False,
        unique=True,
        timeout=600,
    ),
]
```

### Change Billing Cycles
Supported cycles:
- `weekly` - Every 7 days
- `monthly` - Every 30 days
- `yearly` - Every 365 days

## Best Practices

1. **Always run ARQ worker** - Set up as systemd service for auto-restart
2. **Monitor failed payments** - Check daily for payment_failed subscriptions
3. **Keep payment methods updated** - Remind users before card expiry
4. **Test regularly** - Run manual tests monthly
5. **Backup before processing** - Ensure database backups before 2 AM
6. **Use UTC timezone** - All times in UTC to avoid confusion
7. **Set up alerts** - Get notified when subscriptions fail
8. **Monitor price changes** - Track when current prices differ significantly from historical
9. **Run on separate server** - ARQ worker should run independently from FastAPI
10. **Dynamic shipping costs** - Never hardcode shipping costs, always fetch from database

## Summary

The subscription system:
- ✅ Runs automatically via ARQ worker (separate server)
- ✅ Stores historical prices at creation (never change)
- ✅ Calculates current prices dynamically at billing time
- ✅ Fetches shipping costs from database (no hardcoded values)
- ✅ Processes payments BEFORE creating orders
- ✅ Creates actual orders with order items
- ✅ Updates inventory atomically
- ✅ Handles failures gracefully
- ✅ Sends confirmation emails
- ✅ Requires NO manual intervention

**The ARQ worker MUST be running on a separate server for subscriptions to work!**

**Customers are always charged current prices, not historical prices!**
