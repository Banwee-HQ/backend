# API Reference (auto-generated snapshot)

Base URL: `/v1`

All authenticated endpoints require a Bearer token in the `Authorization` header.

This file is an auto-generated snapshot of route decorators as of 2026-04-10. It groups endpoints by area — use `postman_collection.json` for runnable examples.

---

## Auth / Accounts

- POST `/auth/register/` — register a new user
- POST `/auth/login/` — login (returns access + refresh tokens)
- POST `/auth/refresh/` — refresh access token
- POST `/auth/revoke/` — revoke refresh token
- POST `/auth/logout/` — logout current user (requires auth)
- GET `/auth/me/` — current user (requires auth)
- GET `/auth/verify-email/` — verify email token (query param `token`)
- POST `/auth/resend-verification/`
- POST `/auth/forgot-password/`
- POST `/auth/reset-password/`
- PATCH `/auth/me/` — update current user
- PUT `/auth/me/password/` — change password
- DELETE `/auth/me/`

OAuth endpoints:
- GET `/auth/social/{provider}/login/`
- GET `/auth/social/{provider}/callback/`

---

## Users / Admin

- GET `/users/me/`
- GET `/users/profile/`
- POST `/users/` — create user (admin)
- GET `/users/` — list users (admin)
- GET `/users/{user_id}/`
- PATCH `/users/{user_id}/`
- PUT `/users/{user_id}/status/`
- POST `/users/{user_id}/reset-password/`
- POST `/users/{user_id}/deactivate/`
- POST `/users/{user_id}/activate/`
- PUT `/users/{user_id}/verify/`
- GET `/users/{user_id}/activity/`

Addresses:
- POST `/addresses/` — create address
- GET `/addresses/` — list
- GET `/addresses/{address_id}/`
- PATCH `/addresses/{address_id}/`
- DELETE `/addresses/{address_id}/`

---

## Catalog

Products:
- GET `/products/home/`
- GET `/products/` — list/search (query: `q, page, limit, category`)
- GET `/products/featured/`, `/products/deals/`
- GET `/products/{product_id}/`
- POST `/products/` — create (admin)
- PUT `/products/{product_id}/` — update (admin)
- DELETE `/products/{product_id}/`
- POST `/products/{product_id}/variants/`
- GET `/products/{product_id}/variants/`
- GET `/products/variants/{variant_id}/`
- PATCH `/products/variants/{variant_id}/`
- DELETE `/products/variants/{variant_id}/`
- Image endpoints: POST `/products/variants/{variant_id}/images/`, GET `/products/images/{image_id}/`, PATCH/DELETE `/products/images/{image_id}/`
- PATCH `/products/{product_id}/moderate/` — moderate product (admin)
- PATCH `/products/{product_id}/feature/` — feature product (admin)

Reviews:
- GET/POST `/reviews/`
- GET `/reviews/{review_id}/`
- GET `/reviews/product/{product_id}/`update

Inventory:
- POST `/inventory/locations/` — create location (admin)
- GET `/inventory/locations/`, GET `/inventory/locations/{location_id}/`
- PATCH `/inventory/locations/{location_id}/`
- DELETE `/inventory/locations/{location_id}/`
- POST `/inventory/` — create inventory record (admin)
- GET `/inventory/`, GET `/inventory/{inventory_id}/`
- PATCH `/inventory/{inventory_id}/`
- DELETE `/inventory/{inventory_id}/`
- POST `/inventory/adjustments/`, GET `/inventory/adjustments/{adjustment_id}/`, GET `/inventory/adjustments/`

---

## Cart

- GET `/cart/`
- POST `/cart/add/`
- PUT `/cart/items/{id}/`
- DELETE `/cart/items/{id}/`
- POST `/cart/promocode/`, DELETE `/cart/promocode/`
- POST `/cart/clear/`
- POST `/cart/calculate/`
- GET `/cart/checkout-summary/`

---

## Orders

- POST `/orders/checkout/` — place order
- GET `/orders/`, GET `/orders/{order_id}/`
- PUT `/orders/{order_id}/cancel/` — cancel
- GET `/orders/{order_id}/invoice/`
- GET `/orders/{order_id}/tracking/` and other tracking endpoints under shipping tracking

---

## Payments & Webhooks

- GET `/payments/` — list transactions
- GET `/payments/methods/`, POST `/payments/methods/`, DELETE `/payments/methods/{id}/`, PATCH `/payments/methods/{id}/default/`
- GET `/payments/failures/`, POST `/payments/failures/{payment_intent_id}/retry/`
- POST `/webhooks/stripe/` — Stripe webhook endpoint
- GET `/webhooks/health/` — Webhook health check

---

## Subscriptions

