# API Reference (auto-generated)

Base URL: `/v1`

All authenticated endpoints require a Bearer token in the `Authorization` header.

Generated from current API routes.

---

## Addresses

- GET `/`
- POST `/`
- DELETE `/{address_id}/`
- GET `/{address_id}/`
- PATCH `/{address_id}/`

---

## Auth

- POST `/forgot-password/`
- POST `/login/`
- POST `/logout/`
- DELETE `/me/`
- GET `/me/`
- PATCH `/me/`
- PATCH `/me/password/`
- POST `/refresh/`
- POST `/register/`
- POST `/resend-verification/`
- POST `/reset-password/`
- POST `/revoke/`
- GET `/verify-email/`

---

## Oauth

- POST `/facebook`
- POST `/google`

---

## User

- GET `/`
- POST `/`
- GET `/me/`
- GET `/profile/`
- DELETE `/{user_id}/`
- GET `/{user_id}/`
- PATCH `/{user_id}/`
- POST `/{user_id}/activate/`
- GET `/{user_id}/activity/`
- POST `/{user_id}/deactivate/`
- POST `/{user_id}/reset-password/`
- PUT `/{user_id}/status/`
- PUT `/{user_id}/verify/`

---

## Analytics

- GET `/cart-abandonment/`
- GET `/conversion-rates/`
- GET `/dashboard/`
- GET `/dashboard/admin/`
- GET `/export/orders/`
- GET `/kpis/`
- GET `/orders/`
- GET `/products/`
- GET `/refund-rates/`
- GET `/repeat-customers/`
- GET `/revenue/`
- GET `/sales-overview/`
- GET `/sales-trend/`
- GET `/sales/`
- GET `/simple-dashboard/`
- GET `/stats/`
- GET `/time-to-purchase/`
- POST `/track/`
- GET `/users-growth-trend/`
- GET `/users/`

---

## Inventory

- GET `/`
- POST `/`
- GET `/adjustments/`
- POST `/adjustments/`
- DELETE `/adjustments/{adjustment_id}/`
- GET `/adjustments/{adjustment_id}/`
- GET `/locations/`
- POST `/locations/`
- DELETE `/locations/{location_id}/`
- GET `/locations/{location_id}/`
- PATCH `/locations/{location_id}/`
- POST `/sync-all/`
- POST `/sync/product/{product_id}/`
- DELETE `/{inventory_id}/`
- GET `/{inventory_id}/`
- PATCH `/{inventory_id}/`

---

## Products

- GET `/`
- POST `/`
- GET `/deals/`
- GET `/featured/`
- GET `/home/`
- DELETE `/images/{image_id}/`
- GET `/images/{image_id}/`
- PATCH `/images/{image_id}/`
- DELETE `/variants/{variant_id}/`
- GET `/variants/{variant_id}/`
- GET `/variants/{variant_id}/`
- PATCH `/variants/{variant_id}/`
- GET `/variants/{variant_id}/images/`
- POST `/variants/{variant_id}/images/`
- DELETE `/{product_id}/`
- GET `/{product_id}/`
- PATCH `/{product_id}/`
- PATCH `/{product_id}/feature/`
- PATCH `/{product_id}/moderate/`
- GET `/{product_id}/recommendations/`
- GET `/{product_id}/variants/`
- GET `/{product_id}/variants/`
- POST `/{product_id}/variants/`

---

## Review

- GET `/`
- POST `/`
- GET `/product/{product_id}/`
- GET `/{review_id}/`

---

## Cart

- GET `/`
- POST `/`
- POST `/add/`
- POST `/calculate/`
- GET `/checkout-summary/`
- POST `/clear/`
- GET `/count/`
- DELETE `/items/{item_id}/`
- PATCH `/items/{item_id}/`
- POST `/validate/`
- DELETE `/{item_id}/`
- PATCH `/{item_id}/`

---

## Orders

