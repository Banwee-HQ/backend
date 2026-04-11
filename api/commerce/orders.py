from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from core.db import get_db
from core.dependencies import get_current_auth_user, get_order_service, require_admin
from core.exceptions import APIException
from core.logging import get_structured_logger
from services.commerce.orders import OrderService
from models.accounts.user import User
from schemas.commerce.orders import Create, Checkout, Note

router = APIRouter(prefix="/orders", tags=["Orders"])
logger = get_structured_logger(__name__)

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
    db: AsyncSession = Depends(get_db)
):
    """Get a specific order. Admins can view any order, users can only view their own."""
    try:
        order_service = OrderService(db)
        is_admin = current_user.role in [UserRole.ADMIN, UserRole.MANAGER]
        
        if is_admin:
            order = await order_service.get_by_id(order_id)
        else:
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
    customer_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List orders. Returns all orders for admin, user's orders for regular users."""
    try:
        order_service = OrderService(db)
        is_admin = current_user.role in [UserRole.ADMIN, UserRole.MANAGER]
        
        if is_admin:
            orders = await order_service.get_all_orders(
                page=page, limit=limit, customer_id=customer_id, status=status_filter,
                date_from=date_from, date_to=date_to, sort_by=sort_by, sort_order=sort_order
            )
        else:
            orders = await order_service.list(current_user.id, page, limit, status_filter)
            
        if isinstance(orders, dict):
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
    db: AsyncSession = Depends(get_db)
):
    """Comprehensive checkout validation."""
    try:
        order_service = OrderService(db)
        validation_result = await order_service.validate_checkout(current_user.id, request)
        return Response.success(data=validation_result)
    except Exception as e:
        raise APIException(status_code=500, message=f"Checkout validation failed: {str(e)}")


@router.post("/checkout")
async def checkout(
    request: Checkout,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Place order with comprehensive validation."""
    try:
        order_service = OrderService(db)
        order = await order_service.place(current_user.id, request, background_tasks)
        return Response.success(data=order, message="Order placed successfully")
    except Exception as e:
        raise APIException(status_code=500, message=f"Order placement failed: {str(e)}")


@router.patch("/{order_id}/cancel")
async def cancel(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel an order."""
    try:
        order_service = OrderService(db)
        order = await order_service.cancel(order_id, current_user.id)
        return Response.success(data=order, message="Order cancelled successfully")
    except Exception as e:
        raise APIException(status_code=400, message="Failed to cancel order")


@router.post("/{order_id}/cancel")
async def cancel_post(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Compatibility: allow POST to cancel an order."""
    return await cancel(order_id=order_id, current_user=current_user, db=db)



@router.get("/{order_id}/invoice")
async def get_invoice(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get order invoice (PDF)."""
    try:
        order_service = OrderService(db)
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
async def create_note(
    order_id: UUID,
    request: Note,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Add note to order."""
    try:
        order_service = OrderService(db)
        result = await order_service.add_note(order_id, current_user.id, request.note)
        return Response.success(data=result, message="Note added successfully")
    except Exception as e:
        raise APIException(status_code=400, message=f"Failed to add note: {str(e)}")


@router.get("/{order_id}/notes/{note_index}")
async def get_note(
    order_id: UUID,
    note_index: int,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific note by index."""
    try:
        order_service = OrderService(db)
        note = await order_service.get_note(order_id, current_user.id, note_index)
        if not note:
            raise APIException(status_code=404, message="Note not found")
        return Response.success(data=note)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to get note: {str(e)}")


@router.get("/{order_id}/notes")
async def list_notes(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """List all notes for an order."""
    try:
        order_service = OrderService(db)
        notes = await order_service.notes(order_id, current_user.id)
        return Response.success(data=notes)
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to get notes: {str(e)}")


# ==========================================================
# ORDER TRACKING - Moved from shipping_tracking.py
# ==========================================================
@router.get("/{order_id}/tracking")
async def get_tracking(
    order_id: UUID,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get order tracking information (authenticated)."""
    try:
        order_service = OrderService(db)
        tracking = await order_service.tracking(order_id, current_user.id)
        if tracking is None:
            raise APIException(status_code=404, message="Order not found or tracking unavailable")
        return Response.success(data=tracking)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to fetch tracking: {str(e)}")


@router.get("/{order_id}/shipments")
async def get_order_shipments(
    order_id: str,
    current_user: User = Depends(get_current_auth_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all shipments for an order."""
    try:
        from services.commerce.shipping_tracking import ShippingTrackingService
        shipping_service = ShippingTrackingService(db)
        shipments = await shipping_service.get_order_shipments(order_id)
        return Response.success(data=shipments)
    except Exception as e:
        raise APIException(
            status_code=500,
            message=f"Failed to get order shipments: {str(e)}"
        )


# ==========================================================
# PUBLIC TRACKING - No authentication required
# ==========================================================
@router.get("/track/{order_id}")
async def get_public_tracking(
    order_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get order tracking (public - no auth required)."""
    try:
        order_service = OrderService(db)
        tracking = await order_service.tracking_public(order_id)
        return Response.success(data=tracking)
    except Exception:
        raise APIException(status_code=404, message="Order not found or tracking unavailable")


@router.patch("/{order_id}/status")
async def update_status(
    order_id: str,
    request: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update order status (admin only)."""
    try:
        order_service = OrderService(db)
        updated_order = await order_service.update_status(order_id, request.get("status"), request.get("notes"))
        return Response.success(data=updated_order, message="Order status updated")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to update order status: {str(e)}")


@router.put("/{order_id}/deliver")
async def deliver(
    order_id: str,
    request: dict = {},
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Mark order as delivered (admin only)."""
    try:
        order_service = OrderService(db)
        result = await order_service.deliver(order_id, request.get("notes"))
        return Response.success(data=result, message="Order marked as delivered")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to mark order as delivered: {str(e)}")


@router.post("/{order_id}/ship")
async def ship(
    order_id: str,
    request: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Ship order (admin only)."""
    try:
        order_service = OrderService(db)
        result = await order_service.ship(order_id, request.get("carrier"), request.get("tracking_number"))
        return Response.success(data=result, message="Order shipped")
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to ship order: {str(e)}")


@router.get("/statistics")
async def statistics(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get order statistics (admin only)."""
    try:
        order_service = OrderService(db)
        stats = await order_service.get_statistics(date_from=date_from, date_to=date_to)
        return Response.success(data=stats)
    except APIException:
        raise
    except Exception as e:
        raise APIException(status_code=500, message=f"Failed to fetch statistics: {str(e)}")
