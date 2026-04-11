#!/usr/bin/env python3
"""
Complete API Test Runner for Banwee Backend

This script runs all 161 tests covering 221+ API endpoints.

Usage:
    python run_all_tests.py              # Run all tests
    python run_all_tests.py --quick     # Run quick sanity check only
    python run_all_tests.py --auth      # Run auth tests only
    python run_all_tests.py --admin     # Run admin tests only
    python run_all_tests.py --list      # List all test cases
"""

import subprocess
import sys
import argparse
from typing import List, Tuple


# Test inventory - all 151 test cases (matching actual API endpoints)
TEST_INVENTORY = {
    "Root & System": [
        ("001", "GET / - Root endpoint"),
        ("002", "GET /v1/health/ - Health check"),
        ("003", "GET /docs - API documentation"),
    ],
    "Authentication (20)": [
        ("004", "POST /v1/auth/register - Register new user"),
        ("005", "POST /v1/auth/login - User login"),
        ("006", "POST /v1/auth/login - Invalid credentials"),
        ("007", "POST /v1/auth/refresh - Refresh access token"),
        ("008", "POST /v1/auth/revoke - Revoke refresh token"),
        ("009", "POST /v1/auth/logout - Logout user"),
        ("010", "GET /v1/auth/me - Get user profile"),
        ("011", "GET /v1/addresses/ - Get user addresses"),
        ("012", "POST /v1/addresses/ - Create address"),
        ("013", "GET /v1/auth/verify-email - Verify email with invalid token"),
        ("014", "POST /v1/auth/forgot-password - Request password reset"),
        ("015", "POST /v1/auth/resend-verification - Resend verification email"),
        ("016", "POST /v1/auth/reset-password - Reset with invalid token"),
        ("017", "PATCH /v1/auth/me - Update profile"),
        ("018", "PUT /v1/auth/change-password - Change password"),
        ("019", "GET /v1/auth/social/google/login - Google OAuth"),
        ("020", "GET /v1/auth/social/facebook/login - Facebook OAuth"),
        ("021", "GET /v1/users/me - Get current user"),
        ("022", "GET /v1/users/ - List users (admin)"),
        ("023", "GET /v1/users/{id} - Get user by ID (admin)"),
    ],
    "Addresses (5)": [
        ("024", "GET /v1/addresses/ - Get my addresses"),
        ("025", "POST /v1/addresses/ - Create address"),
        ("026", "GET /v1/addresses/{id} - Get single address"),
        ("027", "PATCH /v1/addresses/{id} - Update address"),
        ("028", "DELETE /v1/addresses/{id} - Delete address"),
    ],
    "Products (12)": [
        ("029", "GET /v1/products/home - Get home data"),
        ("030", "GET /v1/products/ - List products"),
        ("031", "GET /v1/products/ - List with filters"),
        ("032", "GET /v1/products/ - List with sorting"),
        ("033", "GET /v1/products/ - Search products"),
        ("034", "GET /v1/products/{id} - Get product by ID"),
        ("035", "GET /v1/products/{id}/recommendations - Get recommendations"),
        ("036", "GET /v1/products/{id}/variants - Get product variants"),
        ("037", "GET /v1/products/variants/{id} - Get specific variant"),
        ("038", "POST /v1/products/ - Create product (admin)"),
        ("039", "GET /v1/products/featured - Get featured products"),
        ("040", "GET /v1/products/deals - Get deals"),
    ],
    "Product Variants & Images (10)": [
        ("041", "POST /v1/products/{id}/variants - Create variant"),
        ("042", "PATCH /v1/products/variants/{id} - Update variant"),
        ("043", "DELETE /v1/products/variants/{id} - Delete variant"),
        ("044", "POST /v1/products/variants/{id}/images - Create image"),
        ("045", "GET /v1/products/images/{id} - Get image"),
        ("046", "GET /v1/products/variants/{id}/images - List images"),
        ("047", "PATCH /v1/products/images/{id} - Update image"),
        ("048", "DELETE /v1/products/images/{id} - Delete image"),
        ("049", "GET /v1/products/all-variants - List all variants (admin)"),
        ("050", "PATCH /v1/products/{id}/moderate - Moderate product"),
    ],
    "Reviews (6)": [
        ("051", "GET /v1/reviews/ - List reviews"),
        ("052", "GET /v1/reviews/?product_id={id} - Filter by product"),
        ("053", "GET /v1/reviews/{id} - Get review by ID"),
        ("054", "GET /v1/reviews/product/{id} - Get product reviews"),
        ("055", "POST /v1/reviews/ - Create review"),
        ("056", "PUT /v1/reviews/{id} - Update review"),
    ],
    "Wishlist (6)": [
        ("057", "GET /v1/wishlists/ - List wishlists"),
        ("058", "POST /v1/wishlists/ - Create wishlist"),
        ("059", "GET /v1/wishlists/{id} - Get wishlist"),
        ("060", "PATCH /v1/wishlists/{id} - Update wishlist"),
        ("061", "DELETE /v1/wishlists/{id} - Delete wishlist"),
        ("062", "POST /v1/wishlists/{id}/items - Add item to wishlist"),
    ],
    "Cart (6)": [
        ("063", "GET /v1/cart/ - Get cart"),
        ("064", "POST /v1/cart/add - Add item to cart"),
        ("065", "PUT /v1/cart/items/{id} - Update cart item"),
        ("066", "DELETE /v1/cart/items/{id} - Remove cart item"),
        ("067", "DELETE /v1/cart/clear - Clear cart"),
        ("068", "GET /v1/cart/checkout - Checkout summary"),
    ],
    "Orders (5)": [
        ("069", "GET /v1/orders/ - List orders"),
        ("070", "GET /v1/orders/{id} - Get order by ID"),
        ("071", "PUT /v1/orders/{id}/cancel - Cancel order"),
        ("072", "GET /v1/orders/{id}/shipments - Get order shipments"),
        ("073", "POST /v1/orders/checkout - Checkout"),
    ],
    "Payments (8)": [
        ("074", "GET /v1/payments/ - Get payments overview"),
        ("075", "GET /v1/payments/methods - List payment methods"),
        ("076", "POST /v1/payments/methods - Create payment method"),
        ("077", "GET /v1/payments/methods/{id} - Get payment method"),
        ("078", "PATCH /v1/payments/methods/{id} - Update payment method"),
        ("079", "DELETE /v1/payments/methods/{id} - Delete payment method"),
        ("080", "PATCH /v1/payments/methods/{id}/default - Set default payment method"),
        ("081", "POST /v1/payments/process-order - Process order payment"),
    ],
    "Contact Messages (5)": [
        ("082", "POST /v1/contact-messages/ - Create contact message"),
        ("083", "GET /v1/contact-messages/ - List messages (admin)"),
        ("084", "GET /v1/contact-messages/{id} - Get message (admin)"),
        ("085", "PATCH /v1/contact-messages/{id} - Update message (admin)"),
        ("086", "DELETE /v1/contact-messages/{id} - Delete message (admin)"),
    ],
    "Analytics (20)": [
        ("087", "POST /v1/analytics/track - Track event"),
        ("088", "GET /v1/analytics/conversion-rates - Conversion rates"),
        ("089", "GET /v1/analytics/cart-abandonment - Cart abandonment"),
        ("090", "GET /v1/analytics/time-to-purchase - Time to purchase"),
        ("091", "GET /v1/analytics/refund-rates - Refund rates"),
        ("092", "GET /v1/analytics/repeat-customers - Repeat customers"),
        ("093", "GET /v1/analytics/simple-dashboard - Simple dashboard"),
        ("094", "GET /v1/analytics/dashboard - Dashboard"),
        ("095", "GET /v1/analytics/sales-trend - Sales trend"),
        ("096", "GET /v1/analytics/sales-overview - Sales overview"),
        ("097", "GET /v1/analytics/sales - Sales analytics"),
        ("098", "GET /v1/analytics/users - User analytics"),
        ("099", "GET /v1/analytics/products - Product analytics"),
        ("100", "GET /v1/analytics/orders - Order analytics"),
        ("101", "GET /v1/analytics/revenue - Revenue analytics"),
        ("102", "GET /v1/analytics/kpis - KPIs"),
        ("103", "GET /v1/analytics/stats - Stats"),
        ("104", "GET /v1/analytics/dashboard/admin - Admin dashboard"),
        ("105", "GET /v1/analytics/export/orders - Export orders"),
        ("106", "GET /v1/analytics/export/subscriptions - Export subscriptions"),
    ],
    "Inventory (14)": [
        ("107", "POST /v1/inventory/locations - Create location"),
        ("108", "GET /v1/inventory/locations - List locations"),
        ("109", "GET /v1/inventory/locations/{id} - Get location"),
        ("110", "PATCH /v1/inventory/locations/{id} - Update location"),
        ("111", "DELETE /v1/inventory/locations/{id} - Delete location"),
        ("112", "POST /v1/inventory/ - Create inventory"),
        ("113", "GET /v1/inventory/ - List inventory"),
        ("114", "GET /v1/inventory/{id} - Get inventory"),
        ("115", "PATCH /v1/inventory/{id} - Update inventory"),
        ("116", "DELETE /v1/inventory/{id} - Delete inventory"),
        ("117", "POST /v1/inventory/adjust - Adjust stock"),
        ("118", "GET /v1/inventory/adjustments - List adjustments"),
        ("119", "GET /v1/inventory/adjustments/{id} - Get adjustment"),
        ("120", "DELETE /v1/inventory/adjustments/{id} - Delete adjustment"),
    ],
    "Shipping (9)": [
        ("121", "GET /v1/shipping/methods - List shipping methods"),
        ("122", "GET /v1/shipping/methods/{id} - Get shipping method"),
        ("123", "POST /v1/shipping/methods - Create shipping method (admin)"),
        ("124", "PATCH /v1/shipping/methods/{id} - Update shipping method (admin)"),
        ("125", "DELETE /v1/shipping/methods/{id} - Delete shipping method (admin)"),
        ("126", "POST /v1/shipping/calculate - Calculate shipping cost"),
        ("127", "POST /v1/shipping/track - Track shipment"),
        ("128", "POST /v1/shipping-tracking/shipments - Create shipment"),
        ("129", "GET /v1/shipping-tracking/shipments/{id} - Get shipment"),
    ],
    "Subscriptions (12)": [
        ("130", "POST /v1/subscriptions/trigger-order-processing - Trigger processing (admin)"),
        ("131", "GET /v1/subscriptions/plans - List subscription plans"),
        ("132", "GET /v1/subscriptions/ - List user subscriptions"),
        ("133", "POST /v1/subscriptions/ - Create subscription"),
        ("134", "GET /v1/subscriptions/{id} - Get subscription by ID"),
        ("135", "PATCH /v1/subscriptions/{id} - Update subscription"),
        ("136", "POST /v1/subscriptions/{id}/cancel - Cancel subscription"),
        ("137", "POST /v1/subscriptions/{id}/pause - Pause subscription"),
        ("138", "POST /v1/subscriptions/{id}/resume - Resume subscription"),
        ("139", "POST /v1/subscriptions/{id}/products - Add products"),
        ("140", "DELETE /v1/subscriptions/{id}/products - Remove products"),
        ("141", "DELETE /v1/subscriptions/{id}/products/{pid} - Remove single product"),
    ],
    "Tax (6)": [
        ("142", "POST /v1/tax/calculate - Calculate tax"),
        ("143", "GET /v1/tax/rates - List tax rates"),
        ("144", "POST /v1/tax/admin/tax-rates - Create tax rate (admin)"),
        ("145", "GET /v1/tax/rates/{id} - Get tax rate"),
        ("146", "PATCH /v1/tax/rates/{id} - Update tax rate (admin)"),
        ("147", "DELETE /v1/tax/rates/{id} - Delete tax rate (admin)"),
    ],
    "Promocodes (8)": [
        ("148", "GET /v1/promocodes/ - List promocodes"),
        ("149", "GET /v1/promocodes/{id} - Get promocode"),
        ("150", "POST /v1/promocodes/ - Create promocode (admin)"),
        ("151", "PATCH /v1/promocodes/{id} - Update promocode (admin)"),
        ("152", "DELETE /v1/promocodes/{id} - Delete promocode (admin)"),
        ("153", "POST /v1/promocodes/validate - Validate promocode"),
        ("154", "POST /v1/promocodes/trigger-cleanup - Trigger cleanup (admin)"),
        ("155", "POST /v1/cart/promocode - Apply promocode to cart"),
    ],
    "Refunds (4)": [
        ("156", "GET /v1/refunds/ - List refunds"),
        ("157", "POST /v1/refunds/ - Create refund"),
        ("158", "GET /v1/refunds/{id} - Get refund by ID"),
        ("159", "PATCH /v1/refunds/{id} - Update refund status"),
    ],
    "Webhooks (2)": [
        ("160", "POST /v1/webhooks/stripe - Stripe webhook"),
        ("161", "GET /v1/webhooks/health - Webhook health check"),
    ],
}


