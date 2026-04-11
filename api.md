# API Reference (auto-generated snapshot)

Base URL: `/v1`

All authenticated endpoints require a Bearer token in the `Authorization` header.

This file is an auto-generated snapshot of route decorators as of 2026-04-10. It groups endpoints by area — use `postman_collection.json` for runnable examples.

---

## Auth / Accounts

- POST `/auth/register` — register a new user
- POST `/auth/login` — login (returns access + refresh tokens)
- POST `/auth/refresh` — refresh access token
- POST `/auth/revoke` — revoke refresh token
- POST `/auth/logout` — logout current user (requires auth)
- GET `/auth/me` — current user (requires auth)
- GET `/auth/verify-email` — verify email token (query param `token`)
- POST `/auth/resend-verification`
- POST `/auth/forgot-password`
- POST `/auth/reset-password`
- PATCH `/auth/me` — update current user
- PATCH `/auth/me/password` — change password
- DELETE `/auth/me`

OAuth endpoints:
- GET `/accounts/{provider}/login`
- GET `/accounts/callback/{provider}`

---

## Users / Admin

- GET `/users/me`
- GET `/users/profile`
- POST `/users` — create user (admin)
- GET `/users` — list users (admin)
- GET `/users/{user_id}`
- PATCH/PUT `/users/{user_id}`
- PUT `/users/{user_id}/status`
- POST `/users/{user_id}/reset-password`
- POST `/users/{user_id}/deactivate`
- POST `/users/{user_id}/activate`

Addresses:
- POST `/accounts/addresses` — create address
- GET `/accounts/addresses` — list
- GET `/accounts/addresses/{address_id}`
- PATCH `/accounts/addresses/{address_id}`
- DELETE `/accounts/addresses/{address_id}`

---

## Catalog

Products:
- GET `/products/home`
- GET `/products` — list/search (query: `q, page, limit, category`)
- GET `/products/featured`, `/products/deals`
- GET `/products/{product_id}`
- POST `/products` — create (admin)
- PATCH `/products/{product_id}` — update (admin)
- DELETE `/products/{product_id}`
- POST `/products/{product_id}/variants`
- GET `/products/{product_id}/variants`
- GET `/products/variants/{variant_id}`
- PATCH `/products/variants/{variant_id}`
- DELETE `/products/variants/{variant_id}`
- Image endpoints: POST `/products/variants/{variant_id}/images`, GET `/products/images/{image_id}`, PATCH/DELETE `/products/images/{image_id}`

Reviews & Wishlist:
- GET/POST `/reviews`
- GET `/reviews/{review_id}`
- GET `/reviews/product/{product_id}`
- Wishlist endpoints under `/wishlist` — add/get/remove/update

Inventory:
- GET `/inventory/check-stock/{variant_id}`
- POST `/inventory/check-stock/bulk`
- POST `/inventory/locations` — create location (admin)
- GET `/inventory/locations`, GET `/inventory/locations/{location_id}`
- PATCH/PUT/DELETE `/inventory/locations/{location_id}`
- POST `/inventory` — create inventory record (admin)
- GET `/inventory`, GET `/inventory/{inventory_id}`
- PATCH/PUT/DELETE `/inventory/{inventory_id}`
- POST `/inventory/adjustments`, GET `/inventory/adjustments/{adjustment_id}`, GET `/inventory/adjustments`

---

## Cart

- GET `/cart`
- POST `/cart/add`
- PUT `/cart/items/{id}`
- DELETE `/cart/items/{id}`
- POST `/cart/promocode`, DELETE `/cart/promocode`
- GET `/cart/count`
- POST `/cart/validate`, `/cart/calculate`, `/cart/shipping-options`
- POST `/cart/clear`, GET `/cart/checkout-summary`

---

## Orders

- POST `/orders` — create
- POST `/orders/checkout/validate` — validate checkout
- POST `/orders/checkout` — place order
- GET `/orders`, GET `/orders/{order_id}`
- POST/PATCH `/orders/{order_id}/cancel` — cancel
- GET `/orders/{order_id}/invoice`
- GET `/orders/{order_id}/tracking` and other tracking endpoints under shipping tracking

Admin order endpoints (`/admin/orders`):
- GET `/admin/orders`, GET `/admin/orders/{order_id}`
- PUT `/admin/orders/{order_id}/ship`
- PUT/PATCH `/admin/orders/{order_id}/status`
- GET `/admin/orders/export`, GET `/admin/orders/statistics`, GET `/admin/orders/all`

---

## Payments & Webhooks

