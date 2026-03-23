from uuid import UUID
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query, status, BackgroundTasks, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from typing import Optional, Dict, Any, List
from core.db import get_db
from core.utils.response import Response
from core.errors import APIException
from core.logging import get_logger
from services.admin import AdminService
from services.orders import OrderService
from services.shipping import ShippingService
from services.products import ProductService
from services.review import ReviewService
from models.user import User
from models.subscriptions import Subscription
from models.product import ProductVariant
from models.refunds import Refund, RefundStatus, RefundItem
from models.orders import Order
from models.payments import PaymentIntent, Transaction
from services.auth import AuthService
from schemas.auth import UserCreate
from schemas.user import UserUpdate
from schemas.product import ProductCreate, ProductUpdate
from schemas.shipping import ShippingMethodCreate, ShippingMethodUpdate
from core.dependencies import get_current_auth_user

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

class ShipOrderRequest(BaseModel):
    tracking_number: str
    carrier_name: str

class UpdateOrderStatusRequest(BaseModel):
    status: str
    tracking_number: Optional[str] = None
    carrier_name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None

class UpdateRefundStatusRequest(BaseModel):
    status: str
    admin_notes: Optional[str] = None

class AdminUserUpdate(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

def require_admin(current_user: User = Depends(get_current_auth_user)):
    """Require admin role."""
    if current_user.role not in ["admin", "manager", "Admin", "SuperAdmin"]:
        raise APIException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Admin access required"
        )
    return current_user


def _parse_date_filter(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid date format. Use ISO format (YYYY-MM-DD)."
        )


@router.get("/subscriptions")
async def get_all_subscriptions(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all subscriptions (admin only)."""
    try:
        base_query = select(Subscription).join(User).options(
            selectinload(Subscription.user),
            selectinload(Subscription.products)
        )

        if status_filter:
            base_query = base_query.where(Subscription.status == status_filter)

        if search:
            search_term = f"%{search}%"
            base_query = base_query.where(
                or_(
                    User.email.ilike(search_term),
                    User.firstname.ilike(search_term),
                    User.lastname.ilike(search_term)
                )
            )

        parsed_from = _parse_date_filter(date_from)
        parsed_to = _parse_date_filter(date_to)

        if parsed_from:
            base_query = base_query.where(Subscription.created_at >= parsed_from)

        if parsed_to:
            if date_to and "T" not in date_to:
                parsed_to = parsed_to + timedelta(days=1)
                base_query = base_query.where(Subscription.created_at < parsed_to)
            else:
                base_query = base_query.where(Subscription.created_at <= parsed_to)

        sort_columns = {
            "created_at": Subscription.created_at,
            "status": Subscription.status,
            "next_billing_date": Subscription.next_billing_date,
            "total": Subscription.total,
            "price": Subscription.price
        }
        sort_column = sort_columns.get(sort_by, Subscription.created_at)
        base_query = base_query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())

        count_query = select(func.count()).select_from(Subscription).join(User)
        if status_filter:
            count_query = count_query.where(Subscription.status == status_filter)
        if search:
            search_term = f"%{search}%"
            count_query = count_query.where(
                or_(
                    User.email.ilike(search_term),
                    User.firstname.ilike(search_term),
                    User.lastname.ilike(search_term)
                )
            )
        if parsed_from:
            count_query = count_query.where(Subscription.created_at >= parsed_from)
        if parsed_to:
            if date_to and "T" not in date_to:
                count_query = count_query.where(Subscription.created_at < parsed_to)
            else:
                count_query = count_query.where(Subscription.created_at <= parsed_to)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        result = await db.execute(
            base_query.offset((page - 1) * limit).limit(limit)
        )
        subscriptions = result.scalars().all()

        subscriptions_data = []
        for subscription in subscriptions:
            payload = subscription.to_dict(include_products=True)
            variant_quantities = payload.get("variant_quantities") or {}
            variants_payload = []

            try:
                for variant in subscription.products or []:
                    variant_id = str(variant.id)
                    variants_payload.append({
                        "id": variant_id,
                        "name": variant.name,
                        "sku": variant.sku,
                        "base_price": float(variant.base_price),
                        "current_price": float(getattr(variant, "current_price", variant.base_price)),
                        "qty": int(variant_quantities.get(variant_id, 1))
                    })

                if not variants_payload:
                    variant_ids = payload.get("variant_ids") or []
                    resolved_ids = []
                    for variant_id in variant_ids:
                        try:
                            resolved_ids.append(UUID(str(variant_id)))
                        except Exception:
                            continue

                    if resolved_ids:
                        variant_result = await db.execute(
                            select(ProductVariant).where(ProductVariant.id.in_(resolved_ids))
                        )
                        variants = variant_result.scalars().all()
                        for variant in variants:
                            variant_id = str(variant.id)
                            variants_payload.append({
                                "id": variant_id,
                                "name": variant.name,
                                "sku": variant.sku,
                                "base_price": float(variant.base_price),
                                "current_price": float(getattr(variant, "current_price", variant.base_price)),
                                "qty": int(variant_quantities.get(variant_id, 1))
                            })
            except Exception:
                variants_payload = []
            payload["user"] = {
                "id": str(subscription.user.id) if subscription.user else None,
                "name": subscription.user.full_name if subscription.user else "",
                "email": subscription.user.email if subscription.user else ""
            }
            payload["base_cost"] = payload.get("subtotal", 0)
            payload["delivery_cost"] = payload.get("shipping_cost", 0)
            payload["total_cost"] = payload.get("total", 0)
            payload["subscription_plan"] = None
            payload["variants"] = variants_payload
            subscriptions_data.append(payload)

        pages = max(1, (total + limit - 1) // limit) if limit else 1

        return Response.success(data={
            "data": subscriptions_data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": pages
            }
        })
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch subscriptions: {str(e)}"
        )

# Basic Admin Routes
@router.get("/stats")
async def get_admin_stats(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get admin dashboard statistics with filters."""
    try:
        admin_service = AdminService(db)
        stats = await admin_service.get_dashboard_stats(
            date_from=date_from,
            date_to=date_to,
            status=status,
            category=category
        )
        return Response.success(data=stats)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch admin stats {str(e)}"
        )

