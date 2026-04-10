#!/usr/bin/env python3
"""Quick API endpoint test script - runs tests without database requirements."""

import asyncio
import sys
from httpx import AsyncClient
from main import app


BASE_URL = "http://localhost:8000"


async def test_root_endpoint():
    """Test root endpoint."""
    async with AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "Banwee API"
        print("✅ Root endpoint working")


async def test_health_endpoint():
    """Test health check endpoint."""
    async with AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/v1/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        print("✅ Health endpoint working")


async def test_docs_endpoint():
    """Test API docs endpoint."""
    async with AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/docs")
        assert response.status_code == 200
        print("✅ API docs endpoint working")


async def test_products_home():
    """Test products home endpoint."""
    async with AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/v1/products/home")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "categories" in data["data"]
        print("✅ Products home endpoint working")


async def test_products_list():
    """Test products list endpoint."""
    async with AsyncClient(base_url=BASE_URL) as client:
        response = await client.get("/v1/products/?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        print("✅ Products list endpoint working")


async def run_all_tests():
    """Run all basic endpoint tests."""
    print("=" * 60)
    print("Banwee API Endpoint Tests")
    print("=" * 60)
    
    tests = [
        ("Root", test_root_endpoint),
        ("Health", test_health_endpoint),
        ("Docs", test_docs_endpoint),
        ("Products Home", test_products_home),
        ("Products List", test_products_list),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"❌ {name} endpoint failed: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
