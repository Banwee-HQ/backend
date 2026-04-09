#!/bin/bash
# ============================================================
# Banwee Full API Test Suite
# ============================================================
BASE="http://localhost:8000/v1"
PASS=0; FAIL=0; SKIP=0
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

TOKEN=""; ADMIN_TOKEN=""; REFRESH_TOKEN=""
ADDRESS_ID=""; PRODUCT_ID=""; VARIANT_ID=""
CART_ITEM_ID=""; ORDER_ID=""; REVIEW_ID=""; PAYMENT_METHOD_ID=""
SHIPPING_METHOD_ID=""; PROMO_ID=""; SUBSCRIPTION_ID=""
CONTACT_MSG_ID=""; TAX_RATE_ID=""; PROMO_CODE=""

section() { echo -e "\n${BLUE}══════════════════════════════════════${NC}\n  ${BLUE}$1${NC}\n${BLUE}══════════════════════════════════════${NC}"; }

check() {
  local label="$1" status="$2" body="$3" expected="${4:-200}"
  if [ "$status" -eq "$expected" ] || ([ "$expected" == "2xx" ] && [ "$status" -ge 200 ] && [ "$status" -lt 300 ]); then
    echo -e "  ${GREEN}✓${NC} $label (HTTP $status)"; PASS=$((PASS+1))
  else
    echo -e "  ${RED}✗${NC} $label (HTTP $status)"
    MSG=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('message','')[:150])" 2>/dev/null || echo "$body" | head -c 150)
    echo -e "    ${YELLOW}$MSG${NC}"; FAIL=$((FAIL+1))
  fi
}
skip() { echo -e "  ${YELLOW}⊘${NC} $1 (skipped)"; SKIP=$((SKIP+1)); }