@router.get("/dashboard")
async def get_dashboard_data(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive dashboard data."""
    try:
        admin_service = AdminService(db)
        
        # Get dashboard stats with date filters
        stats = await admin_service.get_dashboard_stats(
            date_from=date_from,
            date_to=date_to,
            status=status,
            category=category
        )
        
        return Response.success(data=stats)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch dashboard data {str(e)}"
        )

# Order Management Routes
@router.get("/orders")
async def get_all_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    order_status: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all orders (admin only)."""
    try:
        admin_service = AdminService(db)
        orders = await admin_service.get_all_orders(page, limit, order_status, q, date_from, date_to, min_price, max_price)
        return Response.success(data=orders)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch orders {str(e)}"
        )

@router.get("/orders/{order_id}")
async def get_order_by_id(
    order_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get a single order by ID (admin only)."""
    try:
        admin_service = AdminService(db)
        order = await admin_service.get_order_by_id(str(order_id))
        if not order:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Order not found"
            )
        return Response.success(data=order)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch order: {str(e)}"
        )

# Refunds Management Routes
@router.get("/refunds")
async def get_all_refunds(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    refund_status: Optional[RefundStatus] = Query(None, alias="status"),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all refunds (admin only)."""
    try:
        base_query = select(Refund).options(
            selectinload(Refund.user),
            selectinload(Refund.order)
        )

        if refund_status:
            base_query = base_query.where(Refund.status == refund_status)

        sort_column = Refund.created_at
        if sort_by == "amount":
            sort_column = Refund.requested_amount

        if sort_order == "asc":
            base_query = base_query.order_by(sort_column.asc())
        else:
            base_query = base_query.order_by(sort_column.desc())

        count_query = select(func.count()).select_from(Refund)
        if refund_status:
            count_query = count_query.where(Refund.status == refund_status)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        result = await db.execute(
            base_query.offset((page - 1) * limit).limit(limit)
        )
        refunds = result.scalars().all()

        refunds_data = []
        for refund in refunds:
            customer_name = refund.user.full_name if refund.user else ""
            refunds_data.append({
                "id": str(refund.id),
                "payment_id": None,
                "order_id": str(refund.order_id),
                "amount": float(refund.requested_amount),
                "currency": refund.currency,
                "status": refund.status.value if refund.status else None,
                "reason": refund.reason.value if refund.reason else None,
                "created_at": refund.created_at.isoformat() if refund.created_at else None,
                "customer_name": customer_name
            })

        # Calculate pages - ensure at least 1 page even if total is 0
        pages = max(1, (total + limit - 1) // limit) if limit else 1

        return Response.success(
            data={
                "data": refunds_data,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": pages
                }
            }
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch refunds {str(e)}"
        )

@router.get("/refunds/{refund_id}")
async def get_refund_details(
    refund_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get refund details (admin only)."""
    try:
        result = await db.execute(
            select(Refund)
            .where(Refund.id == refund_id)
            .options(
                selectinload(Refund.user),
                selectinload(Refund.order),
                selectinload(Refund.refund_items).selectinload(RefundItem.order_item)
            )
        )
        refund = result.scalars().first()

        if not refund:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Refund not found"
            )

        refund_data = refund.to_dict()
        refund_data["customer_name"] = refund.user.full_name if refund.user else ""
        refund_data["refund_items"] = [
            {
                "id": str(item.id),
                "order_item_id": str(item.order_item_id),
                "quantity_to_refund": item.quantity_to_refund,
                "unit_price": item.unit_price,
                "total_refund_amount": item.total_refund_amount,
                "condition_notes": item.condition_notes,
            }
            for item in refund.refund_items
        ]

        return Response.success(data=refund_data)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch refund details {str(e)}"
        )

@router.put("/refunds/{refund_id}/status")
async def update_refund_status(
    refund_id: UUID,
    payload: UpdateRefundStatusRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update refund status (admin only)."""
    try:
        result = await db.execute(select(Refund).where(Refund.id == refund_id))
        refund = result.scalars().first()

        if not refund:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Refund not found"
            )

        try:
            new_status = RefundStatus(payload.status)
        except Exception:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Invalid refund status"
            )

        refund.status = new_status
        if payload.admin_notes is not None:
            refund.admin_notes = payload.admin_notes

        now = datetime.now(timezone.utc)
        if new_status == RefundStatus.APPROVED:
            refund.approved_at = now
            refund.reviewed_at = now
            refund.reviewed_by = current_user.id
            if refund.approved_amount is None:
                refund.approved_amount = refund.requested_amount
        elif new_status == RefundStatus.REJECTED:
            refund.reviewed_at = now
            refund.reviewed_by = current_user.id
        elif new_status == RefundStatus.PROCESSING:
            refund.processed_at = now
            refund.processed_by = current_user.id
            if refund.processed_amount is None:
                refund.processed_amount = refund.approved_amount or refund.requested_amount
        elif new_status == RefundStatus.COMPLETED:
            refund.completed_at = now

        await db.commit()
        await db.refresh(refund)

        refund_data = refund.to_dict()
        refund_data["customer_name"] = refund.user.full_name if refund.user else ""
        return Response.success(data=refund_data, message="Refund status updated")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update refund status {str(e)}"
        )

