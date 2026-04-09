from sqlalchemy.orm import sessionmaker, declarative_base, Mapped, mapped_column
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
from core.utils.uuid_utils import uuid7
from core.exceptions import DatabaseException, APIException

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


# Database connection configuration - NOW INITIALIZED LATER
engine_db = None
AsyncSessionDB = None

class DatabaseManager:
    """Enhanced database manager with connection resilience and monitoring."""

    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._connection_failures = 0
        self._last_health_check = 0
        self._health_check_interval = 60  # Check health every 60 seconds
    
    def initialize(self, database_uri: str, env_is_local: bool):
        """Initializes the database engine and session factory."""
        global engine_db, AsyncSessionDB
        if self.engine and self.session_factory: # Prevent re-initialization
            return

        # SQLite doesn't need pooling, PostgreSQL does
        if database_uri.startswith("sqlite"):
            engine_db = create_async_engine(
                database_uri,
                echo=env_is_local,
                pool_pre_ping=False,  # SQLite doesn't support pool_pre_ping well
                poolclass=None  # No pooling for SQLite
            )
        else:
            # PostgreSQL with connection pooling
            engine_db = create_async_engine(
                database_uri,
                echo=env_is_local,
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

                logger.info(
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

            logger.error(
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

    async def get_session_with_retry(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with retry logic and exponential backoff.
        
        Note: This is not decorated with @asynccontextmanager because we need
        to handle the generator lifecycle manually to avoid 'athrow' errors.
        """
        if not self.session_factory:
            raise DatabaseException(message="Database session factory not initialized.")

        for attempt in range(max_retries + 1):
            session = None
            try:
                session = self.session_factory()
                if attempt > 0:
                    logger.info(
                        message=f"Database connection successful on attempt {attempt + 1}",
                        metadata={"attempt": attempt + 1,
                                  "max_retries": max_retries}
                    )
                
                # Yield the session - this is where the caller's code runs
                try:
                    yield session
                except Exception:
                    # Rollback on any exception from caller
                    await session.rollback()
                    raise
                finally:
                    # Always close the session
                    await session.close()
                
                # Success - exit the retry loop
                return

            except (SQLAlchemyError, DisconnectionError, OperationalError) as e:
                self._connection_failures += 1
                
                # Clean up the session if it was created
                if session is not None:
                    await session.close()

                if attempt == max_retries:
                    logger.error(
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

                logger.warning(
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

async def initialize_db(database_uri: str, env_is_local: bool, engine=None):
    """Initializes the database manager with engine and session factory.
    
    For SQLite (dev): Auto-creates tables on startup.
    For PostgreSQL (prod): Requires Alembic migrations - won't auto-create tables.
    """
    if engine:
        # Use provided engine
        global engine_db, AsyncSessionDB
        engine_db = engine
        AsyncSessionDB = sessionmaker(
            bind=engine_db,
            class_=AsyncSession,
            expire_on_commit=False
        )
        db_manager.set_engine_and_session_factory(engine_db, AsyncSessionDB)
    else:
        # Use default initialization
        db_manager.initialize(database_uri, env_is_local)
        
        # Auto-create tables for SQLite only (dev environment)
        if database_uri.startswith("sqlite"):
            logger.info("SQLite detected - auto-creating tables...")
            try:
                # SQLite doesn't support schemas, so we need to remove schema prefixes
                # Create a copy of metadata with schemas removed for SQLite
                from sqlalchemy import MetaData, Table, ForeignKey, Index
                import re
                
                # Create new metadata without schemas
                sqlite_metadata = MetaData()
                
                # Helper function to remove schema from table reference
                def remove_schema(ref):
                    """Remove schema prefix from table references like 'auth.users' -> 'users'"""
                    if isinstance(ref, str):
                        parts = ref.split('.')
                        if len(parts) == 2 and parts[0] in ('auth', 'catalog', 'commerce', 'admin'):
                            return parts[1]
                    return ref
                
                # Copy all tables from Base.metadata, removing schema
                for table in Base.metadata.tables.values():
                    new_columns = []
                    
                    for column in table.columns:
                        # Copy the column
                        new_col = column.copy()
                        
                        # Fix ForeignKey constraints
                        if new_col.foreign_keys:
                            for fk in new_col.foreign_keys:
                                if fk.target_fullname:
                                    # Remove schema from target reference
                                    fk.target_fullname = remove_schema(fk.target_fullname)
                        
                        new_columns.append(new_col)
                    
                    # Copy the table without schema (indexes will be auto-created from the column definitions)
                    Table(
                        table.name,  # Just the name, no schema
                        sqlite_metadata,
                        *new_columns,
                    )
                
                async with db_manager.engine.begin() as conn:
                    await conn.run_sync(sqlite_metadata.create_all)
                logger.info("SQLite tables created successfully ✅")
            except Exception as e:
                logger.error(f"Failed to create SQLite tables: {e}")
                raise
        else:
            logger.info("PostgreSQL detected - tables must be managed via Alembic migrations")


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
            logger.info(
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
        logger.error(
            message=f"Database error in session: {str(e)}",
            exception=e,
        )
        raise DatabaseException(
            message=f"Database error: {str(e)}",
        )
    except Exception as e:
        # Handle any other unexpected exceptions (but not HTTP/API exceptions)
        logger.error(
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

