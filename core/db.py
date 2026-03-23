from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text, Column, DateTime, func, TypeDecorator, CHAR, Index, String, Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError, OperationalError
from sqlalchemy.pool import QueuePool
import asyncio
import time
import uuid
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from core.logging import get_structured_logger
from datetime import datetime as dt

from core.logging import structured_logger
from core.utils.uuid_utils import uuid7
from core.errors.api_exceptions import DatabaseException, APIException

logger = get_structured_logger(__name__)

Base = declarative_base()
CHAR_LENGTH = 255


class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type, otherwise uses
    CHAR(36), storing as stringified UUID values with hyphens.
    """
    impl = CHAR

    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(UUID())
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        # Always use PostgreSQL - convert UUID to string
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            # Always return UUID object for consistency
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
            return value


class BaseModel(Base):
    """Optimized base model with UUID primary key, timestamps, and essential tracking - HARD DELETE ONLY"""
    __abstract__ = True

    # Core fields - always present
    id = Column(GUID(), primary_key=True, default=uuid7, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    # Audit fields - minimal overhead
    created_by = Column(GUID(), nullable=True, index=True)
    updated_by = Column(GUID(), nullable=True)
    
    # Version for optimistic locking
    version = Column(Integer, default=1, nullable=False)


class StatusMixin:
    """Mixin for models that need status tracking"""
    status = Column(String(50), nullable=False, default="active", index=True)


class MetadataMixin:
    """Mixin for models that need flexible metadata (use JSONB sparingly)"""
    metadata_json = Column(JSONB, nullable=True)


class SearchMixin:
    """Mixin for models that need full-text search"""
    search_vector = Column(Text, nullable=True)  # For full-text search


# Optimized base models for different use cases - ALL HARD DELETE
class HardDeleteModel(BaseModel):
    """Base model for all entities - hard delete only"""
    __abstract__ = True


class StatusModel(BaseModel, StatusMixin):
    """Base model for entities with status tracking - hard delete only"""
    __abstract__ = True


class FullTrackingModel(BaseModel, StatusMixin, MetadataMixin):
    """Base model with full tracking capabilities - hard delete only"""
    __abstract__ = True


# Database connection configuration - NOW INITIALIZED LATER
engine_db = None
AsyncSessionDB = None

class DatabaseOptimizer:
    """Simple database manager for Alembic-managed schema"""
    
    @staticmethod
    def get_engine(database_uri: str = None, env_is_local: bool = None):
        """Create simple async engine"""
        # Import settings here to avoid circular dependency
        if database_uri is None or env_is_local is None:
            from core.config import settings
            database_uri = database_uri or settings.SQLALCHEMY_DATABASE_URI
            env_is_local = env_is_local if env_is_local is not None else (settings.ENVIRONMENT == "local")

        return create_async_engine(
            database_uri,
            echo=env_is_local,  # Only show SQL in local development
            future=True,
            connect_args={
                "ssl": "require" if not env_is_local else None
            }
        )
    
    @staticmethod
    async def create_performance_indexes(db: AsyncSession):
        """Create performance indexes for frequently queried columns"""
        indexes = [
            # User indexes
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
            "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);",
            
            # Product indexes
            "CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id);",
            "CREATE INDEX IF NOT EXISTS idx_products_is_active ON products(is_active);",
            "CREATE INDEX IF NOT EXISTS idx_products_created_at ON products(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_products_name_gin ON products USING gin(to_tsvector('english', name));",
            
            # Product variants indexes
            "CREATE INDEX IF NOT EXISTS idx_product_variants_product_id ON product_variants(product_id);",
            "CREATE INDEX IF NOT EXISTS idx_product_variants_sku ON product_variants(sku);",
            "CREATE INDEX IF NOT EXISTS idx_product_variants_stock ON product_variants(stock);",
            "CREATE INDEX IF NOT EXISTS idx_product_variants_is_active ON product_variants(is_active);",
            
            # Order indexes
            "CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);",
            "CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);",
            "CREATE INDEX IF NOT EXISTS idx_orders_user_status ON orders(user_id, status);",
            
            # Order items indexes
            "CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);",
            "CREATE INDEX IF NOT EXISTS idx_order_items_variant_id ON order_items(variant_id);",
            
            # Payment indexes
            "CREATE INDEX IF NOT EXISTS idx_payment_methods_user_id ON payment_methods(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_payment_methods_is_active ON payment_methods(is_active);",
            "CREATE INDEX IF NOT EXISTS idx_payment_intents_user_id ON payment_intents(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_payment_intents_status ON payment_intents(status);",
            "CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);",
            
            # Review indexes
            "CREATE INDEX IF NOT EXISTS idx_reviews_product_id ON reviews(product_id);",
            "CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON reviews(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating);",
            "CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at);",
            
            # Notification indexes - commented out (table doesn't exist)
            # "CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);",
            # "CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);",
            # "CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);",
            # "CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, is_read) WHERE is_read = false;",
            
            # Wishlist indexes - commented out (table doesn't exist)
            # "CREATE INDEX IF NOT EXISTS idx_wishlist_items_user_id ON wishlist_items(user_id);",
            # "CREATE INDEX IF NOT EXISTS idx_wishlist_items_product_id ON wishlist_items(product_id);",
            # "CREATE INDEX IF NOT EXISTS idx_wishlist_items_user_product ON wishlist_items(user_id, product_id);",
            
            # Category indexes - commented out (table doesn't exist)
            # "CREATE INDEX IF NOT EXISTS idx_categories_parent_id ON categories(parent_id);",
            # "CREATE INDEX IF NOT EXISTS idx_categories_is_active ON categories(is_active);",
            
            # Subscription indexes
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);",
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);",
            "CREATE INDEX IF NOT EXISTS idx_subscriptions_next_billing ON subscriptions(next_billing_date);",
        ]
        
        for index_sql in indexes:
            try:
                await db.execute(text(index_sql))
                logger.info(f"Created index: {index_sql.split('idx_')[1].split(' ')[0] if 'idx_' in index_sql else 'unknown'}")
            except Exception as e:
                # Index might already exist or other error
                logger.warning(f"Index creation warning: {e}")
        
        await db.commit()
        logger.info("Performance indexes creation completed")
    
    @staticmethod
    async def optimize_postgresql_settings(db: AsyncSession):
        """Apply PostgreSQL optimization settings"""
        optimizations = [
            # Memory settings
            "SET shared_buffers = '256MB';",
            "SET effective_cache_size = '1GB';",
            "SET work_mem = '4MB';",
            "SET maintenance_work_mem = '64MB';",
            
            # Checkpoint settings
            "SET checkpoint_completion_target = 0.9;",
            "SET wal_buffers = '16MB';",
            
            # Query planner settings
            "SET random_page_cost = 1.1;",  # For SSD storage
            "SET effective_io_concurrency = 200;",  # For SSD storage
            
            # Logging settings for production
            "SET log_min_duration_statement = 1000;",  # Log slow queries (>1s)
            "SET log_checkpoints = on;",
            "SET log_connections = on;",
            "SET log_disconnections = on;",
            
            # Connection settings
            "SET max_connections = 100;",
            
            # Autovacuum settings
            "SET autovacuum = on;",
            "SET autovacuum_max_workers = 3;",
            "SET autovacuum_naptime = '1min';",
        ]
        
        for setting in optimizations:
            try:
                await db.execute(text(setting))
                logger.info(f"Applied setting: {setting.split('SET ')[1].split(' =')[0]}")
            except Exception as e:
                # Some settings might require superuser privileges
                logger.warning(f"Setting application warning: {e}")
        
        logger.info("PostgreSQL optimization settings applied")
    
    @staticmethod
    async def analyze_tables(db: AsyncSession):
        """Update table statistics for better query planning"""
        tables = [
            'users', 'products', 'product_variants', 'orders', 'order_items',
            'payment_methods', 'payment_intents', 'transactions', 'reviews',
            'subscriptions'  # Only include tables that exist
        ]
        
        for table in tables:
            try:
                await db.execute(text(f"ANALYZE {table};"))
                logger.info(f"Analyzed table: {table}")
            except Exception as e:
                logger.warning(f"Table analysis warning for {table}: {e}")
        
        logger.info("Table analysis completed")
    
    @staticmethod
    async def vacuum_tables(db: AsyncSession):
        """Vacuum tables to reclaim space and update statistics"""
        tables = [
            'users', 'products', 'product_variants', 'orders', 'order_items',
            'payment_methods', 'payment_intents', 'transactions', 'reviews',
            'subscriptions'  # Only include tables that exist
        ]
        
        for table in tables:
            try:
                # Use VACUUM ANALYZE for better performance
                await db.execute(text(f"VACUUM ANALYZE {table};"))
                logger.info(f"Vacuumed table: {table}")
            except Exception as e:
                logger.warning(f"Vacuum warning for {table}: {e}")
        
        logger.info("Table vacuum completed")
    
    @staticmethod
    async def get_database_stats(db: AsyncSession) -> dict:
        """Get database performance statistics"""
        try:
            # Get database size
            size_result = await db.execute(text(
                "SELECT pg_size_pretty(pg_database_size(current_database())) as db_size;"
            ))
            db_size = size_result.scalar()
            
            # Get connection count
            conn_result = await db.execute(text(
                "SELECT count(*) as active_connections FROM pg_stat_activity WHERE state = 'active';"
            ))
            active_connections = conn_result.scalar()
            
            # Get slow queries count
            slow_queries_result = await db.execute(text(
                "SELECT count(*) as slow_queries FROM pg_stat_statements WHERE mean_time > 1000;"
            ))
            slow_queries = slow_queries_result.scalar() or 0
            
            # Get cache hit ratio
            cache_result = await db.execute(text("""
                SELECT 
                    round(
                        (sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read))) * 100, 2
                    ) as cache_hit_ratio
                FROM pg_statio_user_tables;
            """))
            cache_hit_ratio = cache_result.scalar() or 0
            
            return {
                "database_size": db_size,
                "active_connections": active_connections,
                "slow_queries_count": slow_queries,
                "cache_hit_ratio": f"{cache_hit_ratio}%",
                "status": "healthy" if cache_hit_ratio > 90 else "needs_attention"
            }
            
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return {
                "error": str(e),
                "status": "error"
            }
    
    @staticmethod
    async def run_maintenance(db: AsyncSession):
        """Run complete database maintenance"""
        logger.info("Starting database maintenance...")
        
        try:
            # Create performance indexes
            await DatabaseOptimizer.create_performance_indexes(db)
            
            # Analyze tables
            await DatabaseOptimizer.analyze_tables(db)
            
            # Get stats
            stats = await DatabaseOptimizer.get_database_stats(db)
            logger.info(f"Database maintenance completed. Stats: {stats}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Database maintenance error: {e}")
            raise


class DatabaseManager:
    """Enhanced database manager with connection resilience and monitoring."""

    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._connection_failures = 0
        self._last_health_check = 0
        self._health_check_interval = 60  # Check health every 60 seconds
    
    def initialize(self, database_uri: str, env_is_local: bool, use_optimized_engine: bool = True):
        """Initializes the database engine and session factory."""
        global engine_db, AsyncSessionDB
        if self.engine and self.session_factory: # Prevent re-initialization
            return

        if use_optimized_engine:
            engine_db = DatabaseOptimizer.get_engine(database_uri, env_is_local)
        else:
            engine_db = create_async_engine(
                database_uri,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=3600,
                pool_size=10,
                max_overflow=20,
                pool_timeout=30
            )

        AsyncSessionDB = sessionmaker(
            bind=engine_db,
            class_=AsyncSession,
            expire_on_commit=False
        )
        self.set_engine_and_session_factory(engine_db, AsyncSessionDB)

    def set_engine_and_session_factory(self, engine, session_factory):
        self.engine = engine
        self.session_factory = session_factory

    async def health_check(self) -> dict:
        """Perform database health check."""
        if not self.engine or not self.session_factory:
            return {"status": "uninitialized", "message": "Database not initialized."}

        start_time = time.time()

        try:
            async with self.session_factory() as session:
                # Simple query to test connection
                result = await session.execute(text("SELECT 1"))
                result.fetchone()

                response_time = (time.time() - start_time) * \
                    1000  # Convert to milliseconds

                structured_logger.info(
                    message="Database health check successful",
                    metadata={
                        "response_time_ms": response_time,
                        "connection_failures": self._connection_failures,
                    }
                )

                self._connection_failures = 0  # Reset failure count on success
                self._last_health_check = time.time()

                return {
                    "status": "healthy",
                    "response_time_ms": response_time,
                    "connection_failures": self._connection_failures,
                    "last_check": self._last_health_check,
                }

        except Exception as e:
            self._connection_failures += 1
            response_time = (time.time() - start_time) * 1000

            structured_logger.error(
                message="Database health check failed",
                metadata={
                    "response_time_ms": response_time,
                    "connection_failures": self._connection_failures,
                    "error_type": type(e).__name__,
                },
                exception=e,
            )

            return {
                "status": "unhealthy",
                "response_time_ms": response_time,
                "connection_failures": self._connection_failures,
                "error": str(e),
                "last_check": time.time(),
            }

    async def get_connection_pool_status(self) -> dict:
        """Get connection pool status information."""
        if not self.engine:
            return {"status": "uninitialized", "message": "Database not initialized."}
        
        pool = self.engine.pool

        try:
            return {
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                # Note: 'invalid' method may not be available in all pool types
                "invalid": getattr(pool, 'invalid', lambda: 0)(),
            }
        except Exception as e:
            # Fallback for pool types that don't support all methods
            return {
                "pool_size": getattr(pool, 'size', lambda: 0)(),
                "checked_in": getattr(pool, 'checkedin', lambda: 0)(),
                "checked_out": getattr(pool, 'checkedout', lambda: 0)(),
                "overflow": getattr(pool, 'overflow', lambda: 0)(),
                "invalid": 0,
                "error": f"Pool status partially unavailable: {str(e)}",
            }

    @asynccontextmanager
    async def get_session_with_retry(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with retry logic and exponential backoff."""
        if not self.session_factory:
            raise DatabaseException(message="Database session factory not initialized.")

        for attempt in range(max_retries + 1):
            try:
                async with self.session_factory() as session:
                    if attempt > 0:
                        structured_logger.info(
                            message=f"Database connection successful on attempt {attempt + 1}",
                            metadata={"attempt": attempt + 1,
                                      "max_retries": max_retries}
                        )
                    try:
                        yield session
                    except GeneratorExit:
                        # Normal generator exit, let it propagate
                        raise
                    finally:
                        # Ensure session is properly cleaned up after yield
                        await session.rollback()
                    return

            except (SQLAlchemyError, DisconnectionError, OperationalError) as e:
                self._connection_failures += 1

                if attempt == max_retries:
                    structured_logger.error(
                        message=f"Database connection failed after {max_retries + 1} attempts",
                        metadata={
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "total_failures": self._connection_failures,
                        },
                        exception=e,
                    )
                    raise DatabaseException(
                        message=f"Database connection failed after {max_retries + 1} attempts: {str(e)}",
                        metadata={
                            "attempts": max_retries + 1,
                            "error_type": type(e).__name__,
                        }
                    )

                # Calculate delay with exponential backoff
                delay = retry_delay * (backoff_factor ** attempt)

                structured_logger.warning(
                    message=f"Database connection failed on attempt {attempt + 1}, retrying in {delay}s",
                    metadata={
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "retry_delay": delay,
                        "error_type": type(e).__name__,
                    },
                    exception=e,
                )

                await asyncio.sleep(delay)


