"""
Transaction Service for atomic operations and rollback mechanisms
Implements atomic operations for product removal and ensures data consistency
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Dict, Any, Callable, TypeVar, Generic
from uuid import UUID
from datetime import datetime
from core.logging import get_structured_logger
from functools import wraps
import asyncio

logger = get_structured_logger(__name__)

T = TypeVar('T')

class TransactionError(Exception):
    """Custom exception for transaction-related errors"""
    def __init__(self, message: str, original_error: Optional[Exception] = None, rollback_data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.original_error = original_error
        self.rollback_data = rollback_data


class TransactionContext:
    """Context for tracking transaction state and rollback data"""
    
    def __init__(self, operation_id: str, db_session: AsyncSession):
        self.operation_id = operation_id
        self.db_session = db_session
        self.rollback_data: Dict[str, Any] = {}
        self.savepoints: Dict[str, Any] = {}
        self.started_at = datetime.utcnow()
        self.committed = False
        self.rolled_back = False
    
    def add_rollback_data(self, key: str, data: Any) -> None:
        """Add data that can be used for rollback operations"""
        self.rollback_data[key] = data
    
    def get_rollback_data(self, key: str) -> Any:
        """Get rollback data by key"""
        return self.rollback_data.get(key)
    
    async def create_savepoint(self, name: str) -> None:
        """Create a savepoint within the transaction"""
        try:
            savepoint = await self.db_session.begin_nested()
            self.savepoints[name] = savepoint
            logger.info(f"Created savepoint '{name}' for transaction {self.operation_id}")
        except SQLAlchemyError as e:
            logger.error(f"Failed to create savepoint '{name}': {e}")
            raise TransactionError(f"Failed to create savepoint: {e}", original_error=e)
    
    async def rollback_to_savepoint(self, name: str) -> None:
        """Rollback to a specific savepoint"""
        savepoint = self.savepoints.get(name)
        if not savepoint:
            raise TransactionError(f"Savepoint '{name}' not found")
        
        try:
            await savepoint.rollback()
            logger.info(f"Rolled back to savepoint '{name}' for transaction {self.operation_id}")
        except SQLAlchemyError as e:
            logger.error(f"Failed to rollback to savepoint '{name}': {e}")
            raise TransactionError(f"Failed to rollback to savepoint: {e}", original_error=e)


class TransactionService:
    """Service for managing atomic operations with rollback capabilities"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._active_transactions: Dict[str, TransactionContext] = {}
    
    @asynccontextmanager
    async def atomic_operation(
        self,
        operation_id: Optional[str] = None,
        isolation_level: Optional[str] = None
    ) -> AsyncGenerator[TransactionContext, None]:
        """
        Context manager for atomic database operations with rollback capability
        
        Args:
            operation_id: Unique identifier for the operation
            isolation_level: Transaction isolation level (READ_COMMITTED, REPEATABLE_READ, etc.)
        """
        if operation_id is None:
            operation_id = f"txn_{datetime.utcnow().timestamp()}_{id(self)}"
        
        # Check if transaction already exists
        if operation_id in self._active_transactions:
            raise TransactionError(f"Transaction {operation_id} is already active")
        
        transaction_context = TransactionContext(operation_id, self.db)
        self._active_transactions[operation_id] = transaction_context
        
        try:
            # Set isolation level if specified
            if isolation_level:
                await self.db.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation_level}")
            
            logger.info(f"Started atomic operation {operation_id}")
            
            yield transaction_context
            
            # Commit the transaction if no exceptions occurred
            await self.db.commit()
            transaction_context.committed = True
            
            logger.info(f"Successfully committed atomic operation {operation_id}")
            
        except Exception as e:
            # Rollback the transaction on any exception
            try:
                await self.db.rollback()
                transaction_context.rolled_back = True
                logger.info(f"Rolled back atomic operation {operation_id} due to error: {e}")
            except SQLAlchemyError as rollback_error:
                logger.error(f"Failed to rollback transaction {operation_id}: {rollback_error}")
                raise TransactionError(
                    f"Transaction rollback failed: {rollback_error}",
                    original_error=e,
                    rollback_data=transaction_context.rollback_data
                )
            
            # Re-raise the original exception with transaction context
            if isinstance(e, TransactionError):
                raise
            else:
                raise TransactionError(
                    f"Atomic operation failed: {e}",
                    original_error=e,
                    rollback_data=transaction_context.rollback_data
                )
        
        finally:
            # Clean up transaction context
            if operation_id in self._active_transactions:
                del self._active_transactions[operation_id]
    
    async def execute_with_retry(
        self,
        operation: Callable[[], T],
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        operation_id: Optional[str] = None
    ) -> T:
        """
        Execute an operation with retry logic for transient failures
        
        Args:
            operation: The operation to execute
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (seconds)
            backoff_factor: Multiplier for delay on each retry
            operation_id: Unique identifier for the operation
        """
        if operation_id is None:
            operation_id = f"retry_op_{datetime.utcnow().timestamp()}_{id(self)}"
        
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                async with self.atomic_operation(f"{operation_id}_attempt_{attempt}") as ctx:
                    result = await operation()
                    return result
                    
            except TransactionError as e:
                last_error = e
                
                # Don't retry on certain types of errors
                if self._should_not_retry(e):
                    logger.info(f"Not retrying operation {operation_id} due to non-retryable error: {e}")
                    raise
                
                if attempt == max_retries:
                    logger.error(f"Operation {operation_id} failed after {max_retries + 1} attempts")
                    raise
                
                # Calculate delay with exponential backoff
                delay = retry_delay * (backoff_factor ** attempt)
                logger.warning(f"Operation {operation_id} failed on attempt {attempt + 1}, retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
        
        # This should never be reached, but just in case
        raise last_error or TransactionError(f"Operation {operation_id} failed after all retries")
    
    def _should_not_retry(self, error: TransactionError) -> bool:
        """Determine if an error should not be retried"""
        # Don't retry on validation errors, permission errors, etc.
        if error.original_error:
            error_type = type(error.original_error).__name__
            non_retryable_errors = [
                'ValidationError',
                'PermissionError',
                'HTTPException',
                'ValueError',
                'KeyError',
                'AttributeError'
            ]
            return error_type in non_retryable_errors
        
        return False
    
    async def get_transaction_status(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of an active transaction"""
        transaction = self._active_transactions.get(operation_id)
        if not transaction:
            return None
        
        return {
            "operation_id": transaction.operation_id,
            "started_at": transaction.started_at.isoformat(),
            "committed": transaction.committed,
            "rolled_back": transaction.rolled_back,
            "rollback_data_keys": list(transaction.rollback_data.keys()),
            "savepoints": list(transaction.savepoints.keys())
        }
    
    async def force_rollback(self, operation_id: str) -> bool:
        """Force rollback of an active transaction"""
        transaction = self._active_transactions.get(operation_id)
        if not transaction or transaction.committed or transaction.rolled_back:
            return False
        
        try:
            await transaction.db_session.rollback()
            transaction.rolled_back = True
            logger.info(f"Force rolled back transaction {operation_id}")
            return True
        except SQLAlchemyError as e:
            logger.error(f"Failed to force rollback transaction {operation_id}: {e}")
            return False


def transactional(
    isolation_level: Optional[str] = None,
    max_retries: int = 0,
    retry_delay: float = 1.0
):
    """
    Decorator for making methods transactional
    
    Args:
        isolation_level: Transaction isolation level
        max_retries: Number of retry attempts for transient failures
        retry_delay: Delay between retries
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Assume the service has a db attribute
            if not hasattr(self, 'db'):
                raise AttributeError("Service must have a 'db' attribute for transactional decorator")
            
            transaction_service = TransactionService(self.db)
            operation_id = f"{func.__name__}_{datetime.utcnow().timestamp()}"
            
            async def operation():
                return await func(self, *args, **kwargs)
            
            if max_retries > 0:
                return await transaction_service.execute_with_retry(
                    operation,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    operation_id=operation_id
                )
            else:
                async with transaction_service.atomic_operation(operation_id, isolation_level) as ctx:
                    return await operation()
        
        return wrapper
    return decorator


# Utility functions for common transaction patterns

async def execute_in_transaction(
    db: AsyncSession,
    operation: Callable[[TransactionContext], T],
    operation_id: Optional[str] = None,
    isolation_level: Optional[str] = None
) -> T:
    """
    Execute a single operation in a transaction
    
    Args:
        db: Database session
        operation: Operation to execute (receives TransactionContext)
        operation_id: Unique identifier for the operation
        isolation_level: Transaction isolation level
    """
    transaction_service = TransactionService(db)
    
    async with transaction_service.atomic_operation(operation_id, isolation_level) as ctx:
        return await operation(ctx)


async def execute_batch_operations(
    db: AsyncSession,
    operations: List[Callable[[TransactionContext], Any]],
    operation_id: Optional[str] = None,
    fail_fast: bool = True
) -> List[Any]:
    """
    Execute multiple operations in a single transaction
    
    Args:
        db: Database session
        operations: List of operations to execute
        operation_id: Unique identifier for the batch
        fail_fast: Whether to stop on first failure or collect all errors
    """
    transaction_service = TransactionService(db)
    results = []
    errors = []
    
    async with transaction_service.atomic_operation(operation_id) as ctx:
        for i, operation in enumerate(operations):
            try:
                # Create savepoint for each operation if not fail_fast
                if not fail_fast:
                    await ctx.create_savepoint(f"op_{i}")
                
                result = await operation(ctx)
                results.append(result)
                
            except Exception as e:
                if fail_fast:
                    raise TransactionError(f"Batch operation {i} failed: {e}", original_error=e)
                else:
                    # Rollback to savepoint and continue
                    await ctx.rollback_to_savepoint(f"op_{i}")
                    errors.append((i, e))
                    results.append(None)
        
        if errors and not fail_fast:
            # If we have errors but not failing fast, include them in rollback data
            ctx.add_rollback_data("batch_errors", errors)
    
    return results