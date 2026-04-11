"""
Business Analytics API Routes
Provides comprehensive e-commerce metrics including conversion rates,
cart abandonment, time to first purchase, refund rates, and repeat customers
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID
from core.logging import get_structured_logger as get_logger

from core.db import get_db
from core.utils.response import Response
from models.accounts.user import User
from models.system import EventType
from models.accounts import TrafficSource
from services.analytics.analytics import AnalyticsService
from core.exceptions import APIException
from services.accounts.auth import AuthService
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_auth_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    auth_service = AuthService(db)
    return await auth_service.current_user(token)

def require_admin(current_user: User = Depends(get_current_auth_user)):
    """Require admin role."""
    from models.accounts.user import UserRole
    if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
        raise APIException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Admin access required"
        )
    return current_user

logger = get_logger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_analytics_service(db: AsyncSession = Depends(get_db)) -> AnalyticsService:
    """Dependency to get analytics service"""
    return AnalyticsService(db)


@router.post("/track")
async def track(
    event_data: dict,
    current_user: Optional[User] = Depends(get_current_auth_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Track an analytics event
    
    Used by frontend to track user interactions and e-commerce events.
    """
    try:
        event = await analytics_service.track_event(
            session_id=event_data.get("session_id"),
            event_type=EventType(event_data.get("event_type")),
            user_id=current_user.id if current_user else None,
            event_data=event_data.get("data", {}),
            page_url=event_data.get("page_url"),
            page_title=event_data.get("page_title"),
            order_id=UUID(event_data["order_id"]) if event_data.get("order_id") else None,
            product_id=UUID(event_data["product_id"]) if event_data.get("product_id") else None,
            revenue=event_data.get("revenue")
        )
        
        return Response.success(
            data={"event_id": str(event.id)},
            message="Event tracked successfully"
        )
        
    except ValueError as e:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Invalid event data: {str(e)}"
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to track event: {str(e)}"
        )