- GET `/payments` — list transactions
- GET `/payments/methods`, POST `/payments/methods`, DELETE `/payments/methods/{id}`, PUT `/payments/methods/{id}/default`
- GET `/payments/failures/user/failed-payments`, POST `/payments/failures/{id}/retry`
- POST `/commerce/webhooks/stripe` — Stripe webhook endpoint
- Order payment flows: POST `/orders/create-payment-intent` and integrations in services/commerce/payments.py

---

## Subscriptions

- POST `/subscriptions` — create
- POST `/subscriptions/calculate-cost`
- GET `/subscriptions`, GET `/subscriptions/{subscription_id}`
- PUT/PATCH `/subscriptions/{subscription_id}`
- POST `/subscriptions/{subscription_id}/cancel`, POST `/subscriptions/{subscription_id}/pause`, POST `/subscriptions/{subscription_id}/resume`
- Endpoints to add/remove products, set quantities, apply/remove discounts

---

## Refunds & Promocodes

- Refunds: POST `/refunds/orders/{order_id}/request`, GET `/refunds/orders/{order_id}/eligibility`, GET `/refunds`, GET `/refunds/{refund_id}`, PUT `/refunds/{refund_id}/cancel`, GET `/refunds/stats/summary`
- Promocodes: GET `/promocodes`, GET `/promocodes/{id}`, POST `/promocodes`, PUT `/promocodes/{id}`, DELETE `/promocodes/{id}`

---

## Shipping & Shipping Tracking

- GET `/shipping/methods`, GET `/shipping/methods/{method_id}`
- POST/PATCH/DELETE `/shipping/methods` (admin)
- POST `/shipping/calculate`
- Shipping tracking endpoints: POST `/shipping_tracking/shipments`, GET `/shipping_tracking/shipments/{shipment_id}`, GET `/shipping_tracking/orders/{order_id}/shipments`, POST `/shipping_tracking/track`, POST `/shipping_tracking/webhooks/{carrier}`

---

## Tax

- POST `/tax/calculate`
- Admin tax rates under `/admin/tax-rates` (list, create, update, delete, bulk-update)

---

## Admin / Analytics

- Large set of endpoints under `/admin/*` for analytics, users, products, inventory sync, tax rates, payments and more. Key endpoints include `/admin/dashboard`, `/admin/stats`, `/admin/payments`, `/admin/inventory`, `/admin/subscriptions` and `/admin/analytics/*`.

---

## System

- GET `/` — health
- Contact messages under `/system/contact-messages` (POST, GET, GET/{id}, PATCH, DELETE)

---

Notes:
- This snapshot is intended as a developer-facing quick reference. For executable examples and request bodies use `postman_collection.json` in the repository root.


### PUT /orders/{id}/cancel
Cancel order. 🔒

### GET /orders/{id}/tracking
Get order tracking. 🔒

### GET /orders/track/{id}
Public order tracking.

### POST /orders/{id}/refund
Request refund. 🔒

### POST /orders/{id}/reorder
Reorder. 🔒

### GET /orders/{id}/invoice
Download invoice. 🔒

### POST /orders/{id}/notes
Add order note. 🔒

### GET /orders/{id}/notes
Get order notes. 🔒

---

## Payments

### GET /payments
List payment transactions. 🔒

### GET /payments/methods
List payment methods. 🔒

### POST /payments/methods
Add payment method. 🔒

**Body:** `{ stripe_payment_method_id, type, provider, last_four, expiry_month, expiry_year, is_default? }`

### DELETE /payments/methods/{id}
Delete payment method. 🔒

### PUT /payments/methods/{id}
Update payment method. 🔒

### PUT /payments/methods/{id}/default
Set default payment method. 🔒

### POST /payments/intents
Create payment intent. 🔒

### POST /payments/intents/{id}/confirm
Confirm payment intent. 🔒

### POST /payments/process
Process payment. 🔒

### GET /payments/transactions
Get transaction history. 🔒

### POST /payments/refunds/{id}
Process refund. 🔒 Admin

### GET /payments/failures/{id}/status
Get payment failure status. 🔒

### POST /payments/failures/{id}/retry
Retry failed payment. 🔒

### GET /payments/failures/user/failed-payments
Get user's failed payments. 🔒

### POST /payments/failures/{id}/abandon
Abandon failed payment. 🔒

### GET /payments/failures/analytics/failure-reasons
Get failure analytics. 🔒 Admin

---

## Subscriptions

### POST /subscriptions/calculate-cost
Calculate subscription cost. 🔒

