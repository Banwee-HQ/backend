"""Test configuration and fixtures for Banwee API tests."""

import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from uuid import uuid4
from datetime import datetime, timedelta

# Set test environment before importing app modules
import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend package root is on sys.path so tests can import main
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env.dev first so we get the real DATABASE_URL
env_path = Path(__file__).resolve().parents[1] / ".env.dev"
if env_path.exists():
    load_dotenv(env_path)

os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
# Don't overwrite DATABASE_URL - use the one from .env.dev (Supabase)
os.environ["FRONTEND_URL"] = "http://localhost:5173"

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from main import app
from core.db import get_db
from core.config import settings
from models.accounts.user import User, UserRole
from services.accounts.auth import AuthService
from schemas.accounts.user import Create as UserCreate

# Use the actual database URL from environment (Supabase)
TEST_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.vxemrvsdmrzsbhsozyco:7dQPJXWHWGnQBQvt@aws-1-us-east-1.pooler.supabase.com:5432/postgres")
print(f"Using database: {TEST_DATABASE_URL[:50]}...")  # Debug output
if TEST_DATABASE_URL.startswith("postgresql://"):
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=False,
)

# Test session factory
TestingSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


@pytest_asyncio.fixture(scope="function")
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing (ASGI mode)."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def live_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for live server testing.
    
    This fixture connects to the actual running backend server.
    Use this when you want to test against a live server instead of the ASGI app.
    """
    base_url = os.getenv("LIVE_SERVER_URL", "http://localhost:8000")
    async with AsyncClient(base_url=base_url, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    """Create a test client for synchronous testing."""
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    from services.accounts.user import UserService
    from core.utils.encryption import PasswordManager
    from core.utils.uuid_utils import uuid7
    
    password_manager = PasswordManager()
    
    # Create user directly to avoid email sending in tests
    user = User(
        id=uuid7(),
        email=f"test_{uuid4().hex[:8]}@example.com",
        hashed_password=password_manager.hash_password("TestPassword123!"),
        firstname="Test",
        lastname="User",
        phone="+1234567890",
        role=UserRole.CUSTOMER,
        account_status="active",
        verification_status="verified"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession) -> User:
    """Create a test admin user."""
    from core.utils.encryption import PasswordManager
    from core.utils.uuid_utils import uuid7
    
    password_manager = PasswordManager()
    
    user = User(
        id=uuid7(),
        email=f"admin_{uuid4().hex[:8]}@example.com",
        hashed_password=password_manager.hash_password("AdminPassword123!"),
        firstname="Admin",
        lastname="User",
        phone="+1234567890",
        role=UserRole.ADMIN,
        account_status="active",
        verification_status="verified"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def auth_headers(async_client: AsyncClient, test_user: User) -> dict:
    """Get authentication headers for test user."""
    response = await async_client.post(
        "/v1/auth/login/",
        json={
            "email": test_user.email,
            "password": "TestPassword123!"
        }
    )
    assert response.status_code == 200
    data = response.json()
    token = data["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def admin_headers(async_client: AsyncClient, admin_user: User) -> dict:
    """Get authentication headers for admin user."""
    response = await async_client.post(
        "/v1/auth/login/",
        json={
            "email": admin_user.email,
            "password": "AdminPassword123!"
        }
    )
    assert response.status_code == 200
    data = response.json()
    token = data["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_product_data():
    """Sample product data for testing."""
    return {
        "name": "Test Product",
        "slug": f"test-product-{uuid4().hex[:8]}",
        "sku": f"SKU-{uuid4().hex[:8].upper()}",
        "description": "A test product for testing purposes",
        "short_description": "Test product",
        "base_price": 29.99,
        "sale_price": 19.99,
        "cost_price": 15.00,
        "quantity": 100,
        "category": "grains-pulses",
        "origin_country": "Nigeria",
        "is_active": True,
        "is_featured": False,
        "weight_kg": 1.5,
        "tags": ["test", "organic"]
    }


@pytest.fixture
def sample_cart_item():
    """Sample cart item data."""
    return {
        "product_id": str(uuid4()),
        "quantity": 2,
        "variant_id": None
    }


@pytest.fixture
def sample_address_data():
    """Sample address data."""
    return {
        "label": "Home",
        "recipient_name": "Test User",
        "phone": "+1234567890",
        "street_address": "123 Test Street",
        "apartment": "Apt 1",
        "city": "Lagos",
        "state": "Lagos State",
        "postal_code": "100001",
        "country": "NG",
        "is_default": True
    }


@pytest.fixture
def sample_contact_message():
    """Sample contact message data."""
    return {
        "name": "Test Contact",
        "email": "contact@test.com",
        "subject": "Test Subject",
        "message": "This is a test message for the contact form."
    }
