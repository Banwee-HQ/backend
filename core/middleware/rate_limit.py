"""
Rate Limiting Middleware with Redis Integration and Security Features
Implements rate limiting, coupon abuse detection, price tampering protection, and security monitoring
"""
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import json
import hashlib
from core.cache import RedisService, RedisKeyManager
from core.config import settings
from core.utils.response import Response as APIResponse
from core.auth.config import security_settings
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)

class SecurityService(RedisService):
    """Security service for abuse detection and protection"""
    
    def __init__(self):
        super().__init__()
    
    async def detect_coupon_abuse(self, identifier: str, coupon_code: str) -> Dict[str, any]:
        """Detect coupon abuse patterns"""
        try:
            redis_client = await self._get_redis()
            current_time = datetime.utcnow().timestamp()
            
            # Track coupon usage per user/IP
            coupon_key = RedisKeyManager.security_key(f"coupon_abuse:{identifier}:{coupon_code}")
            
            # Get usage count in last 24 hours
            day_ago = current_time - 86400
            await redis_client.zremrangebyscore(coupon_key, 0, day_ago)
            usage_count = await redis_client.zcard(coupon_key)
            
            # Check for abuse (more than 3 attempts per coupon per day)
            if usage_count >= 3:
                return {
                    "blocked": True,
                    "reason": "coupon_abuse_daily_limit",
                    "message": "Too many coupon attempts today. Please try again tomorrow."
                }
            
            # Check rapid attempts (more than 2 in 5 minutes)
            five_minutes_ago = current_time - 300
            recent_attempts = await redis_client.zcount(coupon_key, five_minutes_ago, current_time)
            if recent_attempts >= 2:
                return {
                    "blocked": True,
                    "reason": "coupon_abuse_rate_limit",
                    "message": "Please wait before trying another coupon."
                }
            
            # Record this attempt
            await redis_client.zadd(coupon_key, {str(current_time): current_time})
            await redis_client.expire(coupon_key, 86400)  # 24 hours
            
            return {"blocked": False}
            
        except Exception as e:
            logger.error(f"Error checking coupon abuse for {identifier}: {e}")
            return {"blocked": False}  # Fail open
    
    async def detect_price_tampering(self, identifier: str, submitted_prices: Dict, actual_prices: Dict) -> Dict[str, any]:
        """Detect price tampering attempts"""
        try:
            tampering_detected = False
            tampered_items = []
            
            for item_id, submitted_price in submitted_prices.items():
                actual_price = actual_prices.get(item_id)
                if actual_price is None:
                    continue
                
                # Allow small floating point differences (0.01)
                price_diff = abs(float(submitted_price) - float(actual_price))
                if price_diff > 0.01:
                    tampering_detected = True
                    tampered_items.append({
                        'item_id': item_id,
                        'submitted_price': submitted_price,
                        'actual_price': actual_price,
                        'difference': price_diff
                    })
            
            if tampering_detected:
                # Log and track tampering attempts
                redis_client = await self._get_redis()
                current_time = datetime.utcnow().timestamp()
                
                tampering_key = RedisKeyManager.security_key(f"price_tampering:{identifier}")
                await redis_client.zadd(tampering_key, {str(current_time): current_time})
                await redis_client.expire(tampering_key, 3600)  # 1 hour
                
                # Check for repeated tampering (3+ attempts in 1 hour = suspend)
                hour_ago = current_time - 3600
                await redis_client.zremrangebyscore(tampering_key, 0, hour_ago)
                attempt_count = await redis_client.zcard(tampering_key)
                
                logger.error(f"Price tampering detected from {identifier}: {tampered_items}")
                
                if attempt_count >= 3:
                    return {
                        "blocked": True,
                        "reason": "account_suspended",
                        "message": "Account temporarily suspended due to suspicious activity.",
                        "tampered_items": tampered_items
                    }
                
                return {
                    "blocked": True,
                    "reason": "price_validation_failed",
                    "message": "Price validation failed. Please refresh and try again.",
                    "tampered_items": tampered_items
                }
            
            return {"blocked": False}
            
        except Exception as e:
            logger.error(f"Error checking price tampering for {identifier}: {e}")
            return {"blocked": False}  # Fail open
    
    async def detect_checkout_abuse(self, identifier: str) -> Dict[str, any]:
        """Detect checkout abuse patterns"""
        try:
            redis_client = await self._get_redis()
            current_time = datetime.utcnow().timestamp()
            
            checkout_key = RedisKeyManager.security_key(f"checkout_abuse:{identifier}")
            
            # Remove attempts older than 10 minutes
            ten_minutes_ago = current_time - 600
            await redis_client.zremrangebyscore(checkout_key, 0, ten_minutes_ago)
            
            # Count recent attempts
            attempt_count = await redis_client.zcard(checkout_key)
            
            # Block if more than 5 checkout attempts in 10 minutes
            if attempt_count >= 5:
                logger.warning(f"Checkout abuse detected from {identifier}")
                return {
                    "blocked": True,
                    "reason": "checkout_abuse",
                    "message": "Too many checkout attempts. Please wait before trying again."
                }
            
            # Record this attempt
            await redis_client.zadd(checkout_key, {str(current_time): current_time})
            await redis_client.expire(checkout_key, 600)  # 10 minutes
            
            return {"blocked": False}
            
        except Exception as e:
            logger.error(f"Error checking checkout abuse for {identifier}: {e}")
            return {"blocked": False}  # Fail open
    
    async def track_suspicious_activity(self, identifier: str, activity_type: str, details: Dict = None):
        """Track suspicious activities for monitoring"""
        try:
            redis_client = await self._get_redis()
            current_time = datetime.utcnow().timestamp()
            
            activity_key = RedisKeyManager.security_key(f"suspicious:{activity_type}:{identifier}")
            activity_data = {
                "timestamp": current_time,
                "details": details or {}
            }
            
            await redis_client.zadd(activity_key, {json.dumps(activity_data): current_time})
            await redis_client.expire(activity_key, 86400)  # 24 hours
            
        except Exception as e:
            logger.error(f"Error tracking suspicious activity: {e}")