**Body:** `{ variant_ids, billing_cycle?, currency?, discount_code? }`

### POST /subscriptions
Create subscription. 🔒

**Body:** `{ name, variant_ids, variant_quantities?, delivery_type?, delivery_address_id?, billing_cycle?, currency?, discount_code? }`

### GET /subscriptions
List user subscriptions. 🔒

**Query:** `page?, limit?`

### GET /subscriptions/{id}
Get subscription by ID. 🔒

### PUT /subscriptions/{id}
Update subscription. 🔒

### POST /subscriptions/{id}/cancel
Cancel subscription. 🔒

**Body:** `{ reason? }`

### DELETE /subscriptions/{id}
Delete subscription. 🔒

### POST /subscriptions/{id}/pause
Pause subscription. 🔒

**Body:** `{ pause_reason? }`

### POST /subscriptions/{id}/resume
Resume subscription. 🔒

### PATCH /subscriptions/{id}/auto-renew
Toggle auto-renew. 🔒

**Body:** `{ auto_renew: boolean }`

### POST /subscriptions/{id}/products
Add products to subscription. 🔒

**Body:** `{ variant_ids: string[] }`

### DELETE /subscriptions/{id}/products
Remove products from subscription. 🔒

**Body:** `{ variant_ids: string[] }`

### DELETE /subscriptions/{id}/products/{product_id}
Remove single product. 🔒

### PUT /subscriptions/{id}/products/quantity
Set variant quantity. 🔒

**Body:** `{ variant_id, quantity }`

### PATCH /subscriptions/{id}/products/quantity
Change variant quantity. 🔒

**Body:** `{ variant_id, change }`

### GET /subscriptions/{id}/products/quantities
Get variant quantities. 🔒

### POST /subscriptions/{id}/process-shipment
Process shipment manually. 🔒

### POST /subscriptions/{id}/discounts
Apply discount. 🔒

**Body:** `{ discount_code }`

### DELETE /subscriptions/{id}/discounts/{discount_id}
Remove discount. 🔒

### POST /subscriptions/trigger-order-processing
Trigger order processing. 🔒 Admin

### POST /subscriptions/trigger-notifications
Trigger notifications. 🔒 Admin

---

## Shipping

### GET /shipping/methods
List shipping methods.

### GET /shipping/methods/{id}
Get shipping method by ID.

### POST /shipping/methods
Create shipping method. 🔒 Admin

**Body:** `{ name, description?, price, estimated_days, is_active? }`

### PUT /shipping/methods/{id}
Update shipping method. 🔒 Admin

### DELETE /shipping/methods/{id}
Delete shipping method. 🔒 Admin

### POST /shipping/calculate
Calculate shipping cost.

**Body:** `{ address_id, method_id, items }`

---

## Shipping Tracking

### POST /shipping-tracking/shipments
Create shipment. 🔒 Admin

### GET /shipping-tracking/shipments/{id}
Get shipment by ID. 🔒

### GET /shipping-tracking/orders/{id}/shipments
Get shipments for order. 🔒

### POST /shipping-tracking/track
Track shipment.

**Body:** `{ tracking_number, carrier? }`

### PUT /shipping-tracking/shipments/{id}/status
Update shipment status. 🔒 Admin

### GET /shipping-tracking/carriers
List supported carriers.

### POST /shipping-tracking/providers
Create tracking provider. 🔒 Admin

### GET /shipping-tracking/providers
List tracking providers. 🔒 Admin

### PUT /shipping-tracking/providers/{id}
Update tracking provider. 🔒 Admin

### DELETE /shipping-tracking/providers/{id}
Delete tracking provider. 🔒 Admin

### POST /shipping-tracking/sync/all
Sync all shipments. 🔒 Admin

### POST /shipping-tracking/webhooks/{carrier}
Carrier webhook endpoint.

---

## Promocodes

### GET /promocodes
List promocodes. 🔒 Admin

### GET /promocodes/{id}
Get promocode by ID. 🔒 Admin

### POST /promocodes
Create promocode. 🔒 Admin

**Body:** `{ code, discount_type, discount_value, min_order_amount?, max_uses?, expires_at?, is_active? }`

### PUT /promocodes/{id}
Update promocode. 🔒 Admin

### DELETE /promocodes/{id}
Delete promocode. 🔒 Admin

---

## Refunds

### POST /refunds/orders/{id}/request
Request refund for order. 🔒

**Body:** `{ reason, items? }`

### GET /refunds/orders/{id}/eligibility
Check refund eligibility. 🔒