@router.put("/orders/{order_id}/ship")
async def ship_order(
    order_id: str,
    request: ShipOrderRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update an order with shipping information (admin only)."""
    try:
        order_service = OrderService(db)
        order = await order_service.update_order_shipping_info(
            order_id,
            request.tracking_number,
            request.carrier_name,
            background_tasks
        )
        return Response.success(data=order, message="Order status updated to shipped.")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to update order: {str(e)}"
        )

@router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: str,
    request: UpdateOrderStatusRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update order status with tracking information (admin only)."""
    try:
        from services.orders import OrderService
        
        order_service = OrderService(db)
        order = await order_service.update_order_status(
            order_id=UUID(order_id),
            status=request.status,
            tracking_number=request.tracking_number,
            carrier_name=request.carrier_name,
            location=request.location,
            description=request.description,
            background_tasks=background_tasks
        )
        
        return Response.success(data={
            "id": str(order.id),
            "order_status": order.order_status.value if hasattr(order.order_status, 'value') else str(order.order_status),
            "tracking_number": order.tracking_number,
            "carrier_name": order.carrier_name
        }, message=f"Order status updated to {request.status}")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to update order status: {str(e)}"
        )

@router.get("/orders/{order_id}/invoice")
async def get_order_invoice_admin(
    order_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get order invoice (admin only)."""
    from fastapi.responses import StreamingResponse, FileResponse
    from services.orders import OrderService as OrderService
    import os
    import io
    
    try:
        order_service = OrderService(db)
        order_query = await db.execute(
            select(Order).where(Order.id == order_id)
        )
        order = order_query.scalar_one_or_none()
        
        if not order:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Order not found"
            )
        
        invoice = await order_service.generate_invoice(order_id, order.user_id)
        
        # Check if invoice generation was successful
        if not invoice.get('success', False):
            error_msg = invoice.get('message', 'Failed to generate invoice')
            raise APIException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=error_msg
            )
        
        # Handle pdf_bytes response (new format)
        if 'pdf_bytes' in invoice:
            pdf_bytes = invoice['pdf_bytes']
            return StreamingResponse(
                io.BytesIO(pdf_bytes),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=invoice-{order_id}.pdf"
                }
            )
        
        # Handle invoice_path response (legacy format)
        if 'invoice_path' in invoice and os.path.exists(invoice['invoice_path']):
            file_path = invoice['invoice_path']
            if file_path.endswith('.pdf'):
                return FileResponse(
                    path=file_path,
                    filename=f"invoice-{order_id}.pdf",
                    media_type="application/pdf"
                )
            else:
                return FileResponse(
                    path=file_path,
                    filename=f"invoice-{order_id}.docx",
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                )
        
        # Fallback: return invoice data as JSON
        return Response.success(data=invoice)
    except APIException:
        raise
    except Exception as e:
        logger.exception(f"Failed to generate invoice for order {order_id}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to generate invoice: {str(e)}"
        )

# User Management Routes
@router.get("/users")
async def get_all_users(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    role: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    verified: Optional[bool] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all users (admin only)."""
    try:
        admin_service = AdminService(db)
        users = await admin_service.get_all_users(
            page=page, 
            limit=limit, 
            role_filter=role, 
            search=search, 
            status=status, 
            verified=verified
        )
        return Response.success(data=users)
    except Exception as e:
        logger.exception("Failed to fetch users")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch users: {str(e)}"
        )

@router.post("/users")
async def create_user_admin(
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (admin only)."""
    try:
        admin_service = AdminService(db)
        user = await admin_service.create_user(user_data, background_tasks)
        return Response.success(data=user, message="User created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create user: {str(e)}"
        )

@router.get("/users/{user_id}")
async def get_user_by_id(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get a single user by ID (admin only)."""
    try:
        admin_service = AdminService(db)
        user = await admin_service.get_user_by_id(user_id)
        if not user:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="User not found"
            )
        return Response.success(data=user)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch user: {str(e)}"
        )

@router.get("/dashboard")
async def get_dashboard_data(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive dashboard data."""
    try:
        admin_service = AdminService(db)
        # Get platform overview (includes all dashboard stats, recent users, orders, top products, metrics)
        overview = await admin_service.get_platform_overview()
        return Response.success(data=overview)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch dashboard data {str(e)}"
        )

@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    is_active: bool,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update user status (admin only)."""
    try:
        admin_service = AdminService(db)
        user = await admin_service.update_user_status(user_id, is_active)
        return Response.success(data=user, message="User status updated")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Failed to update user status"
        )

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete user (admin only)."""
    try:
        admin_service = AdminService(db)
        await admin_service.delete_user(user_id)
        return Response.success(message="User deleted successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Failed to delete user"
        )

@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Send password reset email to user (admin only)."""
    try:
        admin_service = AdminService(db)
        result = await admin_service.reset_user_password(user_id)
        return Response.success(data=result, message="Password reset email sent successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to send password reset email: {str(e)}"
        )

