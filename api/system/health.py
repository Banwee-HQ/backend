# Health check endpoints for system monitoring

from fastapi import APIRouter
from datetime import datetime


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/")
async def liveness_check():
    """
    Basic liveness check - returns 200 if the service is running
    Used by load balancers and orchestrators
    """
    return {
        "status": "alive",
        "timestamp": datetime.now().isoformat(),
        "service": "banwee-api"
    }
