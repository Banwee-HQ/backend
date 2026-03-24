#!/bin/bash

ADMIN_TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@banwee.com","password":"Admin1234!"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

BASE="http://localhost:8000/v1"
A="Authorization: Bearer $ADMIN_TOKEN"
CT="Content-Type: application/json"

t() {
  local label=$1 method=$2 url=$3; shift 3
  local out=$(curl -s -X "$method" "$url" "$@" -w "\n__S:%{http_code}")
  local code=$(echo "$out" | grep -o '__S:[0-9]*' | cut -d: -f2)
  local body=$(echo "$out" | sed 's/__S:[0-9]*$//')
  local msg=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK' if d.get('success') else 'FAIL:'+str(d.get('message',''))[:70])" 2>/dev/null || echo "HTTP$code")
  printf "%-50s [%s] %s\n" "$label" "$code" "$msg"
}

echo "=== ADMIN DASHBOARD ==="
t "admin/dashboard"                GET "$BASE/admin/dashboard"              -H "$A"
t "admin/stats"                    GET "$BASE/admin/stats"                  -H "$A"

echo ""
echo "=== ADMIN USERS ==="
t "admin/users list"               GET "$BASE/admin/users"                  -H "$A"

echo ""
echo "=== ADMIN PRODUCTS ==="
t "admin/products list"            GET "$BASE/admin/products"               -H "$A"
t "admin/variants list"            GET "$BASE/admin/variants"               -H "$A"
t "admin/recalculate-ratings"      POST "$BASE/admin/recalculate-ratings"   -H "$A"
t "admin/sync-inventory"           POST "$BASE/admin/sync-inventory"        -H "$A"

echo ""
echo "=== ADMIN CATEGORIES ==="
t "admin/categories list"          GET "$BASE/admin/categories"             -H "$A"

echo ""
echo "=== ADMIN ORDERS ==="
t "admin/orders list"              GET "$BASE/admin/orders"                 -H "$A"

echo ""
echo "=== ADMIN REFUNDS ==="
t "admin/refunds list"             GET "$BASE/admin/refunds"                -H "$A"

echo ""
echo "=== ADMIN SUBSCRIPTIONS ==="
t "admin/subscriptions list"       GET "$BASE/admin/subscriptions"          -H "$A"

echo ""
echo "=== ADMIN SHIPPING ==="
t "admin/shipping-methods list"    GET "$BASE/admin/shipping-methods"       -H "$A"

echo ""
echo "=== ADMIN TAX ==="
t "admin/tax-rates list"           GET "$BASE/admin/tax-rates/"             -H "$A"
t "admin/tax-rates countries"      GET "$BASE/admin/tax-rates/countries"    -H "$A"

echo ""
echo "=== ADMIN PAYMENTS ==="
t "admin/payments list"            GET "$BASE/admin/payments"               -H "$A"

echo ""
echo "=== ANALYTICS ==="
t "analytics/dashboard"            GET "$BASE/analytics/dashboard"          -H "$A"
t "analytics/revenue"              GET "$BASE/analytics/revenue"            -H "$A"
t "analytics/kpis"                 GET "$BASE/analytics/kpis"               -H "$A"
t "analytics/sales-overview"       GET "$BASE/analytics/sales-overview"     -H "$A"
t "analytics/conversion-rates"     GET "$BASE/analytics/conversion-rates"   -H "$A"
t "analytics/cart-abandonment"     GET "$BASE/analytics/cart-abandonment"   -H "$A"
t "analytics/refund-rates"         GET "$BASE/analytics/refund-rates"       -H "$A"
t "analytics/repeat-customers"     GET "$BASE/analytics/repeat-customers"   -H "$A"

echo ""
echo "=== INVENTORY (admin) ==="
t "inventory list"                 GET "$BASE/inventory/"                   -H "$A"
t "inventory warehouses"           GET "$BASE/inventory/locations"          -H "$A"

echo ""
echo "=== SHIPPING TRACKING (admin) ==="
t "shipping-tracking providers"    GET "$BASE/shipping-tracking/providers"  -H "$A"

echo ""
echo "=== CONTACT MESSAGES (admin) ==="
t "contact-messages list"          GET "$BASE/contact-messages"             -H "$A"

echo ""
echo "=== PROMOCODES (admin) ==="
t "promocodes list"                GET "$BASE/promocodes/"                  -H "$A"
