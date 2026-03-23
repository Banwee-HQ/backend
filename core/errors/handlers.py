from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
from core.utils.uuid_utils import uuid7
import traceback

from .api_exceptions import APIException


async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    """Handle custom API exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "error_code": exc.error_code,
            "correlation_id": exc.correlation_id,
            "timestamp": exc.timestamp,
            "detail": exc.detail if exc.detail != exc.message else None
        }
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle standard HTTP exceptions"""
    correlation_id = str(uuid7())

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "error_code": f"HTTP_{exc.status_code}",
            "correlation_id": correlation_id,
            "timestamp": datetime.now().isoformat()
        }
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors"""
    correlation_id = str(uuid7())

    # Format validation errors
    errors = {}
    for error in exc.errors():
        field = ".".join(str(loc)
                         for loc in error["loc"][1:])  # Skip 'body' prefix
        errors[field] = error["msg"]

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Validation failed",
            "error_code": "VALIDATION_ERROR",
            "correlation_id": correlation_id,
            "timestamp": datetime.now().isoformat(),
            "errors": errors
        }
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle SQLAlchemy database errors"""
    correlation_id = str(uuid7())

    # Log the full error for debugging
    print(f"Database error [{correlation_id}]: {str(exc)}")
    print(traceback.format_exc())

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "A database error occurred",
            "error_code": "DATABASE_ERROR",
            "correlation_id": correlation_id,
            "timestamp": datetime.now().isoformat()
        }
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    correlation_id = str(uuid7())

    # Log the full error for debugging
    print(f"Unexpected error [{correlation_id}]: {str(exc)}")
    print(traceback.format_exc())

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "An unexpected error occurred",
            "error_code": "INTERNAL_ERROR",
            "correlation_id": correlation_id,
            "timestamp": datetime.now().isoformat()
        }
    )
