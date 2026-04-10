#!/usr/bin/env python3
"""Test runner script for Banwee API tests."""

import subprocess
import sys
import argparse


def run_tests(test_path="tests/", verbose=True, markers=None, fail_fast=False):
    """Run pytest with the specified options."""
    cmd = ["python", "-m", "pytest", test_path]
    
    if verbose:
        cmd.append("-v")
    
    if fail_fast:
        cmd.append("-x")
    
    if markers:
        cmd.extend(["-m", markers])
    
    # Add coverage if available
    try:
        import pytest_cov
        cmd.extend(["--cov=.", "--cov-report=term-missing", "--cov-report=html"])
    except ImportError:
        pass
    
    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)
    
    result = subprocess.run(cmd)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="Run Banwee API tests")
    parser.add_argument(
        "--path", "-p",
        default="tests/",
        help="Path to test files (default: tests/)"
    )
    parser.add_argument(
        "--markers", "-m",
        default=None,
        help="Run tests with specific markers (e.g., 'unit', 'api', 'auth')"
    )
    parser.add_argument(
        "--fail-fast", "-x",
        action="store_true",
        help="Stop on first failure"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Less verbose output"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Banwee API Test Runner")
    print("=" * 60)
    
    exit_code = run_tests(
        test_path=args.path,
        verbose=not args.quiet,
        markers=args.markers,
        fail_fast=args.fail_fast
    )
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