@router.post("/users/{user_id}/deactivate")
async def deactivate_user_account(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Deactivate user account (admin only)."""
    try:
        admin_service = AdminService(db)
        result = await admin_service.deactivate_user(user_id)
        return Response.success(data=result, message="User account deactivated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to deactivate user: {str(e)}"
        )

@router.post("/users/{user_id}/activate")
async def activate_user_account(
    user_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Activate user account (admin only)."""
    try:
        admin_service = AdminService(db)
        result = await admin_service.activate_user(user_id)
        return Response.success(data=result, message="User account activated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to activate user: {str(e)}"
        )

# Product Management Routes
@router.get("/products")
async def get_all_products_admin(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    supplier: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all products (admin only)."""
    logger.debug(f"Fetching products: page={page}, limit={limit}, search={search}")
    try:
        admin_service = AdminService(db)
        products = await admin_service.get_all_products(page, limit, search, category, status, supplier)
        logger.debug(f"Successfully fetched {len(products.get('data', []))} products")
        return Response.success(data=products)
    except Exception as e:
        logger.exception("Failed to fetch products in admin route")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to fetch products"
        )

@router.post("/products")
async def create_product_admin(
    product_data: ProductCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new product (admin only)."""
    try:
        product_service = ProductService(db)
        product = await product_service.create_product(product_data, current_user.id)
        logger.info(f"Admin {current_user.id} created product {product.id}")
        return Response.success(data=product, message="Product created successfully")
    except APIException:
        raise
    except Exception as e:
        logger.exception("Failed to create product in admin route")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to create product"
        )

@router.get("/products/{product_id}")
async def get_product_by_id_admin(
    product_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get a single product by ID with all related data (admin only)."""
    try:
        from models.product import Product, ProductVariant, ProductImage, Category
        from models.inventories import Inventory
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        
        # Query product with all related data
        query = select(Product).options(
            selectinload(Product.variants).selectinload(ProductVariant.images),
            selectinload(Product.variants).selectinload(ProductVariant.inventory).selectinload(Inventory.location),
            selectinload(Product.category),
            selectinload(Product.supplier)
        ).where(Product.id == product_id)
        
        result = await db.execute(query)
        product = result.scalar_one_or_none()
        
        if not product:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Product not found"
            )
        
        # Convert to detailed dict with all related data
        product_data = product.to_dict(include_variants=True)
        
        # Add detailed variant information
        detailed_variants = []
        for variant in product.variants:
            variant_data = variant.to_dict(include_images=True, include_product=False)
            
            # Add inventory details with error handling
            if variant.inventory:
                try:
                    # Get warehouse location name if available
                    warehouse_location_name = None
                    if variant.inventory.location_id:
                        warehouse_location_name = getattr(variant.inventory.location, 'name', None)
                    
                    variant_data["inventory"] = {
                        "quantity_available": getattr(variant.inventory, 'quantity_available', 0),
                        "quantity": getattr(variant.inventory, 'quantity', 0),
                        "reorder_level": getattr(variant.inventory, 'reorder_level', None),
                        "reorder_quantity": getattr(variant.inventory, 'reorder_quantity', None),
                        "warehouse_location": warehouse_location_name,
                        "updated_at": variant.inventory.updated_at.isoformat() if variant.inventory.updated_at else None
                    }
                except Exception as inv_error:
                    logger.warning(f"Error processing inventory for variant {variant.id}: {inv_error}")
                    variant_data["inventory"] = {"error": "Failed to load inventory data"}
            
            detailed_variants.append(variant_data)
        
        product_data["variants"] = detailed_variants
        
        # Add category details with error handling
        if product.category:
            try:
                product_data["category"] = product.category.to_dict()
            except Exception as cat_error:
                logger.warning(f"Error processing category for product {product.id}: {cat_error}")
                product_data["category"] = {"error": "Failed to load category data"}
        
        # Add supplier details with error handling
        if product.supplier:
            try:
                supplier = product.supplier
                # Handle different possible name field combinations
                supplier_name = (
                    getattr(supplier, 'name', None) or 
                    getattr(supplier, 'firstname', None) and getattr(supplier, 'lastname', None) and 
                    f"{supplier.firstname} {supplier.lastname}".strip() or 
                    supplier.email
                )
                
                product_data["supplier"] = {
                    "id": str(supplier.id),
                    "name": supplier_name,
                    "email": getattr(supplier, 'email', None),
                    "phone": getattr(supplier, 'phone', None),
                }
            except Exception as sup_error:
                logger.warning(f"Error processing supplier for product {product.id}: {sup_error}")
                product_data["supplier"] = {"error": "Failed to load supplier data"}
        
        return Response.success(data=product_data)
    except APIException:
        raise
    except Exception as e:
        logger.exception(f"Failed to fetch product {product_id}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch product: {str(e)}"
        )

@router.put("/products/{product_id}")
async def update_product_admin(
    product_id: UUID,
    product_data: ProductUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a product (admin only)."""
    try:
        product_service = ProductService(db)
        product = await product_service.update_product(product_id, product_data, current_user.id, is_admin=True)
        return Response.success(data=product, message="Product updated successfully")
    except APIException:
        raise
    except Exception as e:
        logger.exception(f"Failed to update product {product_id}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update product: {str(e)}"
        )

@router.delete("/products/{product_id}")
async def delete_product_admin(
    product_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a product and all its associated data (admin only)."""
    try:
        product_service = ProductService(db)
        await product_service.delete_product(product_id, current_user.id, is_admin=True)
        return Response.success(message="Product deleted successfully")
    except HTTPException as e:
        raise APIException(status_code=e.status_code, message=e.detail)
    except Exception as e:
        logger.exception(f"Failed to delete product {product_id}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete product: {str(e)}"
        )

@router.get("/variants")
async def get_all_variants_admin(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    product_id: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all variants (admin only)."""
    try:
        admin_service = AdminService(db)
        variants = await admin_service.get_all_variants(page, limit, search, product_id)
        return Response.success(data=variants)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to fetch variants"
        )

@router.put("/variants/{variant_id}/stock")
async def update_variant_stock_admin(
    variant_id: UUID,
    stock_data: dict,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update variant stock (admin only)."""
    try:
        from models.inventories import Inventory
        from sqlalchemy import select
        
        stock = stock_data.get("stock")
        if stock is None or not isinstance(stock, int) or stock < 0:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Invalid stock value. Must be a non-negative integer."
            )
        
        # Find the inventory record for this variant
        query = select(Inventory).where(Inventory.variant_id == variant_id)
        result = await db.execute(query)
        inventory = result.scalar_one_or_none()
        
        if not inventory:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Inventory record not found for this variant"
            )
        
        # Update the stock
        inventory.quantity_available = stock
        inventory.quantity = stock  # Update legacy field too
        
        await db.commit()
        
        return Response.success(
            data={
                "variant_id": str(variant_id),
                "stock": stock,
                "updated_at": inventory.updated_at.isoformat() if inventory.updated_at else None
            },
            message="Variant stock updated successfully"
        )
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error updating variant stock: {e}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Failed to update variant stock"
        )

# Export Routes
@router.get("/orders/export")
async def export_orders(
    format: str = Query("csv"),
    order_status: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Export orders to CSV, Excel, or PDF (admin only)."""
    from fastapi.responses import StreamingResponse
    from services.export import ExportService
    
    if format not in ['csv', 'excel', 'pdf']:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid format. Use csv, excel, or pdf"
        )
    
    try:
        admin_service = AdminService(db)
        
        # Fetch all orders using pagination to avoid limit restrictions
        all_orders = []
        page = 1
        limit = 100
        
        while True:
            orders_data = await admin_service.get_all_orders(
                page=page, 
                limit=limit,
                order_status=order_status,
                q=q,
                date_from=date_from,
                date_to=date_to,
                min_price=min_price,
                max_price=max_price
            )
            
            orders_batch = orders_data.get('data', [])
            if not orders_batch:
                break
                
            all_orders.extend(orders_batch)
            
            # If we got less than the limit, we've reached the end
            if len(orders_batch) < limit:
                break
                
            page += 1
        
        orders = all_orders
        
        export_service = ExportService()
        
        if format == "csv":
            output = export_service.export_orders_to_csv(orders)
            media_type = "text/csv"
            filename = f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        elif format == "excel":
            output = export_service.export_orders_to_excel(orders)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        elif format == "pdf":
            output = export_service.export_orders_to_pdf(orders)
            media_type = "application/pdf"
            filename = f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        else:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Invalid format. Use csv, excel, or pdf"
            )
        
        return StreamingResponse(
            output,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except APIException:
        raise
    except Exception as e:
        logger.exception("Failed to export orders")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to export orders: {str(e)}"
        )

# Shipping Methods Management Routes
@router.get("/shipping-methods")
async def get_all_shipping_methods(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all shipping methods (admin only)."""
    try:
        shipping_service = ShippingService(db)
        methods = await shipping_service.get_all_shipping_methods()
        
        # Convert to dict format for API response
        methods_data = []
        for method in methods:
            methods_data.append({
                "id": str(method.id),
                "name": method.name,
                "description": method.description,
                "price": float(method.price),
                "estimated_days": method.estimated_days,
                "is_active": method.is_active,
                "carrier": method.carrier,
                "tracking_url_template": method.tracking_url_template,
                "created_at": method.created_at.isoformat() if method.created_at else None,
                "updated_at": method.updated_at.isoformat() if method.updated_at else None
            })
        
        return Response.success(data=methods_data)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch shipping methods: {str(e)}"
        )

@router.get("/shipping-methods/{method_id}")
async def get_shipping_method(
    method_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get a single shipping method by ID (admin only)."""
    try:
        shipping_service = ShippingService(db)
        method = await shipping_service.get_shipping_method_by_id(method_id)
        
        if not method:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Shipping method not found"
            )
        
        method_data = {
            "id": str(method.id),
            "name": method.name,
            "description": method.description,
            "price": float(method.price),
            "estimated_days": method.estimated_days,
            "is_active": method.is_active,
            "carrier": method.carrier,
            "tracking_url_template": method.tracking_url_template,
            "created_at": method.created_at.isoformat() if method.created_at else None,
            "updated_at": method.updated_at.isoformat() if method.updated_at else None
        }
        
        return Response.success(data=method_data)
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch shipping method: {str(e)}"
        )