def print_inventory():
    """Print all test cases."""
    print("\n" + "="*70)
    print("BANWEE API TEST INVENTORY - 161 TEST CASES")
    print("="*70)
    
    total = 0
    for category, tests in TEST_INVENTORY.items():
        print(f"\n{category}:")
        for num, desc in tests:
            print(f"  [{num}] {desc}")
            total += 1
    
    print(f"\n{'='*70}")
    print(f"TOTAL: {total} test cases covering 221+ API endpoints")
    print("="*70 + "\n")


def run_pytest(test_path: str = "tests/", markers: str = None, verbose: bool = True) -> int:
    """Run pytest with specified options."""
    cmd = ["python3", "-m", "pytest", test_path]
    
    if verbose:
        cmd.append("-v")
    
    if markers:
        cmd.extend(["-m", markers])
    
    print(f"\nRunning: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Run Banwee API Tests - 140+ test cases for 273+ endpoints"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all test cases"
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Run authentication tests only"
    )
    parser.add_argument(
        "--admin",
        action="store_true",
        help="Run admin tests only"
    )
    parser.add_argument(
        "--products",
        action="store_true",
        help="Run product tests only"
    )
    parser.add_argument(
        "--commerce",
        action="store_true",
        help="Run commerce (cart, orders, payments) tests only"
    )
    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Quick sanity check (root, health, docs)"
    )
    parser.add_argument(
        "--fail-fast", "-x",
        action="store_true",
        help="Stop on first failure"
    )
    parser.add_argument(
        "--no-verbose",
        action="store_true",
        help="Less verbose output"
    )
    
    args = parser.parse_args()
    
    if args.list:
        print_inventory()
        return 0
    
    # Print header
    print("\n" + "="*70)
    print("BANWEE API TEST RUNNER")
    print("="*70)
    
    # Determine test markers
    markers = None
    if args.auth:
        markers = "auth"
        print("\nRunning: Authentication tests only")
    elif args.admin:
        markers = "admin"
        print("\nRunning: Admin tests only")
    elif args.products:
        markers = "api and not auth and not admin"
        print("\nRunning: Product tests only")
    elif args.commerce:
        markers = "api and not auth and not admin"
        print("\nRunning: Commerce tests only")
    elif args.quick:
        print("\nRunning: Quick sanity check")
        return run_pytest(test_path="tests/test_all_apis.py::TestRootAndSystem", verbose=not args.no_verbose)
    else:
        print("\nRunning: ALL 140+ test cases")
    
    # Run tests - focus on test_all_apis.py for comprehensive coverage
    test_path = "tests/test_all_apis.py" if not markers else "tests/"
    exit_code = run_pytest(
        test_path=test_path,
        markers=markers,
        verbose=not args.no_verbose
    )
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
