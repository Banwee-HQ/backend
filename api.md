# Banwee API Reference

> **Source of truth:** generated from the running FastAPI application schema (`234 operations across 169 paths).

## Environments

| Environment | Base URL |
| --- | --- |
| Local | `http://localhost:8000` |
| Hosted | Set `baseUrl` to the deployed API origin |

All versioned endpoints use the `/v1` prefix. Interactive OpenAPI documentation is available at `/docs`; the raw schema is available at `/openapi.json`.

## Authentication

Send the access token returned by login in the following header for protected operations:

```http
Authorization: Bearer <access_token>
```

Registration, login, token refresh, password recovery, email verification, OAuth sign-in, health checks, and the service root do not require an access token. Authorization failures return `401`; validation failures return `422`.

## Conventions

- JSON request and response bodies use `Content-Type: application/json` unless an operation declares another media type.
- Path parameters are shown in braces, for example `/v1/products/{product_id}`.
- Query, path, and header parameters are listed for every operation where FastAPI exposes them.
- Request and response model names link back to the schemas in the generated OpenAPI document available at `/openapi.json`.

## Addresses

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/addresses/` | List | Yes | `query:page`, `query:limit`, `query:search` | — | `200`, `422` |
| `POST` | `/v1/addresses/` | Create | Yes | — | `AddressCreate` (application/json) | `200`, `422` |
| `DELETE` | `/v1/addresses/{address_id}/` | Delete | Yes | `path:address_id*` | — | `200`, `422` |
| `GET` | `/v1/addresses/{address_id}/` | Get | Yes | `path:address_id*` | — | `200`, `422` |
| `PATCH` | `/v1/addresses/{address_id}/` | Patch | Yes | `path:address_id*` | `AddressUpdate` (application/json) | `200`, `422` |

## analytics

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/analytics/cart-abandonment/` | Cart Abandonment | Yes | `query:start_date`, `query:end_date`, `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/conversion-rates/` | Conversion Rates | Yes | `query:start_date`, `query:end_date`, `query:traffic_source`, `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/dashboard/` | Dashboard | Yes | `query:start_date`, `query:end_date`, `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/dashboard/admin/` | Admin Dashboard | Yes | `query:date_from`, `query:date_to`, `query:status`, `query:category` | — | `200`, `422` |
| `GET` | `/v1/analytics/export/orders/` | Export Orders | Yes | `query:format`, `query:status`, `query:q`, `query:date_from`, `query:date_to`, `query:min_price`, `query:max_price` | — | `200`, `422` |
| `GET` | `/v1/analytics/kpis/` | Kpis | Yes | `query:start_date`, `query:end_date`, `query:days`, `query:compare_previous` | — | `200`, `422` |
| `GET` | `/v1/analytics/orders/` | Orders | Yes | `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/products/` | Products | Yes | `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/refund-rates/` | Refund Rates | Yes | `query:start_date`, `query:end_date`, `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/repeat-customers/` | Repeat Customers | Yes | `query:start_date`, `query:end_date`, `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/revenue/` | Revenue | Yes | `query:start_date`, `query:end_date`, `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/sales-overview/` | Sales Overview | Yes | `query:start_date`, `query:end_date`, `query:days`, `query:granularity`, `query:categories`, `query:regions`, `query:sales_channels` | — | `200`, `422` |
| `GET` | `/v1/analytics/sales-trend/` | Sales Trend | Yes | `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/sales/` | Sales | Yes | `query:start_date`, `query:end_date`, `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/simple-dashboard/` | Simple Dashboard | Yes | — | — | `200` |
| `GET` | `/v1/analytics/stats/` | Admin Stats | Yes | `query:date_from`, `query:date_to`, `query:status`, `query:category` | — | `200`, `422` |
| `GET` | `/v1/analytics/time-to-purchase/` | Time To Purchase | Yes | `query:start_date`, `query:end_date`, `query:days` | — | `200`, `422` |
| `POST` | `/v1/analytics/track/` | Track | Yes | — | `Event Data` (application/json) | `200`, `422` |
| `GET` | `/v1/analytics/users-growth-trend/` | Users Growth Trend | Yes | `query:days` | — | `200`, `422` |
| `GET` | `/v1/analytics/users/` | Users | Yes | `query:days` | — | `200`, `422` |

## Authentication

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/v1/auth/forgot-password/` | Forgot Password | No | — | `ForgotPassword` (application/json) | `200`, `422` |
| `POST` | `/v1/auth/login/` | Login | No | — | `Login` (application/json) | `200`, `422` |
| `POST` | `/v1/auth/logout/` | Logout | Yes | — | — | `200` |
| `DELETE` | `/v1/auth/me/` | Delete | Yes | `query:password*` | — | `200`, `422` |
| `GET` | `/v1/auth/me/` | Me | Yes | — | — | `200` |
| `PATCH` | `/v1/auth/me/` | Update | Yes | — | `User Data` (application/json) | `200`, `422` |
| `PATCH` | `/v1/auth/me/password/` | Password | Yes | `query:current_password`, `query:new_password` | — | `200`, `422` |
| `POST` | `/v1/auth/refresh/` | Refresh | No | — | `Refresh` (application/json) | `200`, `422` |
| `POST` | `/v1/auth/register/` | Register | No | — | `UserCreate` (application/json) | `200`, `422` |
| `POST` | `/v1/auth/resend-verification/` | Resend | No | `header:x-resend-token` | `ResendVerification` (application/json) | `200`, `422` |
| `POST` | `/v1/auth/reset-password/` | Reset | No | — | `ResetPassword` (application/json) | `200`, `422` |
| `POST` | `/v1/auth/revoke/` | Revoke | Yes | `query:refresh_token*` | — | `200`, `422` |
| `GET` | `/v1/auth/verify-email/` | Verify | No | `query:token*` | — | `200`, `422` |

## Cart

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/cart/` | Get | Yes | `query:country`, `query:province` | — | `200`, `422` |
| `POST` | `/v1/cart/` | Create | Yes | — | `Add` (application/json) | `200`, `422` |
| `POST` | `/v1/cart/add/` | Add Item | Yes | — | `Add` (application/json) | `200`, `422` |
| `POST` | `/v1/cart/calculate/` | Calculate | Yes | — | `Data` (application/json) | `200`, `422` |
| `GET` | `/v1/cart/checkout-summary/` | Summary | Yes | — | — | `200` |
| `POST` | `/v1/cart/clear/` | Clear | Yes | — | — | `200` |
| `GET` | `/v1/cart/count/` | Count | Yes | — | — | `200` |
| `DELETE` | `/v1/cart/items/{item_id}/` | Delete Item | Yes | `path:item_id*` | — | `200`, `422` |
| `PATCH` | `/v1/cart/items/{item_id}/` | Patch Item | Yes | `path:item_id*` | `UpdateItem` (application/json) | `200`, `422` |
| `POST` | `/v1/cart/validate/` | Validate | Yes | `query:country`, `query:province` | — | `200`, `422` |
| `DELETE` | `/v1/cart/{item_id}/` | Delete | Yes | `path:item_id*` | — | `200`, `422` |
| `PATCH` | `/v1/cart/{item_id}/` | Patch | Yes | `path:item_id*` | `UpdateItem` (application/json) | `200`, `422` |

## Categories

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/categories/` | List | Yes | `query:page`, `query:limit`, `query:active_only` | — | `200`, `422` |
| `POST` | `/v1/categories/` | Create | Yes | — | `schemas__catalog__category__Create` (application/json) | `201`, `422` |
| `GET` | `/v1/categories/tree/` | Tree | Yes | `query:active_only` | — | `200`, `422` |
| `DELETE` | `/v1/categories/{category_id}/` | Delete | Yes | `path:category_id*` | — | `200`, `422` |
| `GET` | `/v1/categories/{category_id}/` | Get | Yes | `path:category_id*` | — | `200`, `422` |
| `PATCH` | `/v1/categories/{category_id}/` | Update | Yes | `path:category_id*` | `schemas__catalog__category__Update` (application/json) | `200`, `422` |

## Contact Messages

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/contact-messages/` | List | Yes | `query:page`, `query:page_size`, `query:status`, `query:priority`, `query:search` | — | `200`, `422` |
| `POST` | `/v1/contact-messages/` | Create | Yes | — | `schemas__system__contact_message__Create` (application/json) | `200`, `422` |
| `DELETE` | `/v1/contact-messages/{message_id}/` | Delete | Yes | `path:message_id*` | — | `200`, `422` |
| `GET` | `/v1/contact-messages/{message_id}/` | Get | Yes | `path:message_id*` | — | `200`, `422` |
| `PATCH` | `/v1/contact-messages/{message_id}/` | Patch | Yes | `path:message_id*` | `schemas__system__contact_message__Update` (application/json) | `200`, `422` |

## health

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/health/` | Liveness Check | No | — | — | `200` |
| `GET` | `/v1/health/ready` | Readiness Check | No | — | — | `200` |

## inventory

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/inventory/` | List | Yes | `query:page`, `query:limit`, `query:product_id`, `query:location_id`, `query:location_name`, `query:search`, `query:low_stock`, `query:in_stock`, `query:out_of_stock`, `query:sort_by`, `query:sort_order` | — | `200`, `422` |
| `POST` | `/v1/inventory/` | Create | Yes | — | `schemas__catalog__inventory__Create` (application/json) | `200`, `422` |
| `GET` | `/v1/inventory/adjustments/` | List Adj | Yes | `query:page`, `query:limit`, `query:inventory_id` | — | `200`, `422` |
| `POST` | `/v1/inventory/adjustments/` | Create Adj | Yes | — | `AdjustmentCreate` (application/json) | `200`, `422` |
| `DELETE` | `/v1/inventory/adjustments/{adjustment_id}/` | Delete Adj | Yes | `path:adjustment_id*` | — | `200`, `422` |
| `GET` | `/v1/inventory/adjustments/{adjustment_id}/` | Get Adj | Yes | `path:adjustment_id*` | — | `200`, `422` |
| `GET` | `/v1/inventory/locations/` | List Locations | Yes | `query:page`, `query:limit` | — | `200`, `422` |
| `POST` | `/v1/inventory/locations/` | Create Location | Yes | — | `LocationCreate` (application/json) | `200`, `422` |
| `DELETE` | `/v1/inventory/locations/{location_id}/` | Delete Location | Yes | `path:location_id*` | — | `200`, `422` |
| `GET` | `/v1/inventory/locations/{location_id}/` | Get Location | Yes | `path:location_id*` | — | `200`, `422` |
| `PATCH` | `/v1/inventory/locations/{location_id}/` | Update Location | Yes | `path:location_id*` | `LocationUpdate` (application/json) | `200`, `422` |
| `POST` | `/v1/inventory/sync-all/` | Sync All | Yes | — | — | `200` |
| `POST` | `/v1/inventory/sync/product/{product_id}/` | Sync Product | Yes | `path:product_id*` | — | `200`, `422` |
| `DELETE` | `/v1/inventory/{inventory_id}/` | Delete | Yes | `path:inventory_id*` | — | `200`, `422` |
| `GET` | `/v1/inventory/{inventory_id}/` | Get | Yes | `path:inventory_id*` | — | `200`, `422` |
| `PATCH` | `/v1/inventory/{inventory_id}/` | Patch | Yes | `path:inventory_id*` | `schemas__catalog__inventory__Update` (application/json) | `200`, `422` |

## OAuth

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/v1/auth/social/facebook` | Facebook Oauth Credential | No | `query:access_token`, `query:user_id`, `query:mode` | — | `200`, `422` |
| `POST` | `/v1/auth/social/google` | Google Oauth Credential | No | `query:credential`, `query:mode` | — | `200`, `422` |

## Orders

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/orders/` | List | Yes | `query:page`, `query:limit`, `query:status_filter`, `query:search`, `query:date_from`, `query:date_to`, `query:sort_by`, `query:sort_order` | — | `200`, `422` |
| `POST` | `/v1/orders/` | Create | Yes | — | `Checkout` (application/json) | `200`, `422` |
| `POST` | `/v1/orders/checkout/` | Checkout | Yes | — | `Checkout` (application/json) | `200`, `422` |
| `POST` | `/v1/orders/checkout/validate/` | Validate | Yes | — | `Checkout` (application/json) | `200`, `422` |
| `GET` | `/v1/orders/statistics/` | Statistics | Yes | `query:date_from`, `query:date_to` | — | `200`, `422` |
| `GET` | `/v1/orders/track/{order_id}/` | Get Public Tracking | Yes | `path:order_id*` | — | `200`, `422` |
| `GET` | `/v1/orders/{order_id}/` | Get | Yes | `path:order_id*` | — | `200`, `422` |
| `PATCH` | `/v1/orders/{order_id}/cancel/` | Cancel | Yes | `path:order_id*` | — | `200`, `422` |
| `POST` | `/v1/orders/{order_id}/cancel/` | Cancel Post | Yes | `path:order_id*` | — | `200`, `422` |
| `PUT` | `/v1/orders/{order_id}/deliver/` | Deliver | Yes | `path:order_id*` | `Request` (application/json) | `200`, `422` |
| `GET` | `/v1/orders/{order_id}/invoice/` | Get Invoice | Yes | `path:order_id*` | — | `200`, `422` |
| `GET` | `/v1/orders/{order_id}/notes/` | List Notes | Yes | `path:order_id*` | — | `200`, `422` |
| `POST` | `/v1/orders/{order_id}/notes/` | Create Note | Yes | `path:order_id*` | `Note` (application/json) | `200`, `422` |
| `GET` | `/v1/orders/{order_id}/notes/{note_index}/` | Get Note | Yes | `path:order_id*`, `path:note_index*` | — | `200`, `422` |
| `GET` | `/v1/orders/{order_id}/payments/` | Get Order Payments | Yes | `path:order_id*` | — | `200`, `422` |
| `POST` | `/v1/orders/{order_id}/ship/` | Ship | Yes | `path:order_id*` | `Request` (application/json) | `200`, `422` |
| `GET` | `/v1/orders/{order_id}/shipments/` | Get Order Shipments | Yes | `path:order_id*` | — | `200`, `422` |
| `PATCH` | `/v1/orders/{order_id}/status/` | Update Status | Yes | `path:order_id*` | `Request` (application/json) | `200`, `422` |
| `GET` | `/v1/orders/{order_id}/tracking/` | Get Tracking | Yes | `path:order_id*` | — | `200`, `422` |

## payments

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/payments/` | Overview | Yes | — | — | `200` |
| `GET` | `/v1/payments/admin/transactions/` | List All Transactions | Yes | `query:page`, `query:limit`, `query:search`, `query:status`, `query:payment_method`, `query:date_from`, `query:date_to` | — | `200`, `422` |
| `GET` | `/v1/payments/failures/` | List Failures | Yes | `query:page`, `query:limit` | — | `200`, `422` |
| `POST` | `/v1/payments/failures/{payment_intent_id}/retry/` | Retry Payment | Yes | `path:payment_intent_id*`, `query:new_payment_method_id` | — | `200`, `422` |
| `GET` | `/v1/payments/failures/{payment_intent_id}/status/` | Failure Status | Yes | `path:payment_intent_id*` | — | `200`, `422` |
| `GET` | `/v1/payments/intents/` | List Intents | Yes | `query:page`, `query:limit` | — | `200`, `422` |
| `POST` | `/v1/payments/intents/` | Create Intent | Yes | — | `IntentCreate` (application/json) | `200`, `422` |
| `GET` | `/v1/payments/intents/{payment_intent_id}/` | Get Intent | Yes | `path:payment_intent_id*` | — | `200`, `422` |
| `POST` | `/v1/payments/intents/{payment_intent_id}/confirm/` | Confirm Intent | Yes | `path:payment_intent_id*`, `query:payment_method_id*` | — | `200`, `422` |
| `GET` | `/v1/payments/methods/` | List Methods | Yes | `query:page`, `query:limit`, `query:search` | — | `200`, `422` |
| `POST` | `/v1/payments/methods/` | Create Method | Yes | — | `schemas__commerce__payments__MethodCreate` (application/json) | `200`, `422` |
| `DELETE` | `/v1/payments/methods/{payment_method_id}/` | Delete Method | Yes | `path:payment_method_id*` | — | `200`, `422` |
| `GET` | `/v1/payments/methods/{payment_method_id}/` | Get Method | Yes | `path:payment_method_id*` | — | `200`, `422` |
| `PATCH` | `/v1/payments/methods/{payment_method_id}/` | Patch Method | Yes | `path:payment_method_id*` | `schemas__commerce__payments__MethodUpdate` (application/json) | `200`, `422` |
| `POST` | `/v1/payments/methods/{payment_method_id}/default/` | Set Default Method | Yes | `path:payment_method_id*` | — | `200`, `422` |
| `POST` | `/v1/payments/process/` | Process Payment | Yes | `query:amount*`, `query:payment_method_id*`, `query:order_id`, `query:subscription_id` | — | `200`, `422` |
| `GET` | `/v1/payments/refunds/` | List Refunds | Yes | `query:page`, `query:limit` | — | `200`, `422` |
| `POST` | `/v1/payments/refunds/` | Create Refund | Yes | — | `Refund` (application/json) | `200`, `422` |
| `GET` | `/v1/payments/refunds/{refund_id}/` | Get Refund | Yes | `path:refund_id*` | — | `200`, `422` |
| `GET` | `/v1/payments/transactions/` | List Transactions | Yes | `query:page`, `query:limit` | — | `200`, `422` |
| `GET` | `/v1/payments/transactions/{transaction_id}/` | Get Transaction | Yes | `path:transaction_id*` | — | `200`, `422` |

## Products

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/products/` | List | Yes | `query:page`, `query:limit`, `query:category`, `query:q`, `query:min_price`, `query:max_price`, `query:min_rating`, `query:max_rating`, `query:sort_by`, `query:sort_order`, `query:availability`, `query:featured`, `query:is_featured`, `query:is_bestseller`, `query:popular`, `query:sale`, `query:search_mode` | — | `200`, `422` |
| `POST` | `/v1/products/` | Create | Yes | — | `schemas__catalog__product__Create` (application/json) | `200`, `422` |
| `GET` | `/v1/products/deals/` | Get Deals | Yes | `query:page`, `query:limit` | — | `200`, `422` |
| `GET` | `/v1/products/featured/` | Get Featured | Yes | `query:limit` | — | `200`, `422` |
| `GET` | `/v1/products/home/` | Get Home Data | Yes | — | — | `200` |
| `DELETE` | `/v1/products/images/{image_id}/` | Delete Image | Yes | `path:image_id*` | — | `200`, `422` |
| `GET` | `/v1/products/images/{image_id}/` | Get Image | Yes | `path:image_id*` | — | `200`, `422` |
| `PATCH` | `/v1/products/images/{image_id}/` | Patch Image | Yes | `path:image_id*` | `ImageUpdate` (application/json) | `200`, `422` |
| `DELETE` | `/v1/products/variants/{variant_id}/` | Delete Variant | Yes | `path:variant_id*` | — | `200`, `422` |
| `GET` | `/v1/products/variants/{variant_id}/` | Get Variant | Yes | `path:variant_id*` | — | `200`, `422` |
| `PATCH` | `/v1/products/variants/{variant_id}/` | Patch Variant | Yes | `path:variant_id*` | `VariantUpdate` (application/json) | `200`, `422` |
| `GET` | `/v1/products/variants/{variant_id}/images/` | List Images | Yes | `path:variant_id*` | — | `200`, `422` |
| `POST` | `/v1/products/variants/{variant_id}/images/` | Create Image | Yes | `path:variant_id*` | `ImageCreate` (application/json) | `200`, `422` |
| `DELETE` | `/v1/products/{product_id}/` | Delete | Yes | `path:product_id*` | — | `200`, `422` |
| `GET` | `/v1/products/{product_id}/` | Get Product | Yes | `path:product_id*` | — | `200`, `422` |
| `PATCH` | `/v1/products/{product_id}/` | Update | Yes | `path:product_id*` | `schemas__catalog__product__Update` (application/json) | `200`, `422` |
| `PATCH` | `/v1/products/{product_id}/feature/` | Feature | Yes | `path:product_id*`, `query:featured` | — | `200`, `422` |
| `PATCH` | `/v1/products/{product_id}/moderate/` | Moderate | Yes | `path:product_id*` | `Request` (application/json) | `200`, `422` |
| `GET` | `/v1/products/{product_id}/recommendations/` | Recommended | Yes | `path:product_id*`, `query:limit` | — | `200`, `422` |
| `GET` | `/v1/products/{product_id}/variants/` | List Variants | Yes | `path:product_id*` | — | `200`, `422` |
| `POST` | `/v1/products/{product_id}/variants/` | Create Variant | Yes | `path:product_id*` | `VariantCreate` (application/json) | `200`, `422` |

## promocodes

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/promocodes/` | List | Yes | `query:page`, `query:limit`, `query:is_active` | — | `200`, `422` |
| `POST` | `/v1/promocodes/` | Create | Yes | — | `schemas__commerce__promos__Create` (application/json) | `200`, `422` |
| `POST` | `/v1/promocodes/trigger-cleanup/` | Trigger Cleanup | Yes | — | — | `200` |
| `POST` | `/v1/promocodes/validate/` | Validate | Yes | — | `ValidateRequest` (application/json) | `200`, `422` |
| `DELETE` | `/v1/promocodes/{promocode_id}/` | Delete | Yes | `path:promocode_id*` | — | `200`, `422` |
| `GET` | `/v1/promocodes/{promocode_id}/` | Get | Yes | `path:promocode_id*` | — | `200`, `422` |
| `PATCH` | `/v1/promocodes/{promocode_id}/` | Update | Yes | `path:promocode_id*` | `schemas__commerce__promos__Update` (application/json) | `200`, `422` |

## refunds

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/refunds/` | List | Yes | `query:refund_status`, `query:page`, `query:limit`, `query:sort_by`, `query:sort_order` | — | `200`, `422` |
| `POST` | `/v1/refunds/` | Create | Yes | — | `Refund Data` (application/json) | `200`, `422` |
| `POST` | `/v1/refunds/orders/{order_id}/request/` | Request | Yes | `path:order_id*` | `Request` (application/json) | `200`, `422` |
| `GET` | `/v1/refunds/{refund_id}/` | Get | Yes | `path:refund_id*` | — | `200`, `422` |
| `PATCH` | `/v1/refunds/{refund_id}/` | Patch | Yes | `path:refund_id*` | `Payload` (application/json) | `200`, `422` |
| `PUT` | `/v1/refunds/{refund_id}/status/` | Update Status | Yes | `path:refund_id*` | `UpdateRefundStatus` (application/json) | `200`, `422` |

## Reviews

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/reviews/` | List | Yes | `query:page`, `query:limit`, `query:product_id`, `query:min_rating`, `query:max_rating`, `query:sort_by` | — | `200`, `422` |
| `POST` | `/v1/reviews/` | Create | Yes | — | `schemas__catalog__review__Create` (application/json) | `200`, `422` |
| `GET` | `/v1/reviews/product/{product_id}/` | For Product | Yes | `path:product_id*`, `query:page`, `query:limit`, `query:min_rating`, `query:max_rating`, `query:sort_by` | — | `200`, `422` |
| `DELETE` | `/v1/reviews/{review_id}/` | Delete | Yes | `path:review_id*` | — | `200`, `422` |
| `GET` | `/v1/reviews/{review_id}/` | Get | Yes | `path:review_id*` | — | `200`, `422` |
| `PATCH` | `/v1/reviews/{review_id}/` | Update | Yes | `path:review_id*` | `schemas__catalog__review__Update` (application/json) | `200`, `422` |

## shipping

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/v1/shipping/calculate/` | Calc Cost | Yes | — | `Calculate` (application/json) | `200`, `422` |
| `GET` | `/v1/shipping/methods/` | List | Yes | `query:page`, `query:limit`, `query:is_active`, `query:all_methods` | — | `200`, `422` |
| `POST` | `/v1/shipping/methods/` | Create | Yes | — | `schemas__commerce__shipping__MethodCreate` (application/json) | `200`, `422` |
| `DELETE` | `/v1/shipping/methods/{method_id}/` | Delete | Yes | `path:method_id*` | — | `200`, `422` |
| `GET` | `/v1/shipping/methods/{method_id}/` | Get | Yes | `path:method_id*` | — | `200`, `422` |
| `PATCH` | `/v1/shipping/methods/{method_id}/` | Patch | Yes | `path:method_id*` | `schemas__commerce__shipping__MethodUpdate` (application/json) | `200`, `422` |

## shipping-tracking

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/shipping-tracking/carriers/` | List Carriers | Yes | `query:active_only` | — | `200`, `422` |
| `POST` | `/v1/shipping-tracking/carriers/` | Create Carrier | Yes | — | `schemas__commerce__carrier__Create` (application/json) | `200`, `422` |
| `DELETE` | `/v1/shipping-tracking/carriers/{carrier_id}/` | Delete Carrier | Yes | `path:carrier_id*` | — | `200`, `422` |
| `PATCH` | `/v1/shipping-tracking/carriers/{carrier_id}/` | Update Carrier | Yes | `path:carrier_id*` | `schemas__commerce__carrier__Update` (application/json) | `200`, `422` |
| `GET` | `/v1/shipping-tracking/providers/` | List Providers | Yes | — | — | `200` |
| `POST` | `/v1/shipping-tracking/providers/` | Create Provider | Yes | — | `Provider Data` (application/json) | `200`, `422` |
| `DELETE` | `/v1/shipping-tracking/providers/{provider_id}/` | Delete Provider | Yes | `path:provider_id*` | — | `200`, `422` |
| `PATCH` | `/v1/shipping-tracking/providers/{provider_id}/` | Patch Provider | Yes | `path:provider_id*` | `Provider Data` (application/json) | `200`, `422` |
| `GET` | `/v1/shipping-tracking/shipments/` | List | Yes | `query:page`, `query:limit` | — | `200`, `422` |
| `POST` | `/v1/shipping-tracking/shipments/` | Create Shipment | Yes | — | `schemas__commerce__shipping_tracking__Create` (application/json) | `200`, `422` |
| `GET` | `/v1/shipping-tracking/shipments/{shipment_id}/` | Get Shipment | Yes | `path:shipment_id*` | — | `200`, `422` |
| `PATCH` | `/v1/shipping-tracking/shipments/{shipment_id}/status/` | Update Shipment Status | Yes | `path:shipment_id*` | `schemas__commerce__shipping_tracking__Update` (application/json) | `200`, `422` |
| `POST` | `/v1/shipping-tracking/track/` | Track | Yes | — | `Track` (application/json) | `200`, `422` |
| `POST` | `/v1/shipping-tracking/webhooks/{carrier}/` | Handle Carrier Webhook | Yes | `path:carrier*` | `Webhook Data` (application/json) | `200`, `422` |

## subscriptions

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/subscriptions/` | List Subscriptions | Yes | `query:page`, `query:limit`, `query:status`, `query:search`, `query:date_from`, `query:date_to`, `query:sort_by`, `query:sort_order` | — | `200`, `422` |
| `POST` | `/v1/subscriptions/` | Create | Yes | — | `schemas__commerce__subscriptions__Create` (application/json) | `200`, `422` |
| `POST` | `/v1/subscriptions/calculate-cost/` | Calculate | Yes | — | `CostCalculation` (application/json) | `200`, `422` |
| `GET` | `/v1/subscriptions/due/` | List Due | Yes | — | — | `200` |
| `GET` | `/v1/subscriptions/plans/` | Plans | Yes | — | — | `200` |
| `POST` | `/v1/subscriptions/trigger-notifications/` | Trigger Notifications | Yes | — | — | `200` |
| `POST` | `/v1/subscriptions/trigger-order-processing/` | Trigger Order Processing | Yes | — | — | `200` |
| `DELETE` | `/v1/subscriptions/{subscription_id}/` | Delete | Yes | `path:subscription_id*` | — | `200`, `422` |
| `GET` | `/v1/subscriptions/{subscription_id}/` | Get | Yes | `path:subscription_id*` | — | `200`, `422` |
| `PATCH` | `/v1/subscriptions/{subscription_id}/` | Update | Yes | `path:subscription_id*` | `schemas__commerce__subscriptions__Update` (application/json) | `200`, `422` |
| `PATCH` | `/v1/subscriptions/{subscription_id}/auto-renew/` | Toggle Auto Renew | Yes | `path:subscription_id*`, `query:auto_renew*` | — | `200`, `422` |
| `POST` | `/v1/subscriptions/{subscription_id}/cancel/` | Cancel | Yes | `path:subscription_id*`, `query:reason` | — | `200`, `422` |
| `GET` | `/v1/subscriptions/{subscription_id}/details/` | Details | Yes | `path:subscription_id*` | — | `200`, `422` |
| `POST` | `/v1/subscriptions/{subscription_id}/discounts/` | Apply Discount | Yes | `path:subscription_id*` | `DiscountApplication` (application/json) | `200`, `422` |
| `DELETE` | `/v1/subscriptions/{subscription_id}/discounts/{discount_id}/` | Remove Discount | Yes | `path:subscription_id*`, `path:discount_id*` | — | `200`, `422` |
| `PATCH` | `/v1/subscriptions/{subscription_id}/frequency/` | Change Frequency | Yes | `path:subscription_id*` | `ChangeFrequency` (application/json) | `200`, `422` |
| `GET` | `/v1/subscriptions/{subscription_id}/orders/` | Orders | Yes | `path:subscription_id*`, `query:page`, `query:limit` | — | `200`, `422` |
| `POST` | `/v1/subscriptions/{subscription_id}/pause/` | Pause | Yes | `path:subscription_id*`, `query:pause_reason` | — | `200`, `422` |
| `POST` | `/v1/subscriptions/{subscription_id}/process-shipment/` | Process Shipment | Yes | `path:subscription_id*` | — | `200`, `422` |
| `DELETE` | `/v1/subscriptions/{subscription_id}/products/` | Remove Products | Yes | `path:subscription_id*` | `RemoveProducts` (application/json) | `200`, `422` |
| `POST` | `/v1/subscriptions/{subscription_id}/products/` | Add Products | Yes | `path:subscription_id*` | `AddProducts` (application/json) | `200`, `422` |
| `PATCH` | `/v1/subscriptions/{subscription_id}/products/adjust-quantity/` | Adjust Quantity | Yes | `path:subscription_id*` | `QuantityChange` (application/json) | `200`, `422` |
| `GET` | `/v1/subscriptions/{subscription_id}/products/quantities/` | Get Quantities | Yes | `path:subscription_id*` | — | `200`, `422` |
| `PATCH` | `/v1/subscriptions/{subscription_id}/products/quantity/` | Update Quantity | Yes | `path:subscription_id*` | `UpdateQuantity` (application/json) | `200`, `422` |
| `DELETE` | `/v1/subscriptions/{subscription_id}/products/{product_id}/` | Remove Product | Yes | `path:subscription_id*`, `path:product_id*` | — | `200`, `422` |
| `POST` | `/v1/subscriptions/{subscription_id}/resume/` | Resume | Yes | `path:subscription_id*` | — | `200`, `422` |
| `POST` | `/v1/subscriptions/{subscription_id}/skip/` | Skip | Yes | `path:subscription_id*` | `SkipShipment` (application/json) | `200`, `422` |
| `POST` | `/v1/subscriptions/{subscription_id}/unskip/` | Unskip | Yes | `path:subscription_id*` | — | `200`, `422` |

## tax

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `POST` | `/v1/tax/calculate/` | Calculate Tax | Yes | — | `Calculation` (application/json) | `200`, `422` |
| `GET` | `/v1/tax/countries/` | Countries | Yes | — | — | `200` |
| `GET` | `/v1/tax/rates/` | List Rates | Yes | `query:country_code`, `query:country_name`, `query:province_code`, `query:province_name`, `query:is_active`, `query:search`, `query:sort_by`, `query:sort_order`, `query:page`, `query:per_page` | — | `200`, `422` |
| `POST` | `/v1/tax/rates/` | Create Rate | Yes | — | `RateCreate` (application/json) | `201`, `422` |
| `POST` | `/v1/tax/rates/bulk-update/` | Bulk Update | Yes | — | `Updates` (application/json) | `200`, `422` |
| `DELETE` | `/v1/tax/rates/{tax_rate_id}/` | Delete Rate | Yes | `path:tax_rate_id*` | — | `200`, `422` |
| `GET` | `/v1/tax/rates/{tax_rate_id}/` | Get Rate | Yes | `path:tax_rate_id*` | — | `200`, `422` |
| `PATCH` | `/v1/tax/rates/{tax_rate_id}/` | Update Rate | Yes | `path:tax_rate_id*` | `RateUpdate` (application/json) | `200`, `422` |
| `GET` | `/v1/tax/tax-types/` | Tax Types | Yes | — | — | `200` |

## Ungrouped

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/` | Read Root | No | — | — | `200` |

## Users

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/users/` | List | Yes | `query:page`, `query:limit`, `query:role`, `query:q`, `query:search`, `query:status` | — | `200`, `422` |
| `POST` | `/v1/users/` | Create | Yes | — | `schemas__accounts__user__Create` (application/json) | `200`, `422` |
| `GET` | `/v1/users/me/` | Me | Yes | — | — | `200` |
| `GET` | `/v1/users/profile/` | Profile | Yes | — | — | `200` |
| `DELETE` | `/v1/users/{user_id}/` | Delete | Yes | `path:user_id*` | — | `200`, `422` |
| `GET` | `/v1/users/{user_id}/` | Get | Yes | `path:user_id*` | — | `200`, `422` |
| `PATCH` | `/v1/users/{user_id}/` | Patch | Yes | `path:user_id*` | `schemas__accounts__user__Update` (application/json) | `200`, `422` |
| `POST` | `/v1/users/{user_id}/activate/` | Activate | Yes | `path:user_id*` | — | `200`, `422` |
| `GET` | `/v1/users/{user_id}/activity/` | Activity | Yes | `path:user_id*`, `query:page`, `query:limit` | — | `200`, `422` |
| `POST` | `/v1/users/{user_id}/deactivate/` | Deactivate | Yes | `path:user_id*` | — | `200`, `422` |
| `POST` | `/v1/users/{user_id}/reset-password/` | Reset Password | Yes | `path:user_id*` | — | `200`, `422` |
| `PUT` | `/v1/users/{user_id}/status/` | Update Status | Yes | `path:user_id*` | `UserStatusUpdate` (application/json) | `200`, `422` |
| `PUT` | `/v1/users/{user_id}/verify/` | Verify | Yes | `path:user_id*` | — | `200`, `422` |

## webhooks

| Method | Path | Summary | Auth | Parameters | Request body | Responses |
| --- | --- | --- | --- | --- | --- | --- |
| `GET` | `/v1/webhooks/health/` | Webhook Health | Yes | — | — | `200` |
| `POST` | `/v1/webhooks/stripe/` | Stripe Webhook | Yes | — | — | `200` |

## Error responses

| Status | Meaning |
| --- | --- |
| `400` | Request rejected by business validation. |
| `401` | Missing or invalid authentication. |
| `403` | Authenticated user lacks permission. |
| `404` | Resource does not exist. |
| `409` | Request conflicts with current state. |
| `422` | Request failed FastAPI schema validation. |
| `429` | Rate limit exceeded. |
| `500` | Unexpected server error; inspect structured logs and request ID. |

## Keeping this reference current

Regenerate this file and `postman_collection.json` after changing a route, schema, or authentication rule. The generated artifacts must match `app.openapi()` before release.