@router.post("/shipping-methods")
async def create_shipping_method(
    method_data: ShippingMethodCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new shipping method (admin only)."""
    try:
        shipping_service = ShippingService(db)
        method = await shipping_service.create_shipping_method(method_data)
        
        method_response = {
            "id": str(method.id),
            "name": method.name,
            "description": method.description,
            "price": float(method.price),
            "estimated_days": method.estimated_days,
            "is_active": method.is_active,
            "carrier": method.carrier,
            "tracking_url_template": method.tracking_url_template,
            "created_at": method.created_at.isoformat() if method.created_at else None,
            "updated_at": method.updated_at.isoformat() if method.updated_at else None
        }
        
        return Response.success(data=method_response, message="Shipping method created successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to create shipping method: {str(e)}"
        )

@router.put("/shipping-methods/{method_id}")
async def update_shipping_method(
    method_id: UUID,
    method_data: ShippingMethodUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a shipping method (admin only)."""
    try:
        shipping_service = ShippingService(db)
        method = await shipping_service.update_shipping_method(method_id, method_data)
        
        if not method:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Shipping method not found"
            )
        
        method_response = {
            "id": str(method.id),
            "name": method.name,
            "description": method.description,
            "price": float(method.price),
            "estimated_days": method.estimated_days,
            "is_active": method.is_active,
            "carrier": method.carrier,
            "tracking_url_template": method.tracking_url_template,
            "created_at": method.created_at.isoformat() if method.created_at else None,
            "updated_at": method.updated_at.isoformat() if method.updated_at else None
        }
        
        return Response.success(data=method_response, message="Shipping method updated successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to update shipping method: {str(e)}"
        )

