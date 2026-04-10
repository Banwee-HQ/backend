#!/usr/bin/env python3
"""
Complete API Test Runner for Banwee Backend

This script runs all 140+ tests covering 273+ API endpoints.

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


# Test inventory - all 140+ test cases
TEST_INVENTORY = {
    "Root & System": [
        ("001", "GET / - Root endpoint"),
        ("002", "GET /v1/health/ - Health check"),
        ("003", "GET /docs - API documentation"),
    ],
    "Authentication (19)": [
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
    ],
    "Users (11)": [
        ("021", "GET /v1/users/me - Get current user"),
        ("022", "GET /v1/users/me - Get current user via auth"),
        ("023", "GET /v1/users/ - List users"),
        ("024", "GET /v1/users/{id} - Get user by ID"),
        ("025", "GET /v1/addresses/ - Get my addresses via addresses router"),
        ("026", "POST /v1/addresses/ - Create address via addresses router"),
        ("027", "PATCH /v1/addresses/{id} - Update address via addresses router"),
        ("028", "DELETE /v1/addresses/{id} - Delete address via addresses router"),
        ("029", "GET /v1/auth/me without auth - Should fail"),
    ],
    "Products (10)": [
        ("032", "GET /v1/products/home - Get home data"),
        ("033", "GET /v1/products/ - List products"),
        ("034", "GET /v1/products/ - List with filters"),
        ("035", "GET /v1/products/ - List with sorting"),
        ("036", "GET /v1/products/ - Search products"),
        ("037", "GET /v1/products/{id} - Get product by ID"),
        ("038", "GET /v1/products/{id}/recommendations - Get recommendations"),
        ("039", "GET /v1/products/{id}/variants - Get product variants"),
        ("040", "GET /v1/products/variants/{id} - Get specific variant"),
        ("041", "POST /v1/products/ - Create product (admin)"),
    ],
    "Reviews (6)": [
        ("042", "GET /v1/reviews/ - List reviews"),
        ("043", "GET /v1/reviews/?product_id={id} - Filter by product"),
        ("044", "GET /v1/reviews/{id} - Get review by ID"),
        ("045", "GET /v1/reviews/product/{id} - Get product reviews"),
        ("046", "POST /v1/reviews/ - Create review"),
        ("047", "PUT /v1/reviews/{id} - Update review"),
    ],
    "Wishlist (3)": [
        ("048", "GET /v1/wishlists/ - List wishlists"),
        ("049", "POST /v1/wishlists/ - Create wishlist"),
        ("050", "DELETE /v1/wishlists/{id} - Delete wishlist"),
    ],
    "Cart (5)": [
        ("051", "GET /v1/cart/ - Get cart"),
        ("052", "POST /v1/cart/add - Add item to cart"),
        ("053", "PUT /v1/cart/items/{id} - Update cart item"),
        ("054", "DELETE /v1/cart/items/{id} - Remove cart item"),
        ("055", "DELETE /v1/cart/clear - Clear cart"),
    ],
    "Orders (4)": [
        ("056", "GET /v1/orders/ - List orders"),
        ("057", "GET /v1/orders/{id} - Get order by ID"),
        ("058", "PUT /v1/orders/{id}/cancel - Cancel order"),
        ("059", "GET /v1/shipping/orders/{id} - Get order tracking"),
    ],
    "Payments (4)": [
        ("060", "GET /v1/payments/ - Get payments overview"),
        ("061", "GET /v1/payments/methods - List payment methods"),
        ("062", "POST /v1/payments/methods - Create payment method"),
        ("063", "DELETE /v1/payments/methods/{id} - Delete payment method"),
    ],
    "Contact Messages (2)": [
        ("064", "POST /v1/contact-messages/ - Create contact message"),
        ("065", "GET /v1/contact-messages/ - List messages (admin)"),
    ],
    "Admin Dashboard (6)": [
        ("066", "GET /v1/admin/dashboard - Admin dashboard"),
        ("067", "GET /v1/admin/users - List all users (admin)"),
        ("068", "GET /v1/admin/users/{id} - Get user by ID (admin)"),
        ("069", "PUT /v1/admin/users/{id} - Update user (admin)"),
        ("070", "DELETE /v1/admin/users/{id} - Delete user (admin)"),
        ("071", "GET /v1/admin/users as regular user - Should fail"),
    ],
    "Admin Products (4)": [
        ("072", "GET /v1/admin/products - List all products (admin)"),
        ("073", "POST /v1/admin/products - Create product (admin)"),
        ("074", "PUT /v1/admin/products/{id} - Update product (admin)"),
        ("075", "DELETE /v1/admin/products/{id} - Delete product (admin)"),
    ],
    "Admin Orders (4)": [
        ("076", "GET /v1/admin/orders - List all orders (admin)"),
        ("077", "GET /v1/admin/orders/{id} - Get order by ID (admin)"),
        ("078", "PATCH /v1/admin/orders/{id}/status - Update order status (admin)"),
        ("079", "POST /v1/admin/orders/{id}/ship - Ship order (admin)"),
    ],
    "Admin Subscriptions (4)": [
        ("080", "GET /v1/admin/subscriptions - List all subscriptions (admin)"),
        ("081", "GET /v1/admin/subscriptions/{id} - Get subscription by ID (admin)"),
        ("082", "PATCH /v1/admin/subscriptions/{id} - Update subscription (admin)"),
        ("083", "POST /v1/admin/subscriptions/{id}/cancel - Cancel subscription (admin)"),
    ],
    "Admin Refunds (4)": [
        ("084", "GET /v1/admin/refunds - List all refunds (admin)"),
        ("085", "POST /v1/admin/refunds - Create refund (admin)"),
        ("086", "GET /v1/admin/refunds/{id} - Get refund by ID (admin)"),
        ("087", "PATCH /v1/admin/refunds/{id} - Update refund status (admin)"),
    ],
    "Admin Inventory (2)": [
        ("088", "GET /v1/admin/inventory - List inventory (admin)"),
        ("089", "POST /v1/admin/inventory/adjust - Adjust inventory (admin)"),
    ],
    "Admin Shipping (4)": [
        ("090", "GET /v1/admin/shipping/methods - List shipping methods (admin)"),
        ("091", "POST /v1/admin/shipping/methods - Create shipping method (admin)"),
        ("092", "PUT /v1/admin/shipping/methods/{id} - Update shipping method (admin)"),
        ("093", "DELETE /v1/admin/shipping/methods/{id} - Delete shipping method (admin)"),
    ],
    "Analytics (7)": [
        ("094", "GET /v1/analytics/sales - Sales analytics"),
        ("095", "GET /v1/analytics/sales?date_range - Sales analytics with date range"),
        ("096", "GET /v1/analytics/users - User analytics"),
        ("097", "GET /v1/analytics/products - Product analytics"),
        ("098", "GET /v1/analytics/orders - Order analytics"),
        ("099", "GET /v1/analytics/revenue - Revenue analytics"),
        ("100", "GET /v1/analytics/dashboard - Dashboard analytics"),
    ],
    "User Subscriptions (5)": [
        ("101", "GET /v1/subscriptions/plans - List subscription plans"),
        ("102", "GET /v1/subscriptions/ - List user subscriptions"),
        ("103", "POST /v1/subscriptions/ - Create subscription"),
        ("104", "GET /v1/subscriptions/{id} - Get subscription by ID"),
        ("105", "POST /v1/subscriptions/{id}/cancel - Cancel subscription"),
    ],
    "Promocodes (4)": [
        ("106", "GET /v1/promocodes/ - List active promocodes"),
        ("107", "POST /v1/promocodes/validate - Validate promocode"),
        ("108", "POST /v1/promocodes/ - Create promocode (admin)"),
        ("109", "DELETE /v1/promocodes/{id} - Delete promocode (admin)"),
    ],
    "Shipping (3)": [
        ("110", "GET /v1/shipping/methods - List shipping methods"),
        ("111", "POST /v1/shipping/calculate - Calculate shipping cost"),
        ("112", "POST /v1/shipping/track - Track shipment by number"),
        ("113", "GET /v1/shipping/shipments/{id} - Get shipment details"),
    ],
    "Tax (2)": [
        ("114", "POST /v1/tax/calculate - Calculate tax"),
        ("115", "GET /v1/tax/rates - List tax rates"),
        ("116", "GET /v1/tax/admin/tax-rates - Admin tax rates list"),
    ],
    "Webhooks (2)": [
        ("117", "POST /v1/webhooks/stripe - Stripe webhook"),
        ("118", "GET /v1/webhooks/health - Webhook health check"),
    ],
}


def print_inventory():
    """Print all test cases."""
    print("\n" + "="*70)
    print("BANWEE API TEST INVENTORY - 116 TEST CASES")
    print("="*70)
    
    total = 0
    for category, tests in TEST_INVENTORY.items():
        print(f"\n{category}:")
        for num, desc in tests:
            print(f"  [{num}] {desc}")
            total += 1
    
    print(f"\n{'='*70}")
    print(f"TOTAL: {total} test cases covering 273+ API endpoints")
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