- GET `/`
- POST `/`
- POST `/checkout/`
- POST `/checkout/validate/`
- GET `/statistics/`
- GET `/track/{order_id}/`
- GET `/{order_id}/`
- PATCH `/{order_id}/cancel/`
- POST `/{order_id}/cancel/`
- PUT `/{order_id}/deliver/`
- GET `/{order_id}/invoice/`
- GET `/{order_id}/notes/`
- POST `/{order_id}/notes/`
- GET `/{order_id}/notes/{note_index}/`
- POST `/{order_id}/ship/`
- GET `/{order_id}/shipments/`
- PATCH `/{order_id}/status/`
- GET `/{order_id}/tracking/`

---

## Payments

- GET `/`
- GET `/admin/transactions/`
- GET `/failures/`
- POST `/failures/{payment_intent_id}/retry/`
- GET `/failures/{payment_intent_id}/status/`
- GET `/intents/`
- POST `/intents/`
- GET `/intents/{payment_intent_id}/`
- POST `/intents/{payment_intent_id}/confirm/`
- GET `/methods/`
- POST `/methods/`
- DELETE `/methods/{payment_method_id}/`
- GET `/methods/{payment_method_id}/`
- PATCH `/methods/{payment_method_id}/`
- POST `/methods/{payment_method_id}/default/`
- POST `/process/`
- GET `/refunds/`
- POST `/refunds/`
- GET `/refunds/{refund_id}/`
- GET `/transactions/`
- GET `/transactions/{transaction_id}/`

---

## Promocodes

- GET `/`
- POST `/`
- POST `/trigger-cleanup/`
- POST `/validate/`
- DELETE `/{promocode_id}/`
- GET `/{promocode_id}/`
- PATCH `/{promocode_id}/`

---

## Refunds

- GET `/`
- POST `/`
- POST `/orders/{order_id}/request/`
- GET `/{refund_id}/`
- PATCH `/{refund_id}/`
- PUT `/{refund_id}/status/`

---

## Shipping

- POST `/calculate/`
- GET `/methods/`
- POST `/methods/`
- DELETE `/methods/{method_id}/`
- GET `/methods/{method_id}/`
- PATCH `/methods/{method_id}/`

---

## Shipping Tracking

- GET `/carriers/`
- GET `/providers/`
- POST `/providers/`
- DELETE `/providers/{provider_id}/`
- PATCH `/providers/{provider_id}/`
- GET `/shipments/`
- POST `/shipments/`
- GET `/shipments/{shipment_id}/`
- PATCH `/shipments/{shipment_id}/status/`
- POST `/track/`
- POST `/webhooks/{carrier}/`

---

## Subscriptions

- GET `/`
- POST `/`
- POST `/calculate-cost/`
- GET `/plans/`
- POST `/trigger-notifications/`
- POST `/trigger-order-processing/`
- DELETE `/{subscription_id}/`
- GET `/{subscription_id}/`
- PATCH `/{subscription_id}/`
- PATCH `/{subscription_id}/auto-renew/`
- POST `/{subscription_id}/cancel/`
- GET `/{subscription_id}/details/`
- POST `/{subscription_id}/discounts/`
- DELETE `/{subscription_id}/discounts/{discount_id}/`
- GET `/{subscription_id}/orders/`
- POST `/{subscription_id}/pause/`
- POST `/{subscription_id}/process-shipment/`
- DELETE `/{subscription_id}/products/`
- POST `/{subscription_id}/products/`
- PATCH `/{subscription_id}/products/adjust-quantity/`
- GET `/{subscription_id}/products/quantities/`
- PATCH `/{subscription_id}/products/quantity/`
- DELETE `/{subscription_id}/products/{product_id}/`
- POST `/{subscription_id}/resume/`

---

## Tax

- POST `/calculate/`
- GET `/countries/`
- GET `/rates/`
- POST `/rates/` , response_model=RateResponse, status_code=status.HTTP_201_CREATED
- POST `/rates/bulk-update/`
- DELETE `/rates/{tax_rate_id}/`
- GET `/rates/{tax_rate_id}/` , response_model=RateResponse
- PATCH `/rates/{tax_rate_id}/` , response_model=RateResponse
- GET `/tax-types/`

---

## Webhooks

- GET `/health/`
- POST `/stripe/`

---

## Contact Messages

- GET `/`
- POST `/`
- DELETE `/{message_id}/`
- GET `/{message_id}/`
- PATCH `/{message_id}/`

---

## Health

- GET `/`

---

