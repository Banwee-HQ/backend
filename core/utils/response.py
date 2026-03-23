"""
Response utility for consistent API responses
"""
from typing import Any, Optional, Dict
from fastapi.responses import JSONResponse
from fastapi import status
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date


class Response(JSONResponse):
    """
    Standardized API response wrapper that matches frontend expectations
    Inherits from JSONResponse to be directly returnable from FastAPI routes
    """

    def __init__(
        self,
        success: bool = True,
        data: Any = None,
        message: str = "Success",
        status_code: int = status.HTTP_200_OK,
        code: Optional[int] = None,  # For backward compatibility
        pagination: Optional[Dict[str, Any]] = None,
        errors: Optional[list] = None,
        **kwargs
    ):
        """
        Initialize response object that can be returned directly from FastAPI routes
        """
        # Use code parameter if provided for backward compatibility
        final_status_code = code if code is not None else status_code

        # Convert Pydantic models to dictionaries for JSON serialization
        serialized_data = self._serialize_data(data)

        response_data = {
            "success": success,
            "data": serialized_data,
            "message": message
        }

        if pagination:
            response_data["pagination"] = pagination

        if errors:
            response_data["errors"] = errors

        super().__init__(
            content=response_data,
            status_code=final_status_code,
            **kwargs
        )

    def _serialize_data(self, data: Any) -> Any:
        """
        Convert Pydantic models and other non-serializable objects to JSON-serializable format
        """
        if data is None:
            return None
        elif isinstance(data, BaseModel):
            # Convert Pydantic model to dict with JSON serialization mode
            return data.model_dump(mode='json')
        elif isinstance(data, UUID):
            # Convert UUID to string
            return str(data)
        elif isinstance(data, (datetime, date)):
            # Convert datetime/date to ISO string
            return data.isoformat()
        elif isinstance(data, list):
            # Convert list of items (may contain Pydantic models)
            return [self._serialize_data(item) for item in data]
        elif isinstance(data, dict):
            # Convert dict values (may contain Pydantic models)
            return {key: self._serialize_data(value) for key, value in data.items()}
        else:
            # Return as-is for JSON-serializable types
            return data

    @staticmethod
    def success(
        data: Any = None,
        message: str = "Success",
        status_code: int = status.HTTP_200_OK,
        code: Optional[int] = None,  # For backward compatibility
        pagination: Optional[Dict[str, Any]] = None
    ) -> "Response":
        """
        Create a successful response
        """
        return Response(
            success=True,
            data=data,
            message=message,
            status_code=status_code,
            code=code,
            pagination=pagination
        )

    @staticmethod
    def error(
        message: str = "An error occurred",
        status_code: int = status.HTTP_400_BAD_REQUEST,
        data: Any = None,
        errors: Optional[list] = None
    ) -> "Response":
        """
        Create an error response
        """
        return Response(
            success=False,
            data=data,
            message=message,
            status_code=status_code,
            errors=errors
        )


def create_response(
    success: bool = True,
    data: Any = None,
    message: str = "Success",
    status_code: int = status.HTTP_200_OK,
    pagination: Optional[Dict[str, Any]] = None,
    errors: Optional[list] = None
) -> Response:
    """
    Helper function to create standardized responses
    """
    return Response(
        success=success,
        data=data,
        message=message,
        status_code=status_code,
        pagination=pagination,
        errors=errors
    )