- POST `/subscriptions/` — create
- POST `/subscriptions/calculate-cost/`
- GET `/subscriptions/`, GET `/subscriptions/{subscription_id}/`
- PATCH `/subscriptions/{subscription_id}/`
- POST `/subscriptions/{subscription_id}/cancel/`, POST `/subscriptions/{subscription_id}/pause/`, POST `/subscriptions/{subscription_id}/resume/`
- POST `/subscriptions/{subscription_id}/products/` — add products
- DELETE `/subscriptions/{subscription_id}/products/` — remove products
- DELETE `/subscriptions/{subscription_id}/products/{product_id}/` — remove single product
- POST `/subscriptions/trigger-order-processing/` — trigger processing (admin)
- GET `/subscriptions/plans/` — list subscription plans

---

## Refunds & Promocodes

- Refunds: POST `/refunds/`, GET `/refunds/{refund_id}/`, PATCH `/refunds/{refund_id}/`, PUT `/refunds/{refund_id}/status/`
- Promocodes: GET `/promocodes/`, GET `/promocodes/{id}/`, POST `/promocodes/`, PATCH `/promocodes/{id}/`, DELETE `/promocodes/{id}/`, POST `/promocodes/validate/`, POST `/promocodes/trigger-cleanup/`

---

## Shipping & Shipping Tracking

- GET `/shipping/methods/`, GET `/shipping/methods/{method_id}/`
- POST `/shipping/methods/` (admin)
- PATCH `/shipping/methods/{method_id}/` (admin)
- DELETE `/shipping/methods/{method_id}/` (admin)
- POST `/shipping/calculate/`
- POST `/shipping/track/`
- Shipping tracking endpoints: POST `/shipping-tracking/shipments/`, GET `/shipping-tracking/shipments/{shipment_id}/`, POST `/shipping-tracking/track/`, POST `/shipping-tracking/webhooks/{carrier}/`

---

## Tax

- POST `/tax/calculate/`
- GET `/tax/rates/` — list tax rates
- POST `/tax/rates/` — create tax rate (admin)
- GET `/tax/rates/{tax_rate_id}/` — get tax rate
- PATCH `/tax/rates/{tax_rate_id}/` — update tax rate (admin)
- DELETE `/tax/rates/{tax_rate_id}/` — delete tax rate (admin)

---

## Admin / Analytics

- Large set of endpoints under `/admin/*` for analytics, users, products, inventory sync, tax rates, payments and more. Key endpoints include `/admin/dashboard`, `/admin/stats`, `/admin/payments`, `/admin/inventory`, `/admin/subscriptions` and `/admin/analytics/*`.

---

## System

- GET `/` — health
- Contact messages under `/contact-messages/` (POST, GET, GET/{id}, PATCH, DELETE)

---

## Analytics

- POST `/analytics/track/` — track event
- GET `/analytics/dashboard/` — dashboard
- GET `/analytics/simple-dashboard/` — simple dashboard
- GET `/analytics/conversion-rates/` — conversion rates
- GET `/analytics/cart-abandonment/` — cart abandonment
- GET `/analytics/time-to-purchase/` — time to purchase
- GET `/analytics/refund-rates/` — refund rates
- GET `/analytics/repeat-customers/` — repeat customers
- GET `/analytics/sales-trend/` — sales trend
- GET `/analytics/sales-overview/` — sales overview
- GET `/analytics/sales/` — sales analytics
- GET `/analytics/users/` — user analytics
- GET `/analytics/products/` — product analytics
- GET `/analytics/orders/` — order analytics
- GET `/analytics/revenue/` — revenue analytics
- GET `/analytics/kpis/` — KPIs
- GET `/analytics/stats/` — stats
- GET `/analytics/dashboard/admin/` — admin dashboard
- GET `/analytics/export/orders/` — export orders
- GET `/analytics/export/subscriptions/` — export subscriptions

---

Notes:
- This snapshot is intended as a developer-facing quick reference. For executable examples and request bodies use `postman_collection.json` in the repository root.


### PUT /orders/{id}/cancel/
Cancel order. 🔒

### GET /orders/{id}/tracking/
Get order tracking. 🔒

### POST /orders/{id}/refund/
Request refund. 🔒

### POST /orders/{id}/reorder/
Reorder. 🔒

### GET /orders/{id}/invoice/
Download invoice. 🔒

### POST /orders/{id}/notes/
Add order note. 🔒

### GET /orders/{id}/notes/
Get order notes. 🔒

---

## Payments

### GET /payments/
List payment transactions. 🔒

### GET /payments/methods/
List payment methods. 🔒

### POST /payments/methods/
Add payment method. 🔒

**Body:** `{ stripe_payment_method_id, type, provider, last_four, expiry_month, expiry_year, is_default? }`

### DELETE /payments/methods/{id}/
Delete payment method. 🔒

