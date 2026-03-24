#!/bin/bash

LOGIN=$(curl -s -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@banwee.com","password":"Test1234!"}')
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
BASE="http://localhost:8000/v1"
H="Authorization: Bearer $TOKEN"

t() {
  local label=$1 method=$2 url=$3; shift 3
  local out=$(curl -s -X "$method" "$url" "$@" -w "\n__S:%{http_code}")
  local code=$(echo "$out" | grep -o '__S:[0-9]*' | cut -d: -f2)
  local body=$(echo "$out" | sed 's/__S:[0-9]*$//')
  if echo "$label" | grep -qE "health|webhook"; then
    local msg=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK:'+str(d.get('status','?')))" 2>/dev/null || echo "HTTP$code")
  else
    local msg=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('success') else 'FAIL:'+str(d.get('message',''))[:70])" 2>/dev/null || echo "HTTP$code")
  fi
  printf "%-46s [%s] %s\n" "$label" "$code" "$msg"
}

echo "=== HEALTH ==="
t "health/live"                GET "$BASE/health/live"
t "health/ready"               GET "$BASE/health/ready"

echo ""
echo "=== AUTH ==="
t "auth/profile"               GET "$BASE/auth/profile"              -H "$H"
t "users/me"                   GET "$BASE/users/me"                  -H "$H"
t "users/profile"              GET "$BASE/users/profile"             -H "$H"
t "users/me/addresses"         GET "$BASE/users/me/addresses"        -H "$H"

echo ""
echo "=== CATALOG ==="
t "products list"              GET "$BASE/products/"
t "categories list"            GET "$BASE/categories/"
t "search"                     GET "$BASE/search/?q=test"
t "search autocomplete"        GET "$BASE/search/autocomplete?q=te"
t "reviews for product"        GET "$BASE/reviews/product/00000000-0000-0000-0000-000000000001"

echo ""
echo "=== COMMERCE ==="
t "cart get"                   GET "$BASE/cart/"                     -H "$H"
t "cart count"                 GET "$BASE/cart/count"                -H "$H"
t "orders list"                GET "$BASE/orders/"                   -H "$H"
t "wishlist get"               GET "$BASE/wishlist/"                 -H "$H"
t "shipping methods"           GET "$BASE/shipping/methods"
t "shipping calculate"         POST "$BASE/shipping/calculate"       -H "$H" -H "Content-Type: application/json" -d '{"order_amount":100,"destination_country":"US"}'
t "tax calculate"              POST "$BASE/tax/calculate"            -H "$H" -H "Content-Type: application/json" -d '{"subtotal":100,"country_code":"US"}'
t "payments list"              GET "$BASE/payments/"                 -H "$H"
t "payments methods"           GET "$BASE/payments/methods"          -H "$H"
t "payments transactions"      GET "$BASE/payments/transactions"     -H "$H"
t "refunds list"               GET "$BASE/refunds/"                  -H "$H"
t "subscriptions list"         GET "$BASE/subscriptions/"            -H "$H"
t "contact-messages POST"      POST "$BASE/contact-messages"         -H "Content-Type: application/json" -d '{"name":"Test User","email":"t@t.com","subject":"Hello","message":"This is a test message"}'

echo ""
echo "=== INVENTORY (admin-only, expect 403) ==="
t "inventory list"             GET "$BASE/inventory/"                -H "$H"
t "inventory warehouses"       GET "$BASE/inventory/warehouse-locations" -H "$H"

echo ""
echo "=== SHIPPING TRACKING ==="
t "shipping-tracking carriers"    GET "$BASE/shipping-tracking/carriers"
t "shipping-tracking shipments"   GET "$BASE/shipping-tracking/shipments"  -H "$H"
t "shipping-tracking providers"   GET "$BASE/shipping-tracking/providers"  -H "$H"

echo ""
echo "=== SYSTEM ==="
t "contact-messages list (admin)" GET "$BASE/contact-messages"       -H "$H"
t "webhooks health"               GET "$BASE/webhooks/health"