@router.get("/conversion-rates")
async def conversion_rates(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    traffic_source: Optional[TrafficSource] = Query(None, description="Filter by traffic source"),
    days: Optional[int] = Query(30, description="Number of days back from today (if dates not provided)"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get conversion rate metrics
    
    Returns overall conversion rates and breakdown by traffic source.
    Requires admin access.
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        metrics = await analytics_service.get_conversion_metrics(
            start_date=start_date,
            end_date=end_date,
            traffic_source=traffic_source
        )
        
        return Response.success(
            data=metrics,
            message="Conversion metrics retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve conversion metrics: {str(e)}"
        )


@router.get("/cart-abandonment")
async def cart_abandonment(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    days: Optional[int] = Query(30, description="Number of days back from today"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get cart abandonment metrics
    
    Returns cart abandonment rates and conversion funnel data.
    Requires admin access.
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        metrics = await analytics_service.get_cart_abandonment_metrics(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response.success(
            data=metrics,
            message="Cart abandonment metrics retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve cart abandonment metrics: {str(e)}"
        )


@router.get("/time-to-purchase")
async def time_to_purchase(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    days: Optional[int] = Query(30, description="Number of days back from today"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get time to first purchase metrics
    
    Returns statistics on how long it takes customers to make their first purchase.
    Requires admin access.
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        metrics = await analytics_service.get_time_to_purchase_metrics(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response.success(
            data=metrics,
            message="Time to purchase metrics retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve time to purchase metrics: {str(e)}"
        )


@router.get("/refund-rates")
async def refund_rates(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    days: Optional[int] = Query(30, description="Number of days back from today"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get refund rate metrics
    
    Returns refund rates and breakdown by reason.
    Requires admin access.
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        metrics = await analytics_service.get_refund_rate_metrics(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response.success(
            data=metrics,
            message="Refund rate metrics retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve refund rate metrics: {str(e)}"
        )


@router.get("/repeat-customers")
async def repeat_customers(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    days: Optional[int] = Query(30, description="Number of days back from today"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get repeat customer metrics
    
    Returns repeat purchase rates and customer segmentation data.
    Requires admin access.
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        metrics = await analytics_service.get_repeat_customer_metrics(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response.success(
            data=metrics,
            message="Repeat customer metrics retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve repeat customer metrics: {str(e)}"
        )


@router.get("/simple-dashboard")
async def simple_dashboard(
    current_user: User = Depends(get_current_auth_user)
):
    """Get simple dashboard data (no admin required for testing)"""
    return Response.success(data={
        "message": "Dashboard data",
        "user_role": current_user.role,
        "timestamp": datetime.now().isoformat(),
        "metrics": {
            "total_orders": 0,
            "total_revenue": 0.0,
            "total_users": 0
        }
    })


@router.get("/dashboard")
async def dashboard(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    days: Optional[int] = Query(30, description="Number of days back from today"),
    current_user: User = Depends(get_current_auth_user),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get comprehensive dashboard data
    
    Returns all key business metrics in a single response for dashboard display.
    """
    try:
        # Check if user has admin role
        from models.accounts.user import UserRole
        if current_user.role not in [UserRole.ADMIN, UserRole.MANAGER]:
            # Return limited data for non-admin users
            return Response.success(
                data={
                    "message": "Limited dashboard access",
                    "user_role": current_user.role,
                    "timestamp": datetime.now().isoformat(),
                    "metrics": {
                        "total_orders": 0,
                        "total_revenue": 0.0,
                        "total_users": 1
                    }
                },
                message="Dashboard data retrieved successfully (limited access)"
            )
        
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        dashboard_data = await analytics_service.get_comprehensive_dashboard_data(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response.success(
            data=dashboard_data,
            message="Dashboard data retrieved successfully"
        )
        
    except Exception as e:
        # Return basic data on error
        return Response.success(
            data={
                "message": "Dashboard data (fallback)",
                "user_role": current_user.role,
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "metrics": {
                    "total_orders": 0,
                    "total_revenue": 0.0,
                    "total_users": 1
                }
            },
            message="Dashboard data retrieved successfully (fallback)"
        )


@router.get("/sales-trend")
async def sales_trend(
    days: int = Query(30, description="Number of days to analyze"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get sales trend data over specified number of days
    
    Returns daily sales data for trend analysis.
    Requires admin access.
    """
    try:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        trend_data = await analytics_service.get_sales_trend_data(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response.success(
            data=trend_data,
            message="Sales trend data retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve sales trend data: {str(e)}"
        )


@router.get("/sales-overview")
async def sales_overview(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    days: Optional[int] = Query(30, description="Number of days back from today"),
    granularity: str = Query("daily", description="Data granularity: daily, weekly, monthly"),
    categories: Optional[str] = Query(None, description="Comma-separated category IDs"),
    regions: Optional[str] = Query(None, description="Comma-separated region IDs"),
    sales_channels: Optional[str] = Query("online,instore", description="Comma-separated sales channels"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get comprehensive sales overview data for dashboard
    
    Returns sales metrics, chart data, and performance indicators
    optimized for the sales overview dashboard.
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        # Parse filter parameters
        category_list = categories.split(',') if categories else []
        region_list = regions.split(',') if regions else []
        channel_list = sales_channels.split(',') if sales_channels else ['online', 'instore']
        
        # Get sales overview data
        overview_data = await analytics_service.get_sales_overview_data(
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            categories=category_list,
            regions=region_list,
            sales_channels=channel_list
        )
        
        return Response.success(
            data=overview_data,
            message="Sales overview data retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve sales overview data: {str(e)}"
        )


@router.get("/kpis")
async def kpis(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    days: Optional[int] = Query(7, description="Number of days back from today"),
    compare_previous: bool = Query(True, description="Include comparison with previous period"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get key performance indicators (KPIs)
    
    Returns summarized KPIs with optional comparison to previous period.
    Optimized for executive dashboards and quick insights.
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        # Get current period data
        current_data = await analytics_service.get_comprehensive_dashboard_data(
            start_date=start_date,
            end_date=end_date
        )
        
        kpis = {
            "period": current_data["period"],
            "kpis": {
                "conversion_rate": current_data["conversion"]["overall"]["conversion_rate"],
                "cart_abandonment_rate": current_data["cart_abandonment"]["abandonment_rates"]["overall_abandonment_rate"],
                "average_order_value": current_data["conversion"]["overall"]["average_order_value"],
                "refund_rate": current_data["refunds"]["overall"]["refund_rate"],
                "repeat_customer_rate": current_data["repeat_customers"]["overall"]["repeat_rate"],
                "total_revenue": current_data["conversion"]["overall"]["total_revenue"],
                "total_orders": current_data["refunds"]["overall"]["total_orders"],
                "avg_time_to_first_purchase_days": current_data["time_to_purchase"]["metrics"]["average_days"]
            }
        }
        
        # Add comparison with previous period if requested
        if compare_previous:
            period_length = end_date - start_date
            prev_end_date = start_date
            prev_start_date = prev_end_date - period_length
            
            try:
                previous_data = await analytics_service.get_comprehensive_dashboard_data(
                    start_date=prev_start_date,
                    end_date=prev_end_date
                )
                
                # Calculate percentage changes
                def calculate_change(current, previous):
                    if previous == 0:
                        return 0 if current == 0 else 100
                    return round(((current - previous) / previous) * 100, 2)
                
                kpis["comparison"] = {
                    "previous_period": {
                        "start_date": prev_start_date.isoformat(),
                        "end_date": prev_end_date.isoformat()
                    },
                    "changes": {
                        "conversion_rate": calculate_change(
                            current_data["conversion"]["overall"]["conversion_rate"],
                            previous_data["conversion"]["overall"]["conversion_rate"]
                        ),
                        "cart_abandonment_rate": calculate_change(
                            current_data["cart_abandonment"]["abandonment_rates"]["overall_abandonment_rate"],
                            previous_data["cart_abandonment"]["abandonment_rates"]["overall_abandonment_rate"]
                        ),
                        "average_order_value": calculate_change(
                            current_data["conversion"]["overall"]["average_order_value"],
                            previous_data["conversion"]["overall"]["average_order_value"]
                        ),
                        "refund_rate": calculate_change(
                            current_data["refunds"]["overall"]["refund_rate"],
                            previous_data["refunds"]["overall"]["refund_rate"]
                        ),
                        "repeat_customer_rate": calculate_change(
                            current_data["repeat_customers"]["overall"]["repeat_rate"],
                            previous_data["repeat_customers"]["overall"]["repeat_rate"]
                        ),
                        "total_revenue": calculate_change(
                            current_data["conversion"]["overall"]["total_revenue"],
                            previous_data["conversion"]["overall"]["total_revenue"]
                        )
                    }
                }
            except Exception as e:
                logger.warning(f"Failed to get comparison data: {e}")
                kpis["comparison"] = {"error": "Comparison data unavailable"}
        
        return Response.success(
            data=kpis,
            message="KPIs retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve KPIs: {str(e)}"
        )


@router.get("/sales")
async def sales(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    days: Optional[int] = Query(30, description="Number of days back from today"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """Get sales analytics. Requires admin access."""
    try:
        if not end_date:
            end_dt = datetime.now(timezone.utc)
        else:
            end_dt = datetime.fromisoformat(end_date).replace(tzinfo=timezone.utc)
        if not start_date:
            start_dt = end_dt - timedelta(days=days)
        else:
            start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)

        metrics = await analytics_service.get_revenue_metrics(start_date=start_dt, end_date=end_dt)
        return Response.success(data=metrics, message="Sales analytics retrieved successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve sales analytics: {str(e)}"
        )


@router.get("/users")
async def users(
    days: Optional[int] = Query(30),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get user analytics. Requires admin access."""
    try:
        from sqlalchemy import select, func
        from models.accounts.user import User as UserModel
        from datetime import datetime, timezone, timedelta

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)

        total_result = await db.execute(select(func.count()).select_from(UserModel))
        total_users = total_result.scalar() or 0

        new_result = await db.execute(
            select(func.count()).select_from(UserModel).where(UserModel.created_at >= start_dt)
        )
        new_users = new_result.scalar() or 0

        return Response.success(data={
            "total_users": total_users,
            "new_users": new_users,
            "period_days": days,
        }, message="User analytics retrieved successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve user analytics: {str(e)}"
        )


@router.get("/products")
async def products(
    days: Optional[int] = Query(30),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get product analytics. Requires admin access."""
    try:
        from sqlalchemy import select, func
        from models.catalog.product import Product

        total_result = await db.execute(select(func.count()).select_from(Product))
        total_products = total_result.scalar() or 0

        active_result = await db.execute(
            select(func.count()).select_from(Product).where(Product.is_active == True)
        )
        active_products = active_result.scalar() or 0

        return Response.success(data={
            "total_products": total_products,
            "active_products": active_products,
            "period_days": days,
        }, message="Product analytics retrieved successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve product analytics: {str(e)}"
        )


@router.get("/orders")
async def orders(
    days: Optional[int] = Query(30),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get order analytics. Requires admin access."""
    try:
        from sqlalchemy import select, func
        from models.commerce.orders import Order
        from datetime import datetime, timezone, timedelta

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=days)

        total_result = await db.execute(select(func.count()).select_from(Order))
        total_orders = total_result.scalar() or 0

        recent_result = await db.execute(
            select(func.count()).select_from(Order).where(Order.created_at >= start_dt)
        )
        recent_orders = recent_result.scalar() or 0

        return Response.success(data={
            "total_orders": total_orders,
            "recent_orders": recent_orders,
            "period_days": days,
        }, message="Order analytics retrieved successfully")
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve order analytics: {str(e)}"
        )


@router.get("/revenue")
async def revenue(
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    days: Optional[int] = Query(30, description="Number of days back from today"),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """
    Get revenue analytics
    
    Returns revenue metrics by time period, product, and traffic source.
    Requires admin access.
    """
    try:
        # Set default date range if not provided
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=days)
        
        metrics = await analytics_service.get_revenue_metrics(
            start_date=start_date,
            end_date=end_date
        )
        
        return Response.success(
            data=metrics,
            message="Revenue metrics retrieved successfully"
        )
        
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to retrieve revenue metrics: {str(e)}"
        )


# ==========================================================
# ADMIN ANALYTICS ENDPOINTS - Moved from admin.py
# ==========================================================

@router.get("/admin/stats", dependencies=[Depends(require_admin)])
async def get_admin_stats(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """Get admin dashboard statistics with filters."""
    try:
        stats = await analytics_service.get_admin_stats(
            date_from=date_from,
            date_to=date_to,
            status=status,
            category=category
        )
        return Response.success(data=stats)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch admin stats: {str(e)}"
        )


@router.get("/admin/dashboard", dependencies=[Depends(require_admin)])
async def get_admin_dashboard(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    current_user: User = Depends(require_admin),
    analytics_service: AnalyticsService = Depends(get_analytics_service)
):
    """Get comprehensive admin dashboard data."""
    try:
        overview = await analytics_service.get_admin_overview()
        return Response.success(data=overview)
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to fetch dashboard data: {str(e)}"
        )


@router.get("/admin/export/orders", dependencies=[Depends(require_admin)])
async def export_orders_admin(
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
    from services.commerce.orders import OrderService

    if format not in ['csv', 'excel', 'pdf']:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid format. Use csv, excel, or pdf"
        )

    try:
        order_service = OrderService(db)

        # Fetch all orders using pagination
        all_orders = []
        page = 1
        limit = 100

        while True:
            orders_data = await order_service.list_all(
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

            if len(orders_batch) < limit:
                break

            page += 1
        
        export_service = ExportService()
        
        if format == "csv":
            output = export_service.export_orders_to_csv(all_orders)
            media_type = "text/csv"
            filename = f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        elif format == "excel":
            output = export_service.export_orders_to_excel(all_orders)
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            filename = f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        else:  # pdf
            output = export_service.export_orders_to_pdf(all_orders)
            media_type = "application/pdf"
            filename = f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        return StreamingResponse(
            output,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise APIException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message=f"Failed to export orders: {str(e)}"
        )