@router.delete("/shipping-methods/{method_id}")
async def delete_shipping_method(
    method_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a shipping method (admin only)."""
    try:
        shipping_service = ShippingService(db)
        success = await shipping_service.delete_shipping_method(method_id)
        
        if not success:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Shipping method not found"
            )
        
        return Response.success(message="Shipping method deleted successfully")
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Failed to delete shipping method: {str(e)}"
        )


# Include tax rates admin routes
# Tax Rates Admin Routes
from pydantic import Field
from typing import List

# Schemas for tax rates
class TaxRateCreate(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2 country code")
    country_name: str = Field(..., min_length=1, max_length=100)
    province_code: Optional[str] = Field(None, max_length=10, description="State/Province code")
    province_name: Optional[str] = Field(None, max_length=100)
    tax_rate: float = Field(..., ge=0, le=1, description="Tax rate as decimal (e.g., 0.0725 for 7.25%)")
    tax_name: Optional[str] = Field(None, max_length=50, description="e.g., GST, VAT, Sales Tax")
    is_active: bool = True


class TaxRateUpdate(BaseModel):
    country_name: Optional[str] = Field(None, min_length=1, max_length=100)
    province_name: Optional[str] = Field(None, max_length=100)
    tax_rate: Optional[float] = Field(None, ge=0, le=1)
    tax_name: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None


class TaxRateResponse(BaseModel):
    id: UUID
    country_code: str
    country_name: str
    province_code: Optional[str]
    province_name: Optional[str]
    tax_rate: float
    tax_percentage: float  # Computed: tax_rate * 100
    tax_name: Optional[str]
    is_active: bool
    created_at: str
    updated_at: Optional[str]

    class Config:
        from_attributes = True


@router.get("/tax-rates/", response_model=List[TaxRateResponse])
async def list_tax_rates(
    country_code: Optional[str] = Query(None, description="Filter by country code"),
    province_code: Optional[str] = Query(None, description="Filter by province code"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search in country/province names"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """List all tax rates with filtering and pagination"""
    from models.tax_rates import TaxRate
    from sqlalchemy import select, and_, or_
    
    try:
        # Build query
        query = select(TaxRate)
        
        # Apply filters
        conditions = []
        if country_code:
            conditions.append(TaxRate.country_code == country_code.upper())
        if province_code:
            conditions.append(TaxRate.province_code == province_code.upper())
        if is_active is not None:
            conditions.append(TaxRate.is_active == is_active)
        if search:
            search_term = f"%{search}%"
            conditions.append(
                or_(
                    TaxRate.country_name.ilike(search_term),
                    TaxRate.province_name.ilike(search_term)
                )
            )
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # Order by country, then province
        query = query.order_by(TaxRate.country_code, TaxRate.province_code)
        
        # Apply pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)
        
        result = await db.execute(query)
        tax_rates = result.scalars().all()
        
        # Format response
        response_data = []
        for rate in tax_rates:
            response_data.append(TaxRateResponse(
                id=rate.id,
                country_code=rate.country_code,
                country_name=rate.country_name,
                province_code=rate.province_code,
                province_name=rate.province_name,
                tax_rate=rate.tax_rate,
                tax_percentage=rate.tax_rate * 100,
                tax_name=rate.tax_name,
                is_active=rate.is_active,
                created_at=rate.created_at.isoformat(),
                updated_at=rate.updated_at.isoformat() if rate.updated_at else None
            ))
        
        return response_data
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to list tax rates: {str(e)}"
        )


@router.get("/tax-rates/countries", response_model=List[dict])
async def list_countries(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get list of unique countries with tax rates"""
    from models.tax_rates import TaxRate
    from sqlalchemy import select, func
    
    try:
        query = select(
            TaxRate.country_code,
            TaxRate.country_name,
            func.count(TaxRate.id).label('rate_count')
        ).group_by(
            TaxRate.country_code,
            TaxRate.country_name
        ).order_by(TaxRate.country_name)
        
        result = await db.execute(query)
        countries = result.all()
        
        return [
            {
                "country_code": row.country_code,
                "country_name": row.country_name,
                "rate_count": row.rate_count
            }
            for row in countries
        ]
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to list countries: {str(e)}"
        )


@router.get("/tax-rates/{tax_rate_id}", response_model=TaxRateResponse)
async def get_tax_rate(
    tax_rate_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific tax rate by ID"""
    from models.tax_rates import TaxRate
    from sqlalchemy import select
    
    try:
        result = await db.execute(
            select(TaxRate).where(TaxRate.id == tax_rate_id)
        )
        tax_rate = result.scalar_one_or_none()
        
        if not tax_rate:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Tax rate not found"
            )
        
        return TaxRateResponse(
            id=tax_rate.id,
            country_code=tax_rate.country_code,
            country_name=tax_rate.country_name,
            province_code=tax_rate.province_code,
            province_name=tax_rate.province_name,
            tax_rate=tax_rate.tax_rate,
            tax_percentage=tax_rate.tax_rate * 100,
            tax_name=tax_rate.tax_name,
            is_active=tax_rate.is_active,
            created_at=tax_rate.created_at.isoformat(),
            updated_at=tax_rate.updated_at.isoformat() if tax_rate.updated_at else None
        )
        
    except APIException:
        raise
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to get tax rate: {str(e)}"
        )


@router.post("/tax-rates/", response_model=TaxRateResponse, status_code=status.HTTP_201_CREATED)
async def create_tax_rate(
    data: TaxRateCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new tax rate"""
    from models.tax_rates import TaxRate
    from sqlalchemy import select, and_
    
    try:
        # Check if tax rate already exists for this location
        existing_query = select(TaxRate).where(
            and_(
                TaxRate.country_code == data.country_code.upper(),
                TaxRate.province_code == (data.province_code.upper() if data.province_code else None)
            )
        )
        result = await db.execute(existing_query)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message=f"Tax rate already exists for {data.country_code}" + 
                        (f"-{data.province_code}" if data.province_code else "")
            )
        
        # Create new tax rate
        tax_rate = TaxRate(
            country_code=data.country_code.upper(),
            country_name=data.country_name,
            province_code=data.province_code.upper() if data.province_code else None,
            province_name=data.province_name,
            tax_rate=data.tax_rate,
            tax_name=data.tax_name,
            is_active=data.is_active
        )
        
        db.add(tax_rate)
        await db.commit()
        await db.refresh(tax_rate)
        
        return TaxRateResponse(
            id=tax_rate.id,
            country_code=tax_rate.country_code,
            country_name=tax_rate.country_name,
            province_code=tax_rate.province_code,
            province_name=tax_rate.province_name,
            tax_rate=tax_rate.tax_rate,
            tax_percentage=tax_rate.tax_rate * 100,
            tax_name=tax_rate.tax_name,
            is_active=tax_rate.is_active,
            created_at=tax_rate.created_at.isoformat(),
            updated_at=tax_rate.updated_at.isoformat() if tax_rate.updated_at else None
        )
        
    except APIException:
        raise
    except Exception as e:
        await db.rollback()
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create tax rate: {str(e)}"
        )