### PATCH /payments/methods/{id}/
Update payment method. 🔒

### PATCH /payments/methods/{id}/default/
Set default payment method. 🔒

### GET /payments/failures/{payment_intent_id}/status/
Get payment failure status. 🔒

### POST /payments/failures/{payment_intent_id}/retry/
Retry failed payment. 🔒

### GET /payments/failures/
Get user's failed payments. 🔒

---

## Subscriptions

### POST /subscriptions/calculate-cost/
Calculate subscription cost. 🔒

**Body:** `{ variant_ids, billing_cycle?, currency?, discount_code? }`

### POST /subscriptions/
Create subscription. 🔒

**Body:** `{ name, variant_ids, variant_quantities?, delivery_type?, delivery_address_id?, billing_cycle?, currency?, discount_code? }`

### GET /subscriptions/
List user subscriptions. 🔒

**Query:** `page?, limit?`

### GET /subscriptions/{id}/
Get subscription by ID. 🔒

### PATCH /subscriptions/{id}/
Update subscription. 🔒

### POST /subscriptions/{id}/cancel/
Cancel subscription. 🔒

**Body:** `{ reason? }`

### DELETE /subscriptions/{id}/
Delete subscription. 🔒

### POST /subscriptions/{id}/pause/
Pause subscription. 🔒

**Body:** `{ pause_reason? }`

### POST /subscriptions/{id}/resume/
Resume subscription. 🔒

### POST /subscriptions/{id}/products/
Add products to subscription. 🔒

**Body:** `{ products: [{variant_id, quantity}] }`

### DELETE /subscriptions/{id}/products/
Remove products from subscription. 🔒

**Body:** `{ variant_ids: string[] }`

### DELETE /subscriptions/{id}/products/{product_id}/
Remove single product. 🔒

### POST /subscriptions/trigger-order-processing/
Trigger order processing. 🔒 Admin

---

## Shipping

### GET /shipping/methods/
List shipping methods.

### GET /shipping/methods/{id}/
Get shipping method by ID.

### POST /shipping/methods/
Create shipping method. 🔒 Admin

**Body:** `{ name, description?, price, estimated_days, is_active? }`

### PATCH /shipping/methods/{id}/
Update shipping method. 🔒 Admin

### DELETE /shipping/methods/{id}/
Delete shipping method. 🔒 Admin

### POST /shipping/calculate/
Calculate shipping cost.

**Body:** `{ address_id, method_id, items }`

---

## Shipping Tracking

### POST /shipping-tracking/shipments/
Create shipment. 🔒 Admin

### GET /shipping-tracking/shipments/{id}/
Get shipment by ID. 🔒

### POST /shipping-tracking/track/
Track shipment.

**Body:** `{ tracking_number, carrier? }`

---

## Promocodes

### GET /promocodes/
List promocodes. 🔒 Admin

### GET /promocodes/{id}/
Get promocode by ID. 🔒 Admin

### POST /promocodes/
Create promocode. 🔒 Admin

**Body:** `{ code, discount_type, discount_value, min_order_amount?, max_uses?, expires_at?, is_active? }`

### PATCH /promocodes/{id}/
Update promocode. 🔒 Admin

### DELETE /promocodes/{id}/
Delete promocode. 🔒 Admin

### POST /promocodes/validate/
Validate promocode. 🔒

### POST /promocodes/trigger-cleanup/
Trigger cleanup. 🔒 Admin

---

## Refunds

### POST /refunds/
Create refund. 🔒

### GET /refunds/{id}/
Get refund by ID. 🔒

### PATCH /refunds/{id}/
Update refund. 🔒

### PUT /refunds/{id}/status/
Update refund status. 🔒 Admin

---

## Tax

### POST /tax/calculate/
Calculate tax.

**Body:** `{ country_code, state?, amount }`

### GET /tax/rates/
List tax rates. 🔒 Admin

### GET /tax/rates/{tax_rate_id}/
Get tax rate by ID. 🔒 Admin

### POST /tax/rates/
Create tax rate. 🔒 Admin

### PATCH /tax/rates/{tax_rate_id}/
Update tax rate. 🔒 Admin

### DELETE /tax/rates/{tax_rate_id}/
Delete tax rate. 🔒 Admin

---

## Webhooks

### POST /webhooks/stripe/
Stripe webhook handler.

### GET /webhooks/health/
Webhook health check.

---

## Contact Messages

### POST /contact-messages/
Submit contact message.

**Body:** `{ name, email, subject, message }`

### GET /contact-messages/
List contact messages. 🔒 Admin

### GET /contact-messages/{id}/
Get contact message by ID. 🔒 Admin

### PATCH /contact-messages/{id}/
Update contact message status. 🔒 Admin

### DELETE /contact-messages/{id}/
Delete contact message. 🔒 Admin
