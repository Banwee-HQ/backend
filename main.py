import asyncio
import os
import subprocess
from core.logging import get_structured_logger
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError

from core.db import AsyncSessionDB, initialize_db, db_manager
from core.cache import redis_manager
from core.config import settings, validate_startup_environment, get_setup_instructions
from core.errors import (
    APIException,
    api_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    sqlalchemy_exception_handler,
    general_exception_handler
)

from api import (
    admin_router,
    analytics_router,
    auth_router,
    cart_router,
    categories_router,
    health_router,
    inventory_router,
    oauth_router,
    orders_router,
    payments_router,
    products_router,
    promocodes_router,
    refunds_router,
    review_router,
    search_router,
    shipping_router,
    subscriptions_router,
    tax_router,
    user_router,
    webhooks_router,
    wishlist_router,
)
from api.contact_messages import router as contact_messages_router

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    # Validate environment variables first
    from core.config import validate_startup_environment, get_setup_instructions
    from core.logging import get_structured_logger
    
    logger = get_structured_logger(__name__)
    logger.info("Validating environment configuration...")
    
    validation_result = validate_startup_environment()
    if not validation_result.is_valid:
        logger.error("Environment validation failed!")
        if validation_result.error_message:
            logger.error(validation_result.error_message)
        
        # Print setup instructions
        instructions = get_setup_instructions()
        logger.error("Setup Instructions:")
        logger.error(instructions)
        
        # For development, just warn instead of failing
        if os.getenv("ENVIRONMENT", "local").lower() in ["local", "development", "dev"]:
            logger.warning("Continuing with invalid environment configuration in development mode")
        else:
            raise RuntimeError("Invalid environment configuration. Please check your .env file.")
    
    logger.info("Environment validation passed ✅")
    if validation_result.warnings:
        for warning in validation_result.warnings:
            logger.warning(warning)

    # Initialize database
    try:
        from core.config import settings
        from core.db import initialize_db
        
        # Initialize database with simple engine (no optimization)
        initialize_db(
            settings.SQLALCHEMY_DATABASE_URI,
            settings.ENVIRONMENT == "local",
            use_optimized_engine=False
        )
        
        logger.info("Database initialized successfully ✅")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise RuntimeError(f"Database initialization failed: {e}")

    # Initialize Redis if enabled
    if settings.ENABLE_REDIS:
        try:
            redis_client = await redis_manager.get_client()
            await redis_client.ping()
            logger.info("Redis connection established ✅")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            if settings.ENVIRONMENT != "local":
                raise RuntimeError("Redis connection required for production")

    
    yield
    
    # Shutdown event
    logger.info("Application shutting down...")
    
    # Close Redis connections
    if settings.ENABLE_REDIS:
        try:
            await redis_manager.close()
            logger.info("Redis connections closed")
        except Exception as e:
            logger.error(f"Error closing Redis connections: {e}")


app = FastAPI(
    title="Banwee API",
    description="Discover premium organic products from Africa. Ethically sourced, sustainably produced, and delivered to your doorstep.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add standard FastAPI middleware
# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS if hasattr(
        settings, 'BACKEND_CORS_ORIGINS') else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
 
# Trusted host middleware for security
if hasattr(settings, 'ALLOWED_HOSTS'):
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS
    )

# Middleware Stack (order matters - last added is executed first)
# Note: Rate limiting disabled for MVP (was using Redis)
# app.add_middleware(RateLimitMiddleware)

# API v1 Router
v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth_router)
v1_router.include_router(user_router)
v1_router.include_router(products_router)
v1_router.include_router(cart_router)
v1_router.include_router(orders_router)
v1_router.include_router(admin_router)
v1_router.include_router(oauth_router)
v1_router.include_router(subscriptions_router)
v1_router.include_router(review_router)
v1_router.include_router(payments_router)
v1_router.include_router(promocodes_router)
v1_router.include_router(wishlist_router)
v1_router.include_router(health_router)
v1_router.include_router(search_router)
v1_router.include_router(inventory_router)
v1_router.include_router(analytics_router)
v1_router.include_router(refunds_router)
v1_router.include_router(shipping_router)
v1_router.include_router(tax_router)
v1_router.include_router(webhooks_router)
v1_router.include_router(categories_router)
v1_router.include_router(contact_messages_router)

# Include the v1 router into the main app
app.include_router(v1_router)

@app.get("/")
async def read_root():
    return {
        "service": "Banwee API",
        "status": "Running",
        "version": "1.0.0",
        "description": "Discover premium organic products from Africa. Ethically sourced, sustainably produced, and delivered to your doorstep.",
    }

# Register exception handlers
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
        reload=True if os.getenv("ENVIRONMENT", "local") == "local" else False,
        log_level="info"
    )