@router.put("/tax-rates/{tax_rate_id}", response_model=TaxRateResponse)
async def update_tax_rate(
    tax_rate_id: UUID,
    data: TaxRateUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing tax rate"""
    from models.tax_rates import TaxRate
    from sqlalchemy import select
    
    try:
        result = await db.execute(
            select(TaxRate).where(TaxRate.id == tax_rate_id)
        )
        tax_rate = result.scalar_one_or_none()
        
        if not tax_rate:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Tax rate not found"
            )
        
        # Update fields
        if data.country_name is not None:
            tax_rate.country_name = data.country_name
        if data.province_name is not None:
            tax_rate.province_name = data.province_name
        if data.tax_rate is not None:
            tax_rate.tax_rate = data.tax_rate
        if data.tax_name is not None:
            tax_rate.tax_name = data.tax_name
        if data.is_active is not None:
            tax_rate.is_active = data.is_active
        
        await db.commit()
        await db.refresh(tax_rate)
        
        return TaxRateResponse(
            id=tax_rate.id,
            country_code=tax_rate.country_code,
            country_name=tax_rate.country_name,
            province_code=tax_rate.province_code,
            province_name=tax_rate.province_name,
            tax_rate=tax_rate.tax_rate,
            tax_percentage=tax_rate.tax_rate * 100,
            tax_name=tax_rate.tax_name,
            is_active=tax_rate.is_active,
            created_at=tax_rate.created_at.isoformat(),
            updated_at=tax_rate.updated_at.isoformat() if tax_rate.updated_at else None
        )
        
    except APIException:
        raise
    except Exception as e:
        await db.rollback()
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update tax rate: {str(e)}"
        )


@router.delete("/tax-rates/{tax_rate_id}")
async def delete_tax_rate(
    tax_rate_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a tax rate"""
    from models.tax_rates import TaxRate
    from sqlalchemy import select
    
    try:
        result = await db.execute(
            select(TaxRate).where(TaxRate.id == tax_rate_id)
        )
        tax_rate = result.scalar_one_or_none()
        
        if not tax_rate:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Tax rate not found"
            )
        
        await db.delete(tax_rate)
        await db.commit()
        
        return Response.success(message="Tax rate deleted successfully")
        
    except APIException:
        raise
    except Exception as e:
        await db.rollback()
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete tax rate: {str(e)}"
        )


@router.post("/tax-rates/bulk-update")
async def bulk_update_tax_rates(
    updates: List[dict],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Bulk update multiple tax rates"""
    from models.tax_rates import TaxRate
    from sqlalchemy import select
    
    try:
        updated_count = 0
        errors = []
        
        for update_data in updates:
            try:
                tax_rate_id = UUID(update_data.get("id"))
                result = await db.execute(
                    select(TaxRate).where(TaxRate.id == tax_rate_id)
                )
                tax_rate = result.scalar_one_or_none()
                
                if tax_rate:
                    if "tax_rate" in update_data:
                        tax_rate.tax_rate = float(update_data["tax_rate"])
                    if "is_active" in update_data:
                        tax_rate.is_active = bool(update_data["is_active"])
                    if "tax_name" in update_data:
                        tax_rate.tax_name = update_data["tax_name"]
                    
                    updated_count += 1
                else:
                    errors.append(f"Tax rate {tax_rate_id} not found")
                    
            except Exception as e:
                errors.append(f"Error updating {update_data.get('id')}: {str(e)}")
        
        await db.commit()
        
        return Response.success(
            data={
                "updated_count": updated_count,
                "errors": errors
            },
            message=f"Successfully updated {updated_count} tax rates"
        )
        
    except Exception as e:
        await db.rollback()
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to bulk update tax rates: {str(e)}"
        )

# --- Inventory Sync Endpoints ---
@router.post("/sync-inventory")
async def sync_all_inventory(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Sync all product availability statuses based on current inventory levels.
    This ensures products showing as out of stock actually have no inventory.
    Admin only - for data consistency maintenance.
    """
    try:
        from services.inventory import InventoryService
        inventory_service = InventoryService(db)
        result = await inventory_service.sync_all_products_availability()
        
        return Response.success(
            data=result,
            message=result.get("message", "Inventory sync completed")
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to sync inventory: {str(e)}"
        )


@router.post("/sync-inventory/product/{product_id}")
async def sync_product_inventory(
    product_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Sync a single product's availability status based on its variant inventory levels.
    Admin only - for data consistency maintenance.
    """
    try:
        from uuid import UUID as UUIDType
        from services.inventory import InventoryService
        
        product_id_uuid = UUIDType(product_id)
        inventory_service = InventoryService(db)
        result = await inventory_service.sync_product_availability_status(product_id_uuid)
        
        return Response.success(
            data=result,
            message="Product inventory synced successfully"
        )
    except ValueError:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid product ID format"
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to sync product inventory: {str(e)}"
        )


@router.get("/payments")
async def get_admin_payments(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all payments for admin management
    """
    try:
        # Build base query for PaymentIntents
        query = select(PaymentIntent).options(selectinload(PaymentIntent.user))
        
        # Apply filters
        if status:
            query = query.where(PaymentIntent.status == status)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    PaymentIntent.stripe_payment_intent_id.ilike(search_term),
                    PaymentIntent.payment_method_type.ilike(search_term)
                )
            )
        
        # Apply sorting
        if sort_by == "created_at":
            sort_column = PaymentIntent.created_at
        elif sort_by == "amount":
            # Extract amount from amount_breakdown JSON
            sort_column = PaymentIntent.amount_breakdown
        elif sort_by == "status":
            sort_column = PaymentIntent.status
        else:
            sort_column = PaymentIntent.created_at
        
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)
        
        # Execute query
        result = await db.execute(query)
        payment_intents = result.scalars().all()
        
        # Format response data
        payments_data = []
        for payment in payment_intents:
            # Extract amount from amount_breakdown
            amount = 0
            if payment.amount_breakdown:
                if isinstance(payment.amount_breakdown, dict):
                    amount = float(payment.amount_breakdown.get("total", 0))
                else:
                    amount = float(payment.amount_breakdown)
            
            payments_data.append({
                "id": str(payment.id),
                "order_id": str(payment.order_id) if payment.order_id else None,
                "amount": amount,
                "currency": payment.currency,
                "status": payment.status,
                "payment_method": payment.payment_method_type or "Unknown",
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
                "customer_name": payment.user.full_name if payment.user else "Unknown User"
            })
        
        # Calculate pagination info
        pages = (total + limit - 1) // limit
        
        return Response.success(
            data={
                "data": payments_data,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": pages
                }
            },
            message="Payments retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error fetching admin payments: {str(e)}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch payments: {str(e)}"
        )


