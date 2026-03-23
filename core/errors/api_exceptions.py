from fastapi import HTTPException
from datetime import datetime
from core.utils.uuid_utils import uuid7
from typing import Any, Dict, Optional


class APIException(HTTPException):
    """Custom API exception with enhanced error details"""

    def __init__(
        self,
        status_code: int,
        message: str = "An unexpected API error occurred",  # Provide a default value
        detail: Optional[str] = None,
        error_code: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **kwargs
    ):
        self.message = message
        self.detail = detail or message
        self.error_code = error_code or f"ERR_{status_code}"
        self.correlation_id = correlation_id or str(uuid7())
        self.timestamp = datetime.now().isoformat()

        super().__init__(status_code=status_code, detail=self.detail, **kwargs)


class ValidationException(APIException):
    """Exception for validation errors"""

    def __init__(self, message: str = "Validation failed", errors: Optional[Dict[str, Any]] = None):
        self.errors = errors or {}
        super().__init__(
            status_code=422,
            message=message,
            error_code="VALIDATION_ERROR"
        )


class AuthenticationException(APIException):
    """Exception for authentication errors"""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            status_code=401,
            message=message,
            error_code="AUTH_ERROR"
        )


class AuthorizationException(APIException):
    """Exception for authorization errors"""

    def __init__(self, message: str = "Access denied"):
        super().__init__(
            status_code=403,
            message=message,
            error_code="AUTHORIZATION_ERROR"
        )


class NotFoundException(APIException):
    """Exception for resource not found errors"""

    def __init__(self, message: str = "Resource not found", resource: Optional[str] = None):
        self.resource = resource
        super().__init__(
            status_code=404,
            message=message,
            error_code="NOT_FOUND"
        )


class ConflictException(APIException):
    """Exception for conflict errors"""

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(
            status_code=409,
            message=message,
            error_code="CONFLICT_ERROR"
        )


class RateLimitException(APIException):
    """Exception for rate limiting errors"""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(
            status_code=429,
            message=message,
            error_code="RATE_LIMIT_ERROR"
        )


class DatabaseException(APIException):
    """Exception for database errors"""

    def __init__(self, message: str = "Database error occurred"):
        super().__init__(
            status_code=500,
            message=message,  # Explicitly pass message
            error_code="DATABASE_ERROR"
        )


class ExternalServiceException(APIException):
    """Exception for external service errors"""

    def __init__(self, message: str = "External service error", service: Optional[str] = None):
        self.service = service
        super().__init__(
            status_code=502,
            message=message,
            error_code="EXTERNAL_SERVICE_ERROR"
        )
