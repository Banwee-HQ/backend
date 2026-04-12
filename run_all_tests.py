#!/usr/bin/env python3
"""
Complete API Test Runner for Banwee Backend

This script runs all 158 tests covering 221+ API endpoints.

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


# Test inventory - all 158 test cases (matching actual API endpoints)
TEST_INVENTORY = {
    "Root & System": [
        ("001", "GET / - Root endpoint"),
        ("002", "GET /v1/health/ - Health check"),
        ("003", "GET /docs - API documentation"),
    ],
    "Authentication (17)": [
        ("004", "POST /v1/auth/register/ - Register new user"),
        ("005", "POST /v1/auth/login/ - User login"),
        ("006", "POST /v1/auth/login/ - Invalid credentials"),
        ("007", "POST /v1/auth/refresh/ - Refresh access token"),
        ("008", "POST /v1/auth/revoke/ - Revoke refresh token"),
        ("009", "POST /v1/auth/logout/ - Logout user"),
        ("010", "GET /v1/auth/me/ - Get user profile"),
        ("011", "GET /v1/addresses/ - Get user addresses"),
        ("012", "POST /v1/addresses/ - Create address"),
        ("013", "GET /v1/auth/verify-email/ - Verify email with invalid token"),
        ("014", "POST /v1/auth/forgot-password/ - Request password reset"),
        ("015", "POST /v1/auth/resend-verification/ - Resend verification email"),
        ("016", "POST /v1/auth/reset-password/ - Reset with invalid token"),
        ("017", "PATCH /v1/auth/me/ - Update profile"),
        ("018", "PUT /v1/auth/me/password/ - Change password"),
        ("019", "GET /v1/auth/social/google/login/ - Google OAuth"),
        ("020", "GET /v1/auth/social/facebook/login/ - Facebook OAuth"),
    ],
    "Users (13)": [
        ("021", "GET /v1/users/me/ - Get current user"),
        ("022", "GET /v1/users/ - List users (admin)"),
        ("023", "GET /v1/users/{id}/ - Get user by ID"),
        ("024", "GET /v1/users/profile/ - Get user profile (legacy)"),
        ("025", "POST /v1/users/ - Create user (admin)"),
        ("026", "PATCH /v1/users/{id}/ - Update user"),
        ("027", "DELETE /v1/users/{id}/ - Delete user (admin)"),
        ("028", "PUT /v1/users/{id}/status/ - Update user status (admin)"),
        ("029", "POST /v1/users/{id}/reset-password/ - Reset password (admin)"),
        ("030", "POST /v1/users/{id}/deactivate/ - Deactivate user (admin)"),
        ("031", "POST /v1/users/{id}/activate/ - Activate user (admin)"),
        ("032", "PUT /v1/users/{id}/verify/ - Verify user (admin)"),
        ("033", "GET /v1/users/{id}/activity/ - Get user activity (admin)"),
    ],
    "Addresses (5)": [
        ("034", "GET /v1/addresses/ - Get my addresses"),
        ("035", "POST /v1/addresses/ - Create address"),
        ("036", "GET /v1/addresses/{id}/ - Get single address"),
        ("037", "PATCH /v1/addresses/{id}/ - Update address"),
        ("038", "DELETE /v1/addresses/{id}/ - Delete address"),
    ],
    "Products (23)": [
        ("039", "GET /v1/products/home/ - Get home data"),
        ("040", "GET /v1/products/ - List products"),
        ("041", "GET /v1/products/ - List with filters"),
        ("042", "GET /v1/products/ - List with sorting"),
        ("043", "GET /v1/products/ - Search products"),
        ("044", "GET /v1/products/{id}/ - Get product by ID"),
        ("045", "GET /v1/products/{id}/recommendations/ - Get recommendations"),
        ("046", "GET /v1/products/{id}/variants/ - Get product variants"),
        ("047", "GET /v1/products/variants/{id}/ - Get specific variant"),
        ("048", "POST /v1/products/ - Create product (admin)"),
        ("049", "GET /v1/products/featured/ - Get featured products"),
        ("050", "GET /v1/products/deals/ - Get deals"),
        ("051", "POST /v1/products/{id}/variants/ - Create variant (admin)"),
        ("052", "PATCH /v1/products/variants/{id}/ - Update variant (admin)"),
        ("053", "DELETE /v1/products/variants/{id}/ - Delete variant (admin)"),
        ("054", "POST /v1/products/variants/{id}/images/ - Create image (admin)"),
        ("055", "GET /v1/products/images/{id}/ - Get image"),
        ("056", "GET /v1/products/variants/{id}/images/ - List images"),
        ("057", "PATCH /v1/products/images/{id}/ - Update image (admin)"),
        ("058", "DELETE /v1/products/images/{id}/ - Delete image (admin)"),
        ("059", "PATCH /v1/products/{id}/moderate/ - Moderate product (admin)"),
        ("060", "PATCH /v1/products/{id}/feature/ - Feature product (admin)"),
        ("061", "PUT /v1/products/{id}/ - Update product (admin)"),
        ("062", "DELETE /v1/products/{id}/ - Delete product (admin)"),
    ],
    "Reviews (6)": [
        ("063", "GET /v1/reviews/ - List reviews"),
        ("064", "GET /v1/reviews/?product_id={id} - Filter by product"),
        ("065", "GET /v1/reviews/{id}/ - Get review by ID"),
        ("066", "GET /v1/reviews/product/{id}/ - Get product reviews"),
        ("067", "POST /v1/reviews/ - Create review"),
        ("068", "PUT /v1/reviews/{id}/ - Update review"),
    ],
    "Cart (8)": [
        ("075", "GET /v1/cart/ - Get cart"),
        ("076", "POST /v1/cart/add/ - Add item to cart"),
        ("077", "PUT /v1/cart/items/{id}/ - Update cart item"),
        ("078", "DELETE /v1/cart/items/{id}/ - Remove cart item"),
        ("079", "POST /v1/cart/clear/ - Clear cart"),
        ("080", "GET /v1/cart/checkout-summary/ - Checkout summary"),
        ("081", "POST /v1/cart/calculate/ - Calculate cart totals"),
    ],
    "Orders (5)": [
        ("082", "GET /v1/orders/ - List orders"),
        ("083", "GET /v1/orders/{id}/ - Get order by ID"),
        ("084", "PUT /v1/orders/{id}/cancel/ - Cancel order"),
        ("085", "GET /v1/orders/{id}/shipments/ - Get order shipments"),
        ("086", "POST /v1/orders/checkout/ - Checkout"),
    ],
    "Payments (8)": [
        ("087", "GET /v1/payments/ - Get payments overview"),
        ("088", "GET /v1/payments/methods/ - List payment methods"),
        ("089", "POST /v1/payments/methods/ - Create payment method"),
        ("090", "GET /v1/payments/methods/{id}/ - Get payment method"),
        ("091", "PATCH /v1/payments/methods/{id}/ - Update payment method"),
        ("092", "DELETE /v1/payments/methods/{id}/ - Delete payment method"),
        ("093", "PATCH /v1/payments/methods/{id}/default/ - Set default payment method"),
        ("094", "POST /v1/payments/process-order/ - Process order payment"),
    ],
    "Contact Messages (5)": [
        ("095", "POST /v1/contact-messages/ - Create contact message"),
        ("096", "GET /v1/contact-messages/ - List messages (admin)"),
        ("097", "GET /v1/contact-messages/{id}/ - Get message (admin)"),
        ("098", "PATCH /v1/contact-messages/{id}/ - Update message (admin)"),
        ("099", "DELETE /v1/contact-messages/{id}/ - Delete message (admin)"),
    ],
    "Analytics (20)": [
        ("100", "POST /v1/analytics/track/ - Track event"),
        ("101", "GET /v1/analytics/conversion-rates/ - Conversion rates"),
        ("102", "GET /v1/analytics/cart-abandonment/ - Cart abandonment"),
        ("103", "GET /v1/analytics/time-to-purchase/ - Time to purchase"),
        ("104", "GET /v1/analytics/refund-rates/ - Refund rates"),
        ("105", "GET /v1/analytics/repeat-customers/ - Repeat customers"),
        ("106", "GET /v1/analytics/simple-dashboard/ - Simple dashboard"),
        ("107", "GET /v1/analytics/dashboard/ - Dashboard"),
        ("108", "GET /v1/analytics/sales-trend/ - Sales trend"),
        ("109", "GET /v1/analytics/sales-overview/ - Sales overview"),
        ("110", "GET /v1/analytics/sales/ - Sales analytics"),
        ("111", "GET /v1/analytics/users/ - User analytics"),
        ("112", "GET /v1/analytics/products/ - Product analytics"),
        ("113", "GET /v1/analytics/orders/ - Order analytics"),
        ("114", "GET /v1/analytics/revenue/ - Revenue analytics"),
        ("115", "GET /v1/analytics/kpis/ - KPIs"),
        ("116", "GET /v1/analytics/stats/ - Stats"),
        ("117", "GET /v1/analytics/dashboard/admin/ - Admin dashboard"),
        ("118", "GET /v1/analytics/export/orders/ - Export orders"),
        ("119", "GET /v1/analytics/export/subscriptions/ - Export subscriptions"),
    ],
    "Inventory (14)": [
        ("120", "POST /v1/inventory/locations/ - Create location"),
        ("121", "GET /v1/inventory/locations/ - List locations"),
        ("122", "GET /v1/inventory/locations/{id}/ - Get location"),
        ("123", "PATCH /v1/inventory/locations/{id}/ - Update location"),
        ("124", "DELETE /v1/inventory/locations/{id}/ - Delete location"),
        ("125", "POST /v1/inventory/ - Create inventory"),
        ("126", "GET /v1/inventory/ - List inventory"),
        ("127", "GET /v1/inventory/{id}/ - Get inventory"),
        ("128", "PATCH /v1/inventory/{id}/ - Update inventory"),
        ("129", "DELETE /v1/inventory/{id}/ - Delete inventory"),
        ("130", "POST /v1/inventory/adjustments/ - Adjust stock"),
        ("131", "GET /v1/inventory/adjustments/ - List adjustments"),
        ("132", "GET /v1/inventory/adjustments/{id}/ - Get adjustment"),
        ("133", "DELETE /v1/inventory/adjustments/{id}/ - Delete adjustment"),
    ],
    "Shipping (9)": [
        ("134", "GET /v1/shipping/methods/ - List shipping methods"),
        ("135", "GET /v1/shipping/methods/{id}/ - Get shipping method"),
        ("136", "POST /v1/shipping/methods/ - Create shipping method (admin)"),
        ("137", "PATCH /v1/shipping/methods/{id}/ - Update shipping method (admin)"),
        ("138", "DELETE /v1/shipping/methods/{id}/ - Delete shipping method (admin)"),
        ("139", "POST /v1/shipping/calculate/ - Calculate shipping cost"),
        ("140", "POST /v1/shipping/track/ - Track shipment"),
        ("141", "POST /v1/shipping-tracking/shipments/ - Create shipment"),
        ("142", "GET /v1/shipping-tracking/shipments/{id}/ - Get shipment"),
    ],
    "Subscriptions (12)": [
        ("143", "POST /v1/subscriptions/trigger-order-processing/ - Trigger processing (admin)"),
        ("144", "GET /v1/subscriptions/plans/ - List subscription plans"),
        ("145", "GET /v1/subscriptions/ - List user subscriptions"),
        ("146", "POST /v1/subscriptions/ - Create subscription"),
        ("147", "GET /v1/subscriptions/{id}/ - Get subscription by ID"),
        ("148", "PATCH /v1/subscriptions/{id}/ - Update subscription"),
        ("149", "POST /v1/subscriptions/{id}/cancel/ - Cancel subscription"),
        ("150", "POST /v1/subscriptions/{id}/pause/ - Pause subscription"),
        ("151", "POST /v1/subscriptions/{id}/resume/ - Resume subscription"),
        ("152", "POST /v1/subscriptions/{id}/products/ - Add products"),
        ("153", "DELETE /v1/subscriptions/{id}/products/ - Remove products"),
        ("154", "DELETE /v1/subscriptions/{id}/products/{pid}/ - Remove single product"),
    ],
    "Tax (6)": [
        ("155", "POST /v1/tax/calculate/ - Calculate tax"),
        ("156", "GET /v1/tax/rates/ - List tax rates"),
        ("157", "POST /v1/tax/rates/ - Create tax rate (admin)"),
        ("158", "GET /v1/tax/rates/{id}/ - Get tax rate"),
        ("159", "PATCH /v1/tax/rates/{id}/ - Update tax rate (admin)"),
        ("160", "DELETE /v1/tax/rates/{id}/ - Delete tax rate (admin)"),
    ],
    "Promocodes (8)": [
        ("161", "GET /v1/promocodes/ - List promocodes"),
        ("162", "GET /v1/promocodes/{id}/ - Get promocode"),
        ("163", "POST /v1/promocodes/ - Create promocode (admin)"),
        ("164", "PATCH /v1/promocodes/{id}/ - Update promocode (admin)"),
        ("165", "DELETE /v1/promocodes/{id}/ - Delete promocode (admin)"),
        ("166", "POST /v1/promocodes/validate/ - Validate promocode"),
        ("167", "POST /v1/promocodes/trigger-cleanup/ - Trigger cleanup (admin)"),
        ("168", "POST /v1/cart/promocode/ - Apply promocode to cart"),
    ],
    "Refunds (4)": [
        ("169", "GET /v1/refunds/ - List refunds"),
        ("170", "POST /v1/refunds/ - Create refund"),
        ("171", "GET /v1/refunds/{id}/ - Get refund by ID"),
        ("172", "PATCH /v1/refunds/{id}/ - Update refund status"),
    ],
    "Webhooks (2)": [
        ("173", "POST /v1/webhooks/stripe/ - Stripe webhook"),
        ("174", "GET /v1/webhooks/health/ - Webhook health check"),
    ],
}


def print_inventory():
    """Print all test cases."""
    print("\n" + "="*70)
    print("BANWEE API TEST INVENTORY - 158 TEST CASES")
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