# Category Management Endpoints
@router.get("/categories")
async def get_admin_categories(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get all categories for admin management."""
    try:
        from models.product import Category
        
        query = select(Category)
        count_query = select(func.count()).select_from(Category)
        
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Category.name.ilike(search_term),
                    Category.description.ilike(search_term)
                )
            )
            count_query = count_query.where(
                or_(
                    Category.name.ilike(search_term),
                    Category.description.ilike(search_term)
                )
            )
        
        query = query.order_by(Category.name.asc())
        
        total = await db.scalar(count_query)
        offset = (page - 1) * limit
        categories = (await db.execute(query.offset(offset).limit(limit))).scalars().all()
        
        categories_data = [
            {
                "id": str(category.id),
                "name": category.name,
                "description": category.description,
                "image_url": category.image_url,
                "is_active": category.is_active,
                "created_at": category.created_at.isoformat() if category.created_at else None,
                "updated_at": category.updated_at.isoformat() if category.updated_at else None
            }
            for category in categories
        ]
        
        pages = (total + limit - 1) // limit
        
        return Response.success(
            data={
                "data": categories_data,
                "page": page,
                "limit": limit,
                "total": total,
                "pages": pages
            },
            message="Categories retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error fetching admin categories: {str(e)}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch categories: {str(e)}"
        )


class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None


@router.post("/categories")
async def create_category(
    category_data: CategoryCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create a new category (admin only)."""
    try:
        from models.product import Category
        from core.utils.uuid_utils import uuid7
        from slugify import slugify
        
        # Check if category with same name exists
        existing = await db.scalar(
            select(Category).where(Category.name == category_data.name)
        )
        if existing:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message="Category with this name already exists"
            )
        
        category = Category(
            id=uuid7(),
            name=category_data.name,
            description=category_data.description,
            image_url=category_data.image_url,
            is_active=category_data.is_active
        )
        
        db.add(category)
        await db.commit()
        await db.refresh(category)
        
        return Response.success(
            data={
                "id": str(category.id),
                "name": category.name,
                "description": category.description,
                "image_url": category.image_url,
                "is_active": category.is_active,
                "created_at": category.created_at.isoformat() if category.created_at else None,
                "updated_at": category.updated_at.isoformat() if category.updated_at else None
            },
            message="Category created successfully"
        )
        
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error creating category: {str(e)}")
        await db.rollback()
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to create category: {str(e)}"
        )


@router.put("/categories/{category_id}")
async def update_category(
    category_id: UUID,
    category_data: CategoryUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update a category (admin only)."""
    try:
        from models.product import Category
        from slugify import slugify
        
        category = await db.get(Category, category_id)
        if not category:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Category not found"
            )
        
        # Check for name conflict if name is being updated
        if category_data.name and category_data.name != category.name:
            existing = await db.scalar(
                select(Category).where(
                    Category.name == category_data.name,
                    Category.id != category_id
                )
            )
            if existing:
                raise APIException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    message="Category with this name already exists"
                )
            
            category.name = category_data.name
        
        if category_data.description is not None:
            category.description = category_data.description
        
        if category_data.image_url is not None:
            category.image_url = category_data.image_url
        
        if category_data.is_active is not None:
            category.is_active = category_data.is_active
        
        category.updated_at = datetime.now(timezone.utc)
        
        await db.commit()
        await db.refresh(category)
        
        return Response.success(
            data={
                "id": str(category.id),
                "name": category.name,
                "description": category.description,
                "image_url": category.image_url,
                "is_active": category.is_active,
                "created_at": category.created_at.isoformat() if category.created_at else None,
                "updated_at": category.updated_at.isoformat() if category.updated_at else None
            },
            message="Category updated successfully"
        )
        
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error updating category: {str(e)}")
        await db.rollback()
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to update category: {str(e)}"
        )


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Delete a category (admin only)."""
    try:
        from models.product import Category, Product
        
        category = await db.get(Category, category_id)
        if not category:
            raise APIException(
                status_code=status.HTTP_404_NOT_FOUND,
                message="Category not found"
            )
        
        # Check if any products are using this category
        products_count = await db.scalar(
            select(func.count()).select_from(Product).where(Product.category_id == category_id)
        )
        
        if products_count > 0:
            raise APIException(
                status_code=status.HTTP_400_BAD_REQUEST,
                message=f"Cannot delete category. {products_count} product(s) are using this category."
            )
        
        await db.delete(category)
        await db.commit()
        
        return Response.success(
            data=None,
            message="Category deleted successfully"
        )
        
    except APIException:
        raise
    except Exception as e:
        logger.error(f"Error deleting category: {str(e)}")
        await db.rollback()
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to delete category: {str(e)}"
        )

@router.post("/recalculate-ratings")
async def recalculate_all_product_ratings(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Recalculate ratings for all products that have reviews"""
    try:
        review_service = ReviewService(db)
        updated_count = await review_service.recalculate_all_product_ratings()
        
        return Response.success(
            data={"updated_count": updated_count},
            message=f"Successfully recalculated ratings for {updated_count} products"
        )
    except Exception as e:
        logger.error(f"Error recalculating product ratings: {str(e)}")
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to recalculate product ratings: {str(e)}"
        )