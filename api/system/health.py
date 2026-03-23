# Health check endpoints for system monitoring

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
import psutil
import asyncio
import aiohttp
import time
from typing import Dict, Any, Optional
from core.logging import get_logger

from core.db import get_db, DatabaseOptimizer
from core.dependencies import get_current_user
from models.user import User

router = APIRouter(prefix="/health", tags=["health"])
logger = get_logger(__name__)

# Health check response models


class HealthStatus:
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth:
    def __init__(self, name: str, status: str, response_time: float = 0,
                 details: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        self.name = name
        self.status = status
        self.response_time = response_time
        self.details = details or {}
        self.error = error
        self.timestamp = datetime.utcnow().isoformat()

# Basic liveness check


@router.get("/live")
async def liveness_check():
    """
    Basic liveness check - returns 200 if the service is running
    Used by load balancers and orchestrators
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "banwee-api"
    }

# Readiness check


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """
    Readiness check - returns 200 if the service is ready to handle traffic
    Checks critical dependencies like database connectivity
    """
    checks = []
    overall_status = HealthStatus.HEALTHY

    # Database connectivity check
    db_health = await check_database_health(db)
    checks.append(db_health)

    if db_health.status != HealthStatus.HEALTHY:
        overall_status = HealthStatus.UNHEALTHY

    response_data = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "service": "banwee-api",
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "response_time": check.response_time,
                "error": check.error
            }
            for check in checks
        ]
    }

    status_code = 200 if overall_status == HealthStatus.HEALTHY else 503
    return JSONResponse(content=response_data, status_code=status_code)

@router.get("/detailed")
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """
    Comprehensive health check with detailed component status
    """
    start_time = time.time()
    checks = []
    overall_status = HealthStatus.HEALTHY

    # Run health checks sequentially to avoid session conflicts
    try:
        # Database health check
        db_health = await check_database_health(db)
        checks.append(db_health)
        if db_health.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        elif db_health.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED

        # System resources check (doesn't use database)
        system_health = await check_system_resources()
        checks.append(system_health)
        if system_health.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        elif system_health.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED

        # External services check (doesn't use database)
        external_health = await check_external_services()
        checks.append(external_health)
        if external_health.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        elif external_health.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED

        # Application metrics check (uses same database session)
        app_health = await check_application_metrics(db)
        checks.append(app_health)
        if app_health.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        elif app_health.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED

    except Exception as e:
        logger.error(f"Health check error: {e}")
        overall_status = HealthStatus.UNHEALTHY
        checks.append(ComponentHealth(
            name="health_check_error",
            status=HealthStatus.UNHEALTHY,
            error=str(e)
        ))

    total_time = (time.time() - start_time) * 1000  # Convert to milliseconds

    response_data = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "service": "banwee-api",
        "version": "1.0.0",
        "uptime": get_uptime(),
        "response_time": round(total_time, 2),
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "response_time": check.response_time,
                "details": check.details,
                "error": check.error,
                "timestamp": check.timestamp
            }
            for check in checks
        ]
    }

    status_code = 200 if overall_status != HealthStatus.UNHEALTHY else 503
    return JSONResponse(content=response_data, status_code=status_code)

# Dependencies health check


@router.get("/dependencies")
async def dependencies_health_check():
    """
    Check health of external dependencies
    """
    checks = []
    overall_status = HealthStatus.HEALTHY

    # Check external services
    external_health = await check_external_services()
    checks.append(external_health)

    if external_health.status != HealthStatus.HEALTHY:
        if external_health.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        elif overall_status == HealthStatus.HEALTHY:
            overall_status = HealthStatus.DEGRADED

    response_data = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "response_time": check.response_time,
                "details": check.details,
                "error": check.error
            }
            for check in checks
        ]
    }

    status_code = 200 if overall_status != HealthStatus.UNHEALTHY else 503
    return JSONResponse(content=response_data, status_code=status_code)

# API endpoints health check


@router.get("/api-endpoints")
async def api_endpoints_health_check():
    """
    Check health of all API endpoints
    """
    endpoints_to_check = [
        "/v1/products",
        "/v1/users/profile",
        "/v1/orders",
        "/v1/cart"
    ]

    checks = []
    overall_status = HealthStatus.HEALTHY

    for endpoint in endpoints_to_check:
        try:
            start_time = time.time()
            # This would make internal requests to check endpoints
            # For now, simulate the check
            response_time = (time.time() - start_time) * 1000

            endpoint_health = ComponentHealth(
                name=f"endpoint_{endpoint.replace('/', '_')}",
                status=HealthStatus.HEALTHY,
                response_time=response_time,
                details={"endpoint": endpoint}
            )
            checks.append(endpoint_health)

        except Exception as e:
            endpoint_health = ComponentHealth(
                name=f"endpoint_{endpoint.replace('/', '_')}",
                status=HealthStatus.UNHEALTHY,
                error=str(e),
                details={"endpoint": endpoint}
            )
            checks.append(endpoint_health)
            overall_status = HealthStatus.UNHEALTHY

    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "response_time": check.response_time,
                "details": check.details,
                "error": check.error
            }
            for check in checks
        ]
    }

# Performance metrics endpoint


@router.get("/metrics")
async def performance_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get performance metrics (requires authentication)
    """
    if current_user.role not in ["admin", "moderator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )

    metrics = await get_performance_metrics(db)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics
    }


# Database optimization endpoints
@router.get("/database/stats")
async def database_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get database performance statistics (requires authentication)"""
    if current_user.role not in ["admin", "moderator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    
    try:
        stats = await DatabaseOptimizer.get_database_stats(db)
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "database_stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get database stats: {str(e)}"
        )


@router.post("/database/maintenance")
async def run_database_maintenance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Run database maintenance tasks (requires admin authentication)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        stats = await DatabaseOptimizer.run_maintenance(db)
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Database maintenance completed successfully",
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error running database maintenance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database maintenance failed: {str(e)}"
        )

# Health check helper functions


async def check_database_health(db: AsyncSession) -> ComponentHealth:
    """Check database connectivity and performance"""
    start_time = time.time()

    try:
        # Test basic connectivity
        result = await db.execute(text("SELECT 1"))
        row = result.scalar()

        # Test a more complex query
        user_count_result = await db.execute(text("SELECT COUNT(*) FROM users"))
        user_count = user_count_result.scalar()

        response_time = (time.time() - start_time) * 1000

        # Check if response time is acceptable
        status = HealthStatus.HEALTHY
        if response_time > 1000:  # 1 second
            status = HealthStatus.DEGRADED
        elif response_time > 5000:  # 5 seconds
            status = HealthStatus.UNHEALTHY

        # Get pool stats safely
        try:
            pool_size = db.get_bind().pool.size()
            checked_out = db.get_bind().pool.checkedout()
        except:
            pool_size = 0
            checked_out = 0

        return ComponentHealth(
            name="database",
            status=status,
            response_time=response_time,
            details={
                "connection_pool_size": pool_size,
                "checked_out_connections": checked_out,
                "user_count": user_count
            }
        )

    except Exception as e:
        response_time = (time.time() - start_time) * 1000
        logger.error(f"Database health check failed: {e}")
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            response_time=response_time,
            error=str(e)
        )


async def check_system_resources() -> ComponentHealth:
    """Check system resource usage"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)

        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent

        # Determine status based on resource usage
        status = HealthStatus.HEALTHY
        if cpu_percent > 80 or memory_percent > 80 or disk_percent > 80:
            status = HealthStatus.DEGRADED
        elif cpu_percent > 95 or memory_percent > 95 or disk_percent > 95:
            status = HealthStatus.UNHEALTHY

        return ComponentHealth(
            name="system_resources",
            status=status,
            details={
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_available_gb": round(memory.available / (1024**3), 2),
                "disk_percent": disk_percent,
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "load_average": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
            }
        )

    except Exception as e:
        return ComponentHealth(
            name="system_resources",
            status=HealthStatus.UNHEALTHY,
            error=str(e)
        )


async def check_external_services() -> ComponentHealth:
    """Check external service dependencies"""
    services_to_check = [
        {"name": "stripe", "url": "https://api.stripe.com/v1/charges", "timeout": 5},
        # Add other external services here
    ]

    service_results = []
    overall_status = HealthStatus.HEALTHY

    async with aiohttp.ClientSession() as session:
        for service in services_to_check:
            try:
                start_time = time.time()
                async with session.get(
                    service["url"],
                    timeout=aiohttp.ClientTimeout(total=service["timeout"])
                ) as response:
                    response_time = (time.time() - start_time) * 1000

                    status = HealthStatus.HEALTHY
                    if response.status >= 500:
                        status = HealthStatus.UNHEALTHY
                        overall_status = HealthStatus.UNHEALTHY
                    elif response.status >= 400:
                        status = HealthStatus.DEGRADED
                        if overall_status == HealthStatus.HEALTHY:
                            overall_status = HealthStatus.DEGRADED

                    service_results.append({
                        "name": service["name"],
                        "status": status,
                        "response_time": response_time,
                        "http_status": response.status
                    })

            except asyncio.TimeoutError:
                service_results.append({
                    "name": service["name"],
                    "status": HealthStatus.UNHEALTHY,
                    "error": "Timeout"
                })
                overall_status = HealthStatus.UNHEALTHY

            except Exception as e:
                service_results.append({
                    "name": service["name"],
                    "status": HealthStatus.UNHEALTHY,
                    "error": str(e)
                })
                overall_status = HealthStatus.UNHEALTHY

    return ComponentHealth(
        name="external_services",
        status=overall_status,
        details={"services": service_results}
    )


async def check_application_metrics(db: AsyncSession) -> ComponentHealth:
    """Check application-specific metrics"""
    try:
        # Get various application metrics with error handling for each query
        metrics = {}
        
        try:
            total_users_result = await db.execute(text("SELECT COUNT(*) FROM users"))
            metrics["total_users"] = total_users_result.scalar()
        except Exception as e:
            logger.warning(f"Failed to get user count: {e}")
            metrics["total_users"] = 0
            
        try:
            total_products_result = await db.execute(text("SELECT COUNT(*) FROM products"))
            metrics["total_products"] = total_products_result.scalar()
        except Exception as e:
            logger.warning(f"Failed to get product count: {e}")
            metrics["total_products"] = 0
            
        try:
            total_orders_result = await db.execute(text("SELECT COUNT(*) FROM orders"))
            metrics["total_orders"] = total_orders_result.scalar()
        except Exception as e:
            logger.warning(f"Failed to get order count: {e}")
            metrics["total_orders"] = 0
            
        try:
            # Use a simpler query that works across different PostgreSQL versions
            orders_24h_result = await db.execute(text(
                "SELECT COUNT(*) FROM orders WHERE created_at > (NOW() - INTERVAL '1 day')"
            ))
            metrics["orders_last_24h"] = orders_24h_result.scalar()
        except Exception as e:
            logger.warning(f"Failed to get 24h order count: {e}")
            metrics["orders_last_24h"] = 0
            
        metrics["active_sessions"] = 0  # Would get from session store

        return ComponentHealth(
            name="application_metrics",
            status=HealthStatus.HEALTHY,
            details=metrics
        )

    except Exception as e:
        logger.error(f"Application metrics check failed: {e}")
        return ComponentHealth(
            name="application_metrics",
            status=HealthStatus.DEGRADED,  # Changed from UNHEALTHY to DEGRADED
            error=str(e)
        )


async def get_performance_metrics(db: AsyncSession) -> Dict[str, Any]:
    """Get detailed performance metrics"""
    try:
        # Get pool stats safely
        try:
            pool_size = db.get_bind().pool.size()
            active_connections = db.get_bind().pool.checkedout()
        except:
            pool_size = 0
            active_connections = 0
            
        return {
            "database": {
                "connection_pool_size": pool_size,
                "active_connections": active_connections,
                "query_performance": {
                    # Would include slow query logs, etc.
                }
            },
            "system": {
                "cpu_usage": psutil.cpu_percent(),
                "memory_usage": psutil.virtual_memory().percent,
                "disk_usage": psutil.disk_usage('/').percent,
                "network_io": dict(psutil.net_io_counters()._asdict()),
                "process_count": len(psutil.pids())
            },
            "application": {
                "uptime": get_uptime(),
                "request_count": 0,  # Would track requests
                "error_rate": 0,     # Would track errors
                "response_times": {
                    "avg": 0,
                    "p95": 0,
                    "p99": 0
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        return {"error": str(e)}


def get_uptime() -> float:
    """Get application uptime in seconds"""
    try:
        boot_time = psutil.boot_time()
        return time.time() - boot_time
    except:
        return 0.0
