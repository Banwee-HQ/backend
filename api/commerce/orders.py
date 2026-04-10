from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from core.logging import get_structured_logger as get_logger
from core.db import get_db
from core.utils.response import Response
from core.exceptions import APIException
from services.commerce.orders import OrderService
from models.accounts.user import User
from schemas.commerce.orders import Create, Checkout, Note
from core.dependencies import get_current_auth_user, get_order_service
logger = get_logger(__name__)

router = APIRouter(prefix="/orders", tags=["Orders"])


# ==========================================================
# ORDERS - 5 Standard APIs
# ==========================================================
@router.post("/")
async def create(
    request: Create,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new order."""
    try:
        order_service = OrderService(db)
        order = await order_service.create(current_user.id, request, background_tasks)
        return Response.success(data=order, message="Order created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=400, message=f"Failed to create order: {str(e)}")


@router.get("/{order_id}")
async def get(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    order_service: OrderService = Depends(get_order_service)
):
    """Get a specific order."""
    try:
        order = await order_service.get(order_id, current_user.id)
        if not order:
            raise APIException(status_code=404, message="Order not found")
        return Response.success(data=order)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to fetch order: {str(e)}")


@router.get("/")
async def list(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status_filter: Optional[str] = Query(None),
    current_user: User = Depends(get_current_auth_user),
    order_service: OrderService = Depends(get_order_service)
):
    """List user's orders."""
    try:
        orders = await order_service.list(current_user.id, page, limit, status_filter)
        if isinstance(orders, dict):
            # support different shapes returned by service
            if "orders" in orders and "pagination" in orders:
                return Response.success(data=orders.get("orders", []), pagination=orders.get("pagination", {}))
            if "data" in orders:
                pagination = {
                    "page": orders.get("page", page),
                    "limit": orders.get("limit", limit),
                    "total": orders.get("total", 0),
                    "pages": orders.get("pages", 1)
                }
                return Response.success(data=orders.get("data", []), pagination=pagination)
        return Response.success(data=orders)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to fetch orders: {str(e)}")


# ==========================================================
# KEPT ROUTES
# ==========================================================
@router.post("/checkout/validate")
async def validate(
    request: Checkout,
    current_user: User = Depends(get_current_auth_user),
    order_service: OrderService = Depends(get_order_service)
):
    """Comprehensive checkout validation."""
    try:
        validation_result = await order_service.validate_checkout(current_user.id, request)
        return Response.success(data=validation_result)
    except Exception as e:
        raise APIException(status_code=500, message=f"Checkout validation failed: {str(e)}")


@router.post("/checkout")
async def checkout(
    request: Checkout,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_auth_user),
    order_service: OrderService = Depends(get_order_service)
):
    """Place order with comprehensive validation."""
    try:
        order = await order_service.place(current_user.id, request, background_tasks)
        return Response.success(data=order, message="Order placed successfully")
    except Exception as e:
        raise APIException(status_code=500, message=f"Order placement failed: {str(e)}")


@router.patch("/{order_id}/cancel")
async def cancel(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    order_service: OrderService = Depends(get_order_service)
):
    """Cancel an order."""
    try:
        order = await order_service.cancel(order_id, current_user.id)
        return Response.success(data=order, message="Order cancelled successfully")
    except Exception as e:
        raise APIException(status_code=400, message="Failed to cancel order")



@router.get("/{order_id}/invoice")
async def get_invoice(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    order_service: OrderService = Depends(get_order_service)
):
    """Get order invoice (PDF)."""
    try:
        invoice_result = await order_service.invoice(order_id, current_user.id)
        if invoice_result.get('success') and invoice_result.get('pdf_bytes'):
            from fastapi.responses import Response
            return Response(
                content=invoice_result['pdf_bytes'],
                media_type="application/pdf",
                headers={"Content-Disposition": f"attachment; filename=invoice-{invoice_result.get('invoice_ref', 'unknown')}.pdf"}
            )
        raise APIException(status_code=500, message=invoice_result.get('message', 'Failed to generate invoice'))
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to generate invoice: {str(e)}")


# ==========================================================
# NOTES - Create, Get, List Only (Immutable Audit Records)
# ==========================================================
@router.post("/{order_id}/notes")
async def create(
    order_id: UUID,
    request: Note,
    current_user: User = Depends(get_current_auth_user),
    order_service: OrderService = Depends(get_order_service)
):
    """Add note to order."""
    try:
        result = await order_service.add_note(order_id, current_user.id, request.note)
        return Response.success(data=result, message="Note added successfully")
    except Exception as e:
        raise APIException(status_code=400, message=f"Failed to add note: {str(e)}")


@router.get("/{order_id}/notes/{note_index}")
async def get(
    order_id: UUID,
    note_index: int,
    current_user: User = Depends(get_current_auth_user),
    order_service: OrderService = Depends(get_order_service)
):
    """Get a specific note by index."""
    try:
        note = await order_service.get_note(order_id, current_user.id, note_index)
        if not note:
            raise APIException(status_code=404, message="Note not found")
        return Response.success(data=note)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to get note: {str(e)}")


@router.get("/{order_id}/notes")
async def list(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    order_service: OrderService = Depends(get_order_service)
):
    """List all notes for an order."""
    try:
        notes = await order_service.notes(order_id, current_user.id)
        return Response.success(data=notes)
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to get notes: {str(e)}")
