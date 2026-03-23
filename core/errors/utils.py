from core.utils.uuid_utils import uuid7
from datetime import datetime
from typing import Any, Dict, Optional


def get_correlation_id() -> str:
    """Generate a new correlation ID"""
    return str(uuid7())


def format_error_response(
    message: str,
    status_code: int = 500,
    error_code: Optional[str] = None,
    correlation_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Format a standardized error response"""
    return {
        "success": False,
        "message": message,
        "error_code": error_code or f"ERR_{status_code}",
        "correlation_id": correlation_id or get_correlation_id(),
        "timestamp": datetime.now().isoformat(),
        **kwargs
    }