### GET /refunds
List refunds. 🔒 Admin

### GET /refunds/{id}
Get refund by ID. 🔒

### PUT /refunds/{id}/cancel
Cancel refund. 🔒

### GET /refunds/stats/summary
Get refund stats. 🔒 Admin

### POST /refunds/process-automatic
Process automatic refunds. 🔒 Admin

---

## Tax

### POST /tax/calculate
Calculate tax.

**Body:** `{ country_code, state?, amount }`

### GET /tax/admin/tax-rates
List tax rates. 🔒 Admin

### GET /tax/admin/tax-rates/countries
List countries with tax rates. 🔒 Admin

### GET /tax/admin/tax-rates/tax-types
List tax types. 🔒 Admin

### GET /tax/admin/tax-rates/{id}
Get tax rate by ID. 🔒 Admin

### POST /tax/admin/tax-rates
Create tax rate. 🔒 Admin

### PUT /tax/admin/tax-rates/{id}
Update tax rate. 🔒 Admin

### DELETE /tax/admin/tax-rates/{id}
Delete tax rate. 🔒 Admin

### POST /tax/admin/tax-rates/bulk-update
Bulk update tax rates. 🔒 Admin

---

## Webhooks

### POST /webhooks/stripe
Stripe webhook handler.

### GET /webhooks/health
Webhook health check.

---

## Admin

### GET /admin/subscriptions
List all subscriptions. 🔒 Admin

### GET /admin/stats
Get admin stats. 🔒 Admin

### GET /admin/dashboard
Get dashboard data. 🔒 Admin

### GET /admin/orders
List all orders. 🔒 Admin

### GET /admin/orders/{id}
Get order by ID. 🔒 Admin

### PUT /admin/orders/{id}/ship
Mark order as shipped. 🔒 Admin

### PUT /admin/orders/{id}/status
Update order status. 🔒 Admin

**Body:** `{ status }`

### GET /admin/orders/{id}/invoice
Get order invoice. 🔒 Admin

### GET /admin/refunds
List all refunds. 🔒 Admin

### GET /admin/refunds/{id}
Get refund by ID. 🔒 Admin

### PUT /admin/refunds/{id}/status
Update refund status. 🔒 Admin

### GET /admin/users
List all users. 🔒 Admin

### POST /admin/users
Create user. 🔒 Admin

### GET /admin/users/{id}
Get user by ID. 🔒 Admin

### PUT /admin/users/{id}/status
Update user status. 🔒 Admin

### DELETE /admin/users/{id}
Delete user. 🔒 Admin

### POST /admin/users/{id}/reset-password
Reset user password. 🔒 Admin

### POST /admin/users/{id}/deactivate
Deactivate user. 🔒 Admin

---

## Analytics

### POST /analytics/track
Track event. 🔒

### GET /analytics/conversion-rates
Get conversion rates. 🔒 Admin

### GET /analytics/cart-abandonment
Get cart abandonment data. 🔒 Admin

### GET /analytics/time-to-purchase
Get time-to-purchase data. 🔒 Admin

### GET /analytics/refund-rates
Get refund rates. 🔒 Admin

### GET /analytics/repeat-customers
Get repeat customer data. 🔒 Admin

### GET /analytics/simple-dashboard
Get simple dashboard. 🔒 Admin

### GET /analytics/dashboard
Get full dashboard. 🔒 Admin

### GET /analytics/sales-trend
Get sales trend. 🔒 Admin

### GET /analytics/sales-overview
Get sales overview. 🔒 Admin

### GET /analytics/kpis
Get KPIs. 🔒 Admin

### GET /analytics/revenue
Get revenue data. 🔒 Admin

---

## Contact Messages

### POST /contact-messages
Submit contact message.

**Body:** `{ name, email, subject, message }`

### GET /contact-messages
List contact messages. 🔒 Admin

### GET /contact-messages/{id}
Get contact message by ID. 🔒 Admin

### PATCH /contact-messages/{id}
Update contact message status. 🔒 Admin

### DELETE /contact-messages/{id}
Delete contact message. 🔒 Admin

---

## Health

### GET /health/live
Liveness check.

### GET /health/ready
Readiness check.

### GET /health/detailed
Detailed health status.

### GET /health/dependencies
Check dependencies.

### GET /health/api-endpoints
List API endpoints.

### GET /health/metrics
Get metrics.

### GET /health/database/stats
Get database stats. 🔒 Admin

### POST /health/database/maintenance
Run database maintenance. 🔒 Admin
