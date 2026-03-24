# API Reference

Base URL: `/v1`

All authenticated endpoints require a Bearer token in the `Authorization` header.

---

## Auth

### POST /auth/register
Register a new user.

**Body:** `{ email, password, firstname, lastname }`

### POST /auth/login
Login and receive access + refresh tokens.

**Body:** `{ email, password }`

### POST /auth/refresh
Refresh access token.

**Body:** `{ refresh_token }`

### POST /auth/revoke
Revoke a refresh token.

**Body:** `{ refresh_token }`

### POST /auth/logout
Logout current user. 🔒

### GET /auth/profile
Get current user profile. 🔒

### PUT /auth/profile
Update current user profile. 🔒

**Body:** `{ firstname?, lastname?, phone? }`

### PUT /auth/change-password
Change password. 🔒

**Body:** `{ current_password, new_password }`

### GET /auth/addresses
Get user addresses. 🔒

### POST /auth/addresses
Add a new address. 🔒

**Body:** `{ street, city, state, post_code, country, is_default? }`

### PUT /auth/addresses/{id}
Update an address. 🔒

### DELETE /auth/addresses/{id}
Delete an address. 🔒

### GET /auth/verify-email
Verify email with token.

**Query:** `token`

### POST /auth/resend-verification
Resend verification email.

**Body:** `{ email }`

### POST /auth/forgot-password
Request password reset.

**Body:** `{ email }`

### POST /auth/reset-password
Reset password with token.

**Body:** `{ token, new_password }`

---

## OAuth

### GET /auth/facebook/callback
Facebook OAuth callback.

---

## Users (Admin)

### GET /users/me
Get current user. 🔒

### GET /users/profile
Get user profile. 🔒

### PUT /users/profile
Update user profile. 🔒

### GET /users/search
Search users. 🔒 Admin

**Query:** `q, page?, limit?`

### GET /users
List all users. 🔒 Admin

### POST /users
Create a user. 🔒 Admin

### GET /users/{id}
Get user by ID. 🔒 Admin

### PUT /users/{id}/status
Update user status. 🔒 Admin

### DELETE /users/{id}
Delete user. 🔒 Admin

### POST /users/{id}/reset-password
Reset user password. 🔒 Admin

### POST /users/{id}/deactivate
Deactivate user. 🔒 Admin

### GET /users/me/addresses
Get current user addresses. 🔒

### GET /users/{id}/addresses
Get user addresses. 🔒 Admin

### GET /users/addresses/{id}
Get address by ID. 🔒

### POST /users/addresses
Add address. 🔒

### PUT /users/addresses/{id}
Update address. 🔒

### DELETE /users/addresses/{id}
Delete address. 🔒

### GET /users/{id}/wishlists
Get user wishlists. 🔒

### POST /users/{id}/wishlists
Create wishlist. 🔒

### POST /users/{id}/wishlists/{wid}/items
Add item to wishlist. 🔒

**Body:** `{ product_id, variant_id?, quantity? }`

### DELETE /users/{id}/wishlists/{wid}/items/{item_id}
Remove item from wishlist. 🔒

### PUT /users/{id}/wishlists/{wid}/default
Set default wishlist. 🔒

---

## Categories

### GET /categories
List all categories.

### GET /categories/{id}
Get category by ID.

### POST /categories
Create category. 🔒 Admin

**Body:** `{ name, slug, description?, image_url?, parent_id? }`

### PUT /categories/{id}
Update category. 🔒 Admin

### DELETE /categories/{id}
Delete category. 🔒 Admin

---

## Products

### GET /products/search
Search products.

**Query:** `q, category?, page?, limit?`

### GET /products/categories/search
Search products by category.

### GET /products/home
Get home page products (featured, popular, deals).

### GET /products
List products.

**Query:** `page?, limit?, category?, featured?, popular?, sale?`

### GET /products/categories
List product categories.

### GET /products/{id}
Get product by ID.

### GET /products/{id}/recommendations
Get product recommendations.