# HTTP helpers
_get()       { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$BASE$1"; }
_aget()      { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $ADMIN_TOKEN" "$BASE$1"; }
_post()      { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$2" "$BASE$1"; }
_apost()     { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d "$2" "$BASE$1"; }
_put()       { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$2" -X PUT "$BASE$1"; }
_aput()      { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d "$2" -X PUT "$BASE$1"; }
_patch()     { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$2" -X PATCH "$BASE$1"; }
_apatch()    { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d "$2" -X PATCH "$BASE$1"; }
_del()       { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $TOKEN" -X DELETE "$BASE$1"; }
_adel()      { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Authorization: Bearer $ADMIN_TOKEN" -X DELETE "$BASE$1"; }
_pub()       { curl -s -o /tmp/resp.json -w "%{http_code}" "$BASE$1"; }
_pub_post()  { curl -s -o /tmp/resp.json -w "%{http_code}" -H "Content-Type: application/json" -d "$2" "$BASE$1"; }
body()       { cat /tmp/resp.json; }
jv()         { cat /tmp/resp.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d$1)" 2>/dev/null; }

# ============================================================
section "HEALTH"
# ============================================================
S=$(_pub "/health/"); check "GET /health/" "$S" "$(body)"

# ============================================================
section "AUTH — Register & Login"
# ============================================================
TS=$(date +%s)
TEST_EMAIL="testuser_${TS}@banwee.com"
TEST_PASS="TestPass123!"

S=$(_pub_post "/auth/register" "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASS\",\"firstname\":\"Test\",\"lastname\":\"User\"}")
check "POST /auth/register (welcome email)" "$S" "$(body)" 200

S=$(_pub_post "/auth/login" "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASS\"}")
check "POST /auth/login" "$S" "$(body)" 200
TOKEN=$(jv "['data']['access_token']")
REFRESH_TOKEN=$(jv "['data']['refresh_token']")

# Get admin token
S=$(_pub_post "/auth/login" "{\"email\":\"admin@banwee.com\",\"password\":\"AdminPass123!\"}")
check "POST /auth/login (admin)" "$S" "$(body)" 200
ADMIN_TOKEN=$(jv "['data']['access_token']")

S=$(_pub_post "/auth/refresh" "{\"refresh_token\":\"$REFRESH_TOKEN\"}")
check "POST /auth/refresh" "$S" "$(body)" 200
NEW_TOKEN=$(jv "['data']['access_token']"); [ -n "$NEW_TOKEN" ] && TOKEN="$NEW_TOKEN"

S=$(_get "/auth/profile"); check "GET /auth/profile" "$S" "$(body)" 200
S=$(_put "/auth/profile" "{\"firstname\":\"Updated\",\"lastname\":\"User\"}"); check "PUT /auth/profile" "$S" "$(body)" 200

S=$(curl -s -o /tmp/resp.json -w "%{http_code}" -H "Content-Type: application/json" -H "X-Resend-Token: abcdefghijklmnop" -d "{\"email\":\"$TEST_EMAIL\"}" "$BASE/auth/resend-verification")
check "POST /auth/resend-verification (email)" "$S" "$(body)" 200

S=$(_pub_post "/auth/forgot-password" "{\"email\":\"$TEST_EMAIL\"}")
check "POST /auth/forgot-password (email)" "$S" "$(body)" 200

# ============================================================
section "AUTH — Addresses"
# ============================================================
S=$(_get "/auth/addresses"); check "GET /auth/addresses" "$S" "$(body)" 200

S=$(_post "/auth/addresses" "{\"street\":\"123 Test St\",\"city\":\"Accra\",\"state\":\"Greater Accra\",\"post_code\":\"00233\",\"country\":\"GH\",\"is_default\":true}")
check "POST /auth/addresses" "$S" "$(body)" 200
ADDRESS_ID=$(jv "['data']['id']")

if [ -n "$ADDRESS_ID" ]; then
  S=$(_put "/auth/addresses/$ADDRESS_ID" "{\"city\":\"Kumasi\"}"); check "PUT /auth/addresses/{id}" "$S" "$(body)" 200
else skip "PUT /auth/addresses/{id}"; fi

# ============================================================
section "PRODUCTS"
# ============================================================
S=$(_pub "/products/"); check "GET /products/" "$S" "$(body)" 200
PRODUCT_ID=$(jv "['data']['data'][0]['id']" 2>/dev/null)

S=$(_pub "/products/home"); check "GET /products/home" "$S" "$(body)" 200

if [ -n "$PRODUCT_ID" ]; then
  S=$(_pub "/products/$PRODUCT_ID"); check "GET /products/{id}" "$S" "$(body)" 200
  S=$(_pub "/products/$PRODUCT_ID/variants"); check "GET /products/{id}/variants" "$S" "$(body)" 200
  VARIANT_ID=$(jv "['data'][0]['id']" 2>/dev/null)
  S=$(_pub "/products/$PRODUCT_ID/recommendations"); check "GET /products/{id}/recommendations" "$S" "$(body)" 200
else
  skip "GET /products/{id}"; skip "GET /products/{id}/variants"; skip "GET /products/{id}/recommendations"
fi

# ============================================================
section "REVIEWS"
# ============================================================
S=$(_pub "/reviews/"); check "GET /reviews/" "$S" "$(body)" 200

if [ -n "$PRODUCT_ID" ]; then
  S=$(_post "/reviews/" "{\"product_id\":\"$PRODUCT_ID\",\"rating\":5,\"comment\":\"Great product!\"}"); check "POST /reviews/" "$S" "$(body)" 200
  REVIEW_ID=$(jv "['data']['id']" 2>/dev/null)
  S=$(_pub "/reviews/product/$PRODUCT_ID"); check "GET /reviews/product/{id}" "$S" "$(body)" 200
  if [ -n "$REVIEW_ID" ]; then
    S=$(_put "/reviews/$REVIEW_ID" "{\"rating\":4,\"comment\":\"Updated\"}"); check "PUT /reviews/{id}" "$S" "$(body)" 200
    S=$(_del "/reviews/$REVIEW_ID"); check "DELETE /reviews/{id}" "$S" "$(body)" 200
  else skip "PUT /reviews/{id}"; skip "DELETE /reviews/{id}"; fi
else skip "POST /reviews/"; skip "GET /reviews/product/{id}"; fi

# ============================================================
section "WISHLIST"
# ============================================================
S=$(_get "/wishlist/"); check "GET /wishlist/" "$S" "$(body)" 200

if [ -n "$PRODUCT_ID" ]; then
  WISH_BODY="{\"product_id\":\"$PRODUCT_ID\""
  [ -n "$VARIANT_ID" ] && WISH_BODY="$WISH_BODY,\"variant_id\":\"$VARIANT_ID\""
  WISH_BODY="$WISH_BODY}"
  S=$(_post "/wishlist/add" "$WISH_BODY"); check "POST /wishlist/add" "$S" "$(body)" 200
  S=$(_del "/wishlist/items/$PRODUCT_ID"); check "DELETE /wishlist/items/{product_id}" "$S" "$(body)" 200
else skip "POST /wishlist/add"; skip "DELETE /wishlist/items/{product_id}"; fi

# ============================================================
section "INVENTORY (admin)"
# ============================================================
S=$(_aget "/inventory/locations"); check "GET /inventory/locations (admin)" "$S" "$(body)" 200
S=$(_aget "/inventory/"); check "GET /inventory/ (admin)" "$S" "$(body)" 200
S=$(_aget "/inventory/adjustments/all"); check "GET /inventory/adjustments/all (admin)" "$S" "$(body)" 200

if [ -n "$VARIANT_ID" ]; then
  S=$(_pub "/inventory/check-stock/$VARIANT_ID"); check "GET /inventory/check-stock/{variant_id}" "$S" "$(body)" 200
  S=$(_post "/inventory/check-stock/bulk" "{\"variant_ids\":[\"$VARIANT_ID\"]}"); check "POST /inventory/check-stock/bulk" "$S" "$(body)" 200
else skip "GET /inventory/check-stock/{variant_id}"; skip "POST /inventory/check-stock/bulk"; fi

# ============================================================
section "CART"
# ============================================================
S=$(_get "/cart/"); check "GET /cart/" "$S" "$(body)" 200
S=$(_get "/cart/count"); check "GET /cart/count" "$S" "$(body)" 200

if [ -n "$VARIANT_ID" ]; then
  S=$(_post "/cart/add" "{\"variant_id\":\"$VARIANT_ID\",\"quantity\":1}"); check "POST /cart/add" "$S" "$(body)" 200
  CART_ITEM_ID=$(jv "['data']['items'][0]['id']" 2>/dev/null)
  S=$(_post "/cart/validate" "{}"); check "POST /cart/validate" "$S" "$(body)" 200
  S=$(_post "/cart/calculate" "{}"); check "POST /cart/calculate" "$S" "$(body)" 200
  S=$(_get "/cart/checkout-summary"); check "GET /cart/checkout-summary" "$S" "$(body)" 200
  if [ -n "$CART_ITEM_ID" ]; then
    S=$(_put "/cart/items/$CART_ITEM_ID" "{\"quantity\":2}"); check "PUT /cart/items/{id}" "$S" "$(body)" 200
    S=$(_del "/cart/items/$CART_ITEM_ID"); check "DELETE /cart/items/{id}" "$S" "$(body)" 200
  else skip "PUT /cart/items/{id}"; skip "DELETE /cart/items/{id}"; fi
else skip "POST /cart/add"; skip "POST /cart/validate"; skip "POST /cart/calculate"; skip "GET /cart/checkout-summary"; fi

# ============================================================
section "SHIPPING"
# ============================================================
S=$(_pub "/shipping/methods"); check "GET /shipping/methods" "$S" "$(body)" 200
SHIPPING_METHOD_ID=$(jv "['data'][0]['id']" 2>/dev/null)

# ============================================================
section "TAX"
# ============================================================
S=$(_pub_post "/tax/calculate" "{\"subtotal\":100.00,\"shipping\":10.00,\"country_code\":\"GH\",\"currency\":\"USD\"}")
check "POST /tax/calculate" "$S" "$(body)" 200
S=$(_aget "/tax/admin/tax-rates"); check "GET /tax/admin/tax-rates (admin)" "$S" "$(body)" 200
S=$(_aget "/tax/admin/tax-rates/countries"); check "GET /tax/admin/tax-rates/countries (admin)" "$S" "$(body)" 200
S=$(_aget "/tax/admin/tax-rates/tax-types"); check "GET /tax/admin/tax-rates/tax-types (admin)" "$S" "$(body)" 200

# Create a tax rate for testing
S=$(_apost "/tax/admin/tax-rates" "{\"country_code\":\"GH\",\"country_name\":\"Ghana\",\"tax_rate\":0.125,\"tax_name\":\"VAT\",\"is_active\":true}")
check "POST /tax/admin/tax-rates (admin)" "$S" "$(body)" 201
TAX_RATE_ID=$(jv "['id']" 2>/dev/null)
if [ -n "$TAX_RATE_ID" ]; then
  S=$(_aget "/tax/admin/tax-rates/$TAX_RATE_ID"); check "GET /tax/admin/tax-rates/{id} (admin)" "$S" "$(body)" 200
  S=$(_aput "/tax/admin/tax-rates/$TAX_RATE_ID" "{\"tax_rate\":0.15}"); check "PUT /tax/admin/tax-rates/{id} (admin)" "$S" "$(body)" 200
  S=$(_adel "/tax/admin/tax-rates/$TAX_RATE_ID"); check "DELETE /tax/admin/tax-rates/{id} (admin)" "$S" "$(body)" 200
else skip "GET /tax/admin/tax-rates/{id}"; skip "PUT /tax/admin/tax-rates/{id}"; skip "DELETE /tax/admin/tax-rates/{id}"; fi

# ============================================================
section "ORDERS"
# ============================================================
S=$(_get "/orders/"); check "GET /orders/" "$S" "$(body)" 200

if [ -n "$VARIANT_ID" ] && [ -n "$ADDRESS_ID" ] && [ -n "$SHIPPING_METHOD_ID" ]; then
  _post "/cart/add" "{\"variant_id\":\"$VARIANT_ID\",\"quantity\":1}" > /dev/null
  S=$(_post "/orders/checkout/validate" "{\"shipping_address_id\":\"$ADDRESS_ID\",\"shipping_method_id\":\"$SHIPPING_METHOD_ID\",\"payment_method_id\":\"pm_card_visa\"}")
  check "POST /orders/checkout/validate" "$S" "$(body)" 200
  S=$(_post "/orders/checkout" "{\"shipping_address_id\":\"$ADDRESS_ID\",\"shipping_method_id\":\"$SHIPPING_METHOD_ID\",\"payment_method_id\":\"pm_card_visa\",\"currency\":\"USD\",\"country_code\":\"GH\"}")
  check "POST /orders/checkout (order email)" "$S" "$(body)" 200
  ORDER_ID=$(jv "['data']['id']" 2>/dev/null)
else skip "POST /orders/checkout/validate"; skip "POST /orders/checkout"; fi

if [ -n "$ORDER_ID" ]; then
  S=$(_get "/orders/$ORDER_ID"); check "GET /orders/{id}" "$S" "$(body)" 200
  S=$(_get "/orders/$ORDER_ID/tracking"); check "GET /orders/{id}/tracking" "$S" "$(body)" 200
  S=$(_get "/orders/$ORDER_ID/notes"); check "GET /orders/{id}/notes" "$S" "$(body)" 200
  S=$(_post "/orders/$ORDER_ID/notes" "{\"note\":\"Test note\"}"); check "POST /orders/{id}/notes" "$S" "$(body)" 200
  S=$(_get "/orders/$ORDER_ID/invoice"); check "GET /orders/{id}/invoice" "$S" "$(body)" 200
  S=$(_get "/refunds/orders/$ORDER_ID/eligibility"); check "GET /refunds/orders/{id}/eligibility" "$S" "$(body)" 200
else skip "GET /orders/{id}"; skip "GET /orders/{id}/tracking"; skip "GET /orders/{id}/notes"; skip "POST /orders/{id}/notes"; skip "GET /orders/{id}/invoice"; skip "GET /refunds/orders/{id}/eligibility"; fi

# ============================================================
section "PAYMENTS"
# ============================================================
S=$(_get "/payments/"); check "GET /payments/" "$S" "$(body)" 200
S=$(_get "/payments/methods"); check "GET /payments/methods" "$S" "$(body)" 200
S=$(_get "/payments/transactions"); check "GET /payments/transactions" "$S" "$(body)" 200
S=$(_get "/payments/failures/user/failed-payments"); check "GET /payments/failures/user/failed-payments" "$S" "$(body)" 200

# ============================================================
section "REFUNDS"
# ============================================================
S=$(_get "/refunds/"); check "GET /refunds/" "$S" "$(body)" 200
S=$(_get "/refunds/stats/summary"); check "GET /refunds/stats/summary" "$S" "$(body)" 200

# ============================================================
section "PROMOCODES (admin)"
# ============================================================
S=$(_aget "/promocodes/"); check "GET /promocodes/ (admin)" "$S" "$(body)" 200

PROMO_CODE="TEST10_${TS}"
S=$(_apost "/promocodes/" "{\"code\":\"$PROMO_CODE\",\"discount_type\":\"percentage\",\"value\":10,\"is_active\":true,\"valid_from\":\"2026-01-01T00:00:00Z\",\"valid_until\":\"2027-01-01T00:00:00Z\"}")
check "POST /promocodes/ (admin)" "$S" "$(body)" 200
PROMO_ID=$(jv "['data']['id']" 2>/dev/null)

if [ -n "$PROMO_ID" ]; then
  S=$(_aget "/promocodes/$PROMO_ID"); check "GET /promocodes/{id} (admin)" "$S" "$(body)" 200
  S=$(_aput "/promocodes/$PROMO_ID" "{\"value\":15}"); check "PUT /promocodes/{id} (admin)" "$S" "$(body)" 200
else skip "GET /promocodes/{id}"; skip "PUT /promocodes/{id}"; fi

if [ -n "$VARIANT_ID" ] && [ -n "$PROMO_CODE" ]; then
  _post "/cart/add" "{\"variant_id\":\"$VARIANT_ID\",\"quantity\":1}" > /dev/null
  S=$(_post "/cart/promocode" "{\"code\":\"$PROMO_CODE\"}"); check "POST /cart/promocode (apply)" "$S" "$(body)" 200
  S=$(_del "/cart/promocode"); check "DELETE /cart/promocode (remove)" "$S" "$(body)" 200
else skip "POST /cart/promocode"; skip "DELETE /cart/promocode"; fi

# ============================================================
section "SUBSCRIPTIONS"
# ============================================================
S=$(_get "/subscriptions/"); check "GET /subscriptions/" "$S" "$(body)" 200

if [ -n "$VARIANT_ID" ] && [ -n "$ADDRESS_ID" ]; then
  S=$(_post "/subscriptions/calculate-cost" "{\"variant_ids\":[\"$VARIANT_ID\"],\"billing_cycle\":\"monthly\"}")
  check "POST /subscriptions/calculate-cost" "$S" "$(body)" 200
  S=$(_post "/subscriptions/" "{\"name\":\"Test Sub\",\"variant_ids\":[\"$VARIANT_ID\"],\"billing_cycle\":\"monthly\",\"delivery_address_id\":\"$ADDRESS_ID\"}")
  check "POST /subscriptions/ (email)" "$S" "$(body)" 200
  SUBSCRIPTION_ID=$(jv "['data']['id']" 2>/dev/null)
else skip "POST /subscriptions/calculate-cost"; skip "POST /subscriptions/"; fi

if [ -n "$SUBSCRIPTION_ID" ]; then
  S=$(_get "/subscriptions/$SUBSCRIPTION_ID"); check "GET /subscriptions/{id}" "$S" "$(body)" 200
  S=$(_patch "/subscriptions/$SUBSCRIPTION_ID/auto-renew" "{\"auto_renew\":false}"); check "PATCH /subscriptions/{id}/auto-renew" "$S" "$(body)" 200
  S=$(_post "/subscriptions/$SUBSCRIPTION_ID/pause" "{\"pause_reason\":\"Testing\"}"); check "POST /subscriptions/{id}/pause" "$S" "$(body)" 200
  S=$(_post "/subscriptions/$SUBSCRIPTION_ID/resume" "{}"); check "POST /subscriptions/{id}/resume" "$S" "$(body)" 200
  S=$(_get "/subscriptions/$SUBSCRIPTION_ID/products/quantities"); check "GET /subscriptions/{id}/products/quantities" "$S" "$(body)" 200
else skip "GET /subscriptions/{id}"; skip "PATCH /subscriptions/{id}/auto-renew"; skip "POST /subscriptions/{id}/pause"; skip "POST /subscriptions/{id}/resume"; skip "GET /subscriptions/{id}/products/quantities"; fi

# ============================================================
section "SHIPPING TRACKING"
# ============================================================
S=$(_pub "/shipping-tracking/carriers"); check "GET /shipping-tracking/carriers" "$S" "$(body)" 200
S=$(_aget "/shipping-tracking/providers"); check "GET /shipping-tracking/providers (admin)" "$S" "$(body)" 200
S=$(_pub_post "/shipping-tracking/track" "{\"tracking_number\":\"1Z999AA10123456784\"}"); check "POST /shipping-tracking/track" "$S" "$(body)" 200

# ============================================================
section "ANALYTICS"
# ============================================================
S=$(_post "/analytics/track" "{\"event_type\":\"page_view\",\"page_url\":\"/home\"}"); check "POST /analytics/track" "$S" "$(body)" 200
S=$(_get "/analytics/simple-dashboard"); check "GET /analytics/simple-dashboard" "$S" "$(body)" 200
S=$(_get "/analytics/dashboard"); check "GET /analytics/dashboard" "$S" "$(body)" 200
S=$(_aget "/analytics/sales-overview"); check "GET /analytics/sales-overview (admin)" "$S" "$(body)" 200
S=$(_aget "/analytics/kpis"); check "GET /analytics/kpis (admin)" "$S" "$(body)" 200
S=$(_aget "/analytics/revenue"); check "GET /analytics/revenue (admin)" "$S" "$(body)" 200
S=$(_aget "/analytics/conversion-rates"); check "GET /analytics/conversion-rates (admin)" "$S" "$(body)" 200
S=$(_aget "/analytics/cart-abandonment"); check "GET /analytics/cart-abandonment (admin)" "$S" "$(body)" 200
S=$(_aget "/analytics/refund-rates"); check "GET /analytics/refund-rates (admin)" "$S" "$(body)" 200
S=$(_aget "/analytics/repeat-customers"); check "GET /analytics/repeat-customers (admin)" "$S" "$(body)" 200
S=$(_aget "/analytics/sales-trend"); check "GET /analytics/sales-trend (admin)" "$S" "$(body)" 200
S=$(_aget "/analytics/time-to-purchase"); check "GET /analytics/time-to-purchase (admin)" "$S" "$(body)" 200

# ============================================================
section "ADMIN"
# ============================================================
S=$(_aget "/admin/stats"); check "GET /admin/stats" "$S" "$(body)" 200
S=$(_aget "/admin/dashboard"); check "GET /admin/dashboard" "$S" "$(body)" 200
S=$(_aget "/admin/orders"); check "GET /admin/orders" "$S" "$(body)" 200
S=$(_aget "/admin/users"); check "GET /admin/users" "$S" "$(body)" 200
S=$(_aget "/admin/refunds"); check "GET /admin/refunds" "$S" "$(body)" 200
S=$(_aget "/admin/subscriptions"); check "GET /admin/subscriptions" "$S" "$(body)" 200

# ============================================================
section "CONTACT MESSAGES (email)"
# ============================================================
S=$(_pub_post "/contact-messages" "{\"name\":\"Test User\",\"email\":\"test@example.com\",\"subject\":\"Test\",\"message\":\"Hello from test suite\"}")
check "POST /contact-messages" "$S" "$(body)" 201
CONTACT_MSG_ID=$(jv "['data']['id']" 2>/dev/null)

S=$(_aget "/contact-messages"); check "GET /contact-messages (admin)" "$S" "$(body)" 200
if [ -n "$CONTACT_MSG_ID" ]; then
  S=$(_aget "/contact-messages/$CONTACT_MSG_ID"); check "GET /contact-messages/{id} (admin)" "$S" "$(body)" 200
  S=$(_apatch "/contact-messages/$CONTACT_MSG_ID" "{\"status\":\"read\"}"); check "PATCH /contact-messages/{id} (admin)" "$S" "$(body)" 200
  S=$(_adel "/contact-messages/$CONTACT_MSG_ID"); check "DELETE /contact-messages/{id} (admin)" "$S" "$(body)" 200
else skip "GET /contact-messages/{id}"; skip "PATCH /contact-messages/{id}"; skip "DELETE /contact-messages/{id}"; fi

# ============================================================
section "WEBHOOKS"
# ============================================================
S=$(_get "/webhooks/health"); check "GET /webhooks/health" "$S" "$(body)" 200

# ============================================================
section "CLEANUP"
# ============================================================
if [ -n "$ADDRESS_ID" ]; then
  S=$(_del "/auth/addresses/$ADDRESS_ID"); check "DELETE /auth/addresses/{id}" "$S" "$(body)" 200
fi
S=$(_post "/auth/logout" "{}"); check "POST /auth/logout" "$S" "$(body)" 200

# ============================================================
echo ""
echo -e "${BLUE}══════════════════════════════════════${NC}"
echo -e "  ${GREEN}PASSED: $PASS${NC}  ${RED}FAILED: $FAIL${NC}  ${YELLOW}SKIPPED: $SKIP${NC}"
echo -e "${BLUE}══════════════════════════════════════${NC}"
[ $FAIL -eq 0 ] && echo -e "  ${GREEN}All tests passed!${NC}" || echo -e "  ${RED}$FAIL test(s) need attention${NC}"
