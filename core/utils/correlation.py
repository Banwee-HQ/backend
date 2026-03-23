from core.utils.uuid_utils import uuid7
from typing import Optional, Any

# This function should ideally be used in conjunction with a middleware
# that sets a correlation ID on the request state.
# For now, it generates a new UUID if one is not found on the request state.
def get_correlation_id(request: Optional[Any] = None) -> str:
    """
    Retrieves a correlation ID from the request state or generates a new one.
    This function is intended to be used by FastAPI endpoints that need a correlation ID.
    In a full implementation, a middleware would ensure this is set on request.state.
    """
    if request and hasattr(request.state, "correlation_id"):
        return request.state.correlation_id
    return str(uuid7())
