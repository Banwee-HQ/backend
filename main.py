import os
import logging
import warnings
from contextlib import asynccontextmanager
from core.logging import get_structured_logger
from fastapi import FastAPI, HTTPException, APIRouter

# Suppress urllib3 OpenSSL warning
warnings.filterwarnings('ignore', category=UserWarning, module='urllib3')
# Suppress WeasyPrint warnings
logging.getLogger('weasyprint').setLevel(logging.ERROR)
os.environ['WEASYPRINT_DO_NOT_INSTALL_EXTRA_LIBS'] = '1'
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError

from core.db import initialize_db
from core.config import settings
from core.exceptions import (
    APIException,
    api_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    sqlalchemy_exception_handler,
    general_exception_handler
)

from api import (
    auth_router, oauth_router, oauth_social_router, user_router, addresses_router,
    products_router, review_router, inventory_router, wishlist_router,
    cart_router, orders_router, payments_router, refunds_router, shipping_router,
    shipping_tracking_router, tax_router, promocodes_router, subscriptions_router, webhooks_router,
    analytics_router,
    health_router, contact_messages_router,
)

logger = get_structured_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    logger.info("Validating environment configuration...")
    validation_result = settings.validate()

    if not validation_result["is_valid"]:
        logger.error("Environment validation failed!")
        missing = validation_result.get("missing", [])
        if missing:
            logger.error("Missing required vars: %s", missing)
        if settings.ENVIRONMENT.lower() in ["local", "development", "dev"]:
            logger.warning("Continuing with invalid environment in development mode")
        else:
            raise RuntimeError("Invalid environment configuration. Check your .env file.")

    logger.info("Environment validation passed ✅")

    # Initialize database
    try:
        await initialize_db(
            settings.SQLALCHEMY_DATABASE_URI,
            settings.ENVIRONMENT == "local"
        )
        # Import all models to ensure SQLAlchemy mappers are configured
        import models
        logger.info("Database initialized ✅")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise RuntimeError(f"Database initialization failed: {e}")

    # Start background scheduler (subscriptions, promocodes)
    from core.worker import start_scheduler
    start_scheduler()

    yield

    # --- Shutdown ---
    logger.info("Application shutting down...")


app = FastAPI(
    title="Banwee API",
    description="Discover premium organic products from Africa. Ethically sourced, sustainably produced, and delivered to your doorstep.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS if hasattr(settings, 'BACKEND_CORS_ORIGINS') else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if hasattr(settings, 'ALLOWED_HOSTS'):
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

v1_router = APIRouter(prefix="/v1", redirect_slashes=False)
v1_router.include_router(auth_router)
v1_router.include_router(oauth_router)
v1_router.include_router(oauth_social_router)
v1_router.include_router(user_router)
v1_router.include_router(addresses_router)
v1_router.include_router(products_router)
v1_router.include_router(review_router)
v1_router.include_router(inventory_router)
v1_router.include_router(wishlist_router)
v1_router.include_router(cart_router)
v1_router.include_router(orders_router)
v1_router.include_router(payments_router)
v1_router.include_router(refunds_router)
v1_router.include_router(shipping_router)
v1_router.include_router(shipping_tracking_router)
v1_router.include_router(tax_router)
v1_router.include_router(promocodes_router)
v1_router.include_router(subscriptions_router)
v1_router.include_router(webhooks_router)
# Admin routes are distributed to domain-specific modules:
# - /users/* for user management (in accounts/user.py)
# - /products/admin/* for product management (in catalog/products.py)
# - /orders/admin/* for order management (in commerce/orders.py)
# - /refunds/admin/* for refund management (in commerce/refunds.py)
# - /subscriptions/admin/* for subscription management (in commerce/subscriptions.py)
# - /tax/admin/* for tax rate management (in commerce/tax.py)
# - /inventory/sync* for inventory sync (in catalog/inventory.py)
# - /analytics/admin/* for analytics/stats (in analytics/analytics.py)
v1_router.include_router(analytics_router)
v1_router.include_router(health_router)
v1_router.include_router(contact_messages_router)

app.include_router(v1_router)


@app.get("/")
async def read_root():
    return {
        "service": "Banwee API",
        "status": "Running",
        "version": "1.0.0",
        "description": "Discover premium organic products from Africa. Ethically sourced, sustainably produced, and delivered to your doorstep.",
    }


app.add_exception_handler(APIException, api_exception_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=True
    )