# Global database manager instance
db_manager = DatabaseManager()

def initialize_db(database_uri: str, env_is_local: bool, engine=None, use_optimized_engine: bool = True):
    """Initializes the database manager with engine and session factory."""
    if engine:
        # Use provided optimized engine
        global engine_db, AsyncSessionDB
        engine_db = engine
        AsyncSessionDB = sessionmaker(
            bind=engine_db,
            class_=AsyncSession,
            expire_on_commit=False
        )
        db_manager.set_engine_and_session_factory(engine_db, AsyncSessionDB)
    else:
        # Use default initialization with optional optimization
        db_manager.initialize(database_uri, env_is_local, use_optimized_engine)


# Enhanced dependency to get the async session with retry logic
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session with enhanced error handling and retry logic."""
    # Use the module-level structured logger
    session_logger = logger
    
    # Ensure database is initialized before getting a session
    if not db_manager.session_factory:
        raise DatabaseException(message="Database session factory not initialized.")

    try:
        async with db_manager.get_session_with_retry() as session:
            structured_logger.info(
                message="Database session created successfully",
            )
            try:
                yield session
            except GeneratorExit:
                # Normal generator exit
                raise
            except Exception:
                # Let exceptions from the calling code propagate
                raise
    except DatabaseException:
        # Re-raise database exceptions (already logged)
        raise
    except HTTPException:
        # Re-raise HTTP exceptions (like 401, 403, etc.) without wrapping
        raise
    except APIException:
        # Re-raise API exceptions without wrapping
        raise
    except (ValueError, ValidationError, RequestValidationError) as e:
        # Re-raise validation errors (including Pydantic validation errors)
        raise
    except SQLAlchemyError as e:
        # Handle database-specific errors
        structured_logger.error(
            message=f"Database error in session: {str(e)}",
            exception=e,
        )
        raise DatabaseException(
            message=f"Database error: {str(e)}",
        )
    except Exception as e:
        # Handle any other unexpected exceptions (but not HTTP/API exceptions)
        structured_logger.error(
            message=f"Unexpected error in database session: {str(e)}",
            exception=e,
        )
        raise DatabaseException(
            message=f"Database session error: {str(e)}",
        )


# Dependency for database health checks
async def get_db_health() -> dict:
    """Get database health status."""
    return await db_manager.health_check()


# Dependency for connection pool status
async def get_db_pool_status() -> dict:
    """Get database connection pool status."""
    return await db_manager.get_connection_pool_status()


# Async context manager for optimized database sessions
class OptimizedAsyncSession:
    """Optimized async session context manager"""
    
    def __init__(self, engine):
        self.engine = engine
        self.session = None
    
    async def __aenter__(self):
        from sqlalchemy.ext.asyncio import AsyncSession
        self.session = AsyncSession(
            self.engine,
            expire_on_commit=False,  # Keep objects accessible after commit
            autoflush=True,  # Auto-flush before queries
            autocommit=False
        )
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            if exc_type:
                await self.session.rollback()
            else:
                await self.session.commit()
            await self.session.close()


# Connection pool monitoring
async def monitor_connection_pool(engine):
    """Monitor connection pool health"""
    pool = engine.pool
    
    stats = {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalid()
    }
    
    logger.info(f"Connection pool stats: {stats}")
    
    # Alert if pool is getting full
    if stats["checked_out"] > (stats["pool_size"] * 0.8):
        logger.warning("Connection pool is getting full!")
    
    return stats