### GET /products/{id}/variants
Get product variants.

### GET /products/variants/{id}
Get variant by ID.

### GET /products/categories/{id}
Get products by category ID.

### POST /products
Create product. 🔒 Admin

### PUT /products/{id}
Update product. 🔒 Admin

### DELETE /products/{id}
Delete product. 🔒 Admin

---

## Reviews

### GET /reviews
List reviews.

### POST /reviews
Create review. 🔒

**Body:** `{ product_id, rating, comment? }`

### GET /reviews/{id}
Get review by ID.

### GET /reviews/product/{id}
Get reviews for a product.

### PUT /reviews/{id}
Update review. 🔒

### DELETE /reviews/{id}
Delete review. 🔒

---

## Search

### GET /search
Full-text search.

**Query:** `q, page?, limit?`

### GET /search/autocomplete
Autocomplete suggestions.

**Query:** `q`

---

## Wishlist

### GET /wishlist
Get current user's wishlist. 🔒

### POST /wishlist/add
Add item to wishlist. 🔒

**Body:** `{ product_id, variant_id?, quantity? }`

### DELETE /wishlist/items/{product_id}
Remove item from wishlist. 🔒

---

## Inventory

### GET /inventory/check-stock/{variant_id}
Check stock for a variant.

### POST /inventory/check-stock/bulk
Bulk stock check.

**Body:** `{ variant_ids: string[] }`

### POST /inventory/locations
Create inventory location. 🔒 Admin

### GET /inventory/locations
List inventory locations. 🔒 Admin

### GET /inventory/locations/{id}
Get inventory location. 🔒 Admin

### PUT /inventory/locations/{id}
Update inventory location. 🔒 Admin

### DELETE /inventory/locations/{id}
Delete inventory location. 🔒 Admin

### POST /inventory
Create inventory record. 🔒 Admin

### GET /inventory
List inventory. 🔒 Admin

### GET /inventory/{id}
Get inventory record. 🔒 Admin

### PUT /inventory/{id}
Update inventory record. 🔒 Admin

### DELETE /inventory/{id}
Delete inventory record. 🔒 Admin

### POST /inventory/adjustments
Create inventory adjustment. 🔒 Admin

### GET /inventory/{id}/adjustments
Get adjustments for inventory record. 🔒 Admin

### GET /inventory/adjustments/all
Get all adjustments. 🔒 Admin

---

## Cart

### GET /cart
Get current cart. 🔒

### POST /cart/add
Add item to cart. 🔒

**Body:** `{ variant_id, quantity }`

### PUT /cart/items/{id}
Update cart item quantity. 🔒

**Body:** `{ quantity }`

### DELETE /cart/items/{id}
Remove cart item. 🔒

### POST /cart/promocode
Apply promo code. 🔒

**Body:** `{ code }`

### DELETE /cart/promocode
Remove promo code. 🔒

### GET /cart/count
Get cart item count. 🔒

### POST /cart/validate
Validate cart. 🔒

### POST /cart/shipping-options
Get shipping options for cart. 🔒

**Body:** `{ address_id }`

### POST /cart/calculate
Calculate cart totals. 🔒

### POST /cart/clear
Clear cart. 🔒

### GET /cart/checkout-summary
Get checkout summary. 🔒

---

## Orders

### POST /orders
Create order. 🔒

### POST /orders/create-payment-intent
Create Stripe payment intent. 🔒

### POST /orders/checkout/validate
Validate checkout data. 🔒

**Body:** `{ shipping_address_id, shipping_method_id, payment_method_id, discount_code?, notes?, currency?, country_code? }`

### POST /orders/checkout
Place order. 🔒

**Body:** `{ shipping_address_id, shipping_method_id, payment_method_id, discount_code?, notes?, currency?, country_code?, frontend_calculated_total? }`

### GET /orders
List user orders. 🔒

**Query:** `page?, limit?`

### GET /orders/{id}
Get order by ID. 🔒

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