class RateLimitService(RedisService):
    """Redis-based rate limiting service using sliding window algorithm"""
    
    def __init__(self):
        super().__init__()
        
        # Default rate limits (requests per minute) - now using security config
        self.default_limits = {
            "auth_login": security_settings.RATE_LIMITS.AUTH_LOGIN,
            "auth_register": security_settings.RATE_LIMITS.AUTH_REGISTER,
            "auth_password_reset": security_settings.RATE_LIMITS.AUTH_PASSWORD_RESET,
            "auth_email_verify": security_settings.RATE_LIMITS.AUTH_EMAIL_VERIFY,
            "cart_operations": security_settings.RATE_LIMITS.CART_OPERATIONS,
            "checkout": security_settings.RATE_LIMITS.CHECKOUT,
            "coupon_validation": security_settings.RATE_LIMITS.COUPON_VALIDATION,
            "search": security_settings.RATE_LIMITS.SEARCH,
            "upload": security_settings.RATE_LIMITS.UPLOAD,
            "api_general": security_settings.RATE_LIMITS.API_GENERAL,
        }
    
    async def check_rate_limit(
        self, 
        identifier: str, 
        endpoint_type: str = "api",
        custom_limit: Optional[int] = None,
        window_seconds: int = 60
    ) -> Dict[str, any]:
        """Check if request is within rate limit using sliding window"""
        try:
            limit = custom_limit or self.default_limits.get(endpoint_type, self.default_limits["api_general"])
            rate_limit_key = RedisKeyManager.rate_limit_key(identifier, endpoint_type)
            
            redis_client = await self._get_redis()
            current_time = datetime.utcnow().timestamp()
            window_start = current_time - window_seconds
            
            # Use Redis sorted set for sliding window
            # Remove old entries outside the window
            await redis_client.zremrangebyscore(rate_limit_key, 0, window_start)
            
            # Count current requests in window
            current_count = await redis_client.zcard(rate_limit_key)
            
            if current_count >= limit:
                # Rate limit exceeded
                oldest_requests = await redis_client.zrange(rate_limit_key, 0, 0, withscores=True)
                reset_time = int(oldest_requests[0][1] + window_seconds) if oldest_requests else int(current_time + window_seconds)
                
                return {
                    "allowed": False,
                    "limit": limit,
                    "remaining": 0,
                    "reset_time": reset_time,
                    "retry_after": reset_time - int(current_time)
                }
            
            # Add current request to the window
            await redis_client.zadd(rate_limit_key, {str(current_time): current_time})
            
            # Set expiry for the key (cleanup)
            await redis_client.expire(rate_limit_key, window_seconds + 10)
            
            remaining = limit - current_count - 1
            reset_time = int(current_time + window_seconds)
            
            return {
                "allowed": True,
                "limit": limit,
                "remaining": remaining,
                "reset_time": reset_time,
                "retry_after": 0
            }
            
        except Exception as e:
            logger.error(f"Error checking rate limit for {identifier}: {e}", exc_info=True)
            # On error, allow the request (fail open)
            return {
                "allowed": True,
                "limit": self.default_limits.get(endpoint_type, 100),
                "remaining": 99,
                "reset_time": int(datetime.utcnow().timestamp() + 60),
                "retry_after": 0,
                "error": str(e)
            }

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware for rate limiting and security protection
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.rate_limit_service = RateLimitService()
        self.security_service = SecurityService()
        
        # Define endpoint types for different rate limits - using security config
        self.endpoint_types = security_settings.ENDPOINT_CATEGORIES
        
        # Security-sensitive endpoints
        self.security_endpoints = security_settings.SECURITY_ENDPOINTS
    
    def _get_client_identifier(self, request: Request) -> str:
        """Get client identifier for tracking"""
        # Try user ID first
        if hasattr(request.state, "user_id") and request.state.user_id:
            return f"user:{request.state.user_id}"
        
        # Fall back to IP + User-Agent hash for anonymous users
        ip = self._get_client_ip(request)
        user_agent = request.headers.get('user-agent', '')
        client_hash = hashlib.md5(f"{ip}:{user_agent}".encode()).hexdigest()[:12]
        return f"client:{client_hash}"
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP"""
        # Check for forwarded headers
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else 'unknown'
    
    async def _check_security_violations(self, request: Request, identifier: str) -> Optional[JSONResponse]:
        """Check for various security violations"""
        path = request.url.path
        
        # Check coupon abuse for coupon-related endpoints
        if any(path.startswith(endpoint) for endpoint in self.security_endpoints["coupon_validation"]):
            try:
                if request.method == "POST":
                    body = await request.body()
                    if body:
                        request._body = body  # Store for later use
                        data = json.loads(body.decode())
                        coupon_code = data.get('code') or data.get('coupon_code')
                        
                        if coupon_code:
                            abuse_result = await self.security_service.detect_coupon_abuse(identifier, coupon_code)
                            if abuse_result.get("blocked"):
                                return JSONResponse(
                                    status_code=429,
                                    content={
                                        "success": False,
                                        "message": abuse_result["message"],
                                        "errors": [abuse_result["reason"].upper()]
                                    }
                                )
            except Exception as e:
                logger.error(f"Error checking coupon abuse: {e}")
        
        # Check checkout abuse
        if any(path.startswith(endpoint) for endpoint in self.security_endpoints["checkout"]):
            if request.method == "POST":
                abuse_result = await self.security_service.detect_checkout_abuse(identifier)
                if abuse_result.get("blocked"):
                    return JSONResponse(
                        status_code=429,
                                            content={
                                                "success": False,
                                                "message": abuse_result["message"],
                                                "errors": [abuse_result["reason"].upper()]
                                            }                    )
        
        return None
    
    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting and security checks"""
        
        # Skip for health checks and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Get client identifier
        identifier = self._get_client_identifier(request)
        
        # Check security violations first
        security_response = await self._check_security_violations(request, identifier)
        if security_response:
            return security_response
        
        # Determine endpoint type for rate limiting
        endpoint_type = security_settings.get_endpoint_category(request.url.path)
        
        # Check rate limit
        try:
            rate_limit_result = await self.rate_limit_service.check_rate_limit(
                identifier=identifier,
                endpoint_type=endpoint_type
            )
            
            if not rate_limit_result.get("allowed", True):
                # Track rate limit violation
                await self.security_service.track_suspicious_activity(
                    identifier, 
                    "rate_limit_violation",
                    {"endpoint": request.url.path, "endpoint_type": endpoint_type}
                )
                
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "message": f"Rate limit exceeded. Try again in {rate_limit_result.get('retry_after', 60)} seconds.",
                        "errors": ["RATE_LIMIT_EXCEEDED"],
                        "data": {
                            "limit": rate_limit_result.get("limit"),
                            "reset_time": rate_limit_result.get("reset_time"),
                            "details": {
                                "limit": rate_limit_result.get("limit"),
                                "reset_time": rate_limit_result.get("reset_time")
                            }
                        }
                    },
                    headers={
                        "X-RateLimit-Limit": str(rate_limit_result.get("limit", 100)),
                        "X-RateLimit-Remaining": str(rate_limit_result.get("remaining", 0)),
                        "X-RateLimit-Reset": str(rate_limit_result.get("reset_time", 0)),
                        "Retry-After": str(rate_limit_result.get("retry_after", 60))
                    }
                )
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers to response
            response.headers["X-RateLimit-Limit"] = str(rate_limit_result.get("limit", 100))
            response.headers["X-RateLimit-Remaining"] = str(rate_limit_result.get("remaining", 99))
            response.headers["X-RateLimit-Reset"] = str(rate_limit_result.get("reset_time", 0))
            
            return response
            
        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            # On error in rate limiting, return a generic 500 error
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "Internal server error during rate limiting.",
                    "errors": [f"Rate limiting internal error: {e}"]
                }
            )