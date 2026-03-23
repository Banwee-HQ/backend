"""
Security Configuration
Centralized security settings and rate limits
"""

from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class RateLimitConfig:
    """Rate limit configuration for different endpoints"""
    
    # Authentication endpoints (per minute)
    AUTH_LOGIN = 5           # Login attempts
    AUTH_REGISTER = 3        # Registration attempts  
    AUTH_PASSWORD_RESET = 3  # Password reset requests
    AUTH_EMAIL_VERIFY = 5    # Email verification attempts
    
    # E-commerce endpoints (per minute)
    CART_OPERATIONS = 120     # Cart add/update/remove (increased for polling)
    CHECKOUT = 5             # Checkout attempts
    COUPON_VALIDATION = 20   # Coupon code attempts
    
    # General API endpoints (per minute)
    API_GENERAL = 300        # General API calls (increased for polling)
    SEARCH = 60              # Search requests
    UPLOAD = 20              # File uploads
    
    # Security thresholds
    COUPON_ABUSE_DAILY = 3   # Max coupon attempts per day
    COUPON_ABUSE_RAPID = 2   # Max coupon attempts per 5 minutes
    CHECKOUT_ABUSE = 5       # Max checkout attempts per 10 minutes
    PRICE_TAMPERING = 3      # Max price tampering attempts per hour
    
    # Block durations (minutes)
    IP_BLOCK_DURATION = 30   # IP block duration for violations
    RATE_LIMIT_BLOCK = 15    # Rate limit violation block


@dataclass
class SecurityConfig:
    """Security configuration settings"""
    
    # Price tampering detection
    PRICE_TOLERANCE = 0.01   # Allowed price difference (cents)
    
    # Suspicious activity tracking
    TRACK_DURATION_HOURS = 24  # How long to track activities
    
    # Account suspension thresholds
    SUSPEND_AFTER_VIOLATIONS = 3  # Suspend after N violations
    
    # Security monitoring
    LOG_SECURITY_EVENTS = True
    ALERT_ON_TAMPERING = True
    
    # Fail-safe settings
    FAIL_OPEN_ON_ERROR = True  # Allow requests if security check fails


class SecuritySettings:
    """Centralized security settings"""
    
    RATE_LIMITS = RateLimitConfig()
    SECURITY = SecurityConfig()
    
    # Endpoint categorization for rate limiting
    ENDPOINT_CATEGORIES = {
        # Authentication
        "/auth/login": "auth_login",
        "/auth/register": "auth_register", 
        "/auth/forgot-password": "auth_password_reset",
        "/auth/reset-password": "auth_password_reset",
        "/auth/verify-email": "auth_email_verify",
        
        # Cart operations
        "/cart/add": "cart_operations",
        "/cart/update": "cart_operations", 
        "/cart/remove": "cart_operations",
        "/cart/clear": "cart_operations",
        "/cart/promocode": "coupon_validation",
        
        # Checkout
        "/orders/checkout": "checkout",
        "/orders/": "checkout",
        
        # Inventory and stock endpoints
        "/inventory/check-stock": "api_general",
        "/inventory/check-stock/bulk": "api_general",
        
        # Address and payment endpoints  
        "/auth/addresses": "api_general",
        "/payments/methods": "api_general",
        
        # General
        "/search": "search",
        "/upload": "upload",
    }
    
    # Security-sensitive endpoints requiring additional protection
    SECURITY_ENDPOINTS = {
        "price_sensitive": [
            "/orders/checkout",
            "/cart/add", 
            "/cart/update"
        ],
        "coupon_validation": [
            "/cart/promocode"
        ],
        "checkout": [
            "/orders/checkout",
            "/orders/"
        ]
    }
    
    @classmethod
    def get_rate_limit(cls, endpoint_category: str) -> int:
        """Get rate limit for endpoint category"""
        rate_limits = {
            "auth_login": cls.RATE_LIMITS.AUTH_LOGIN,
            "auth_register": cls.RATE_LIMITS.AUTH_REGISTER,
            "auth_password_reset": cls.RATE_LIMITS.AUTH_PASSWORD_RESET,
            "auth_email_verify": cls.RATE_LIMITS.AUTH_EMAIL_VERIFY,
            "cart_operations": cls.RATE_LIMITS.CART_OPERATIONS,
            "checkout": cls.RATE_LIMITS.CHECKOUT,
            "coupon_validation": cls.RATE_LIMITS.COUPON_VALIDATION,
            "search": cls.RATE_LIMITS.SEARCH,
            "upload": cls.RATE_LIMITS.UPLOAD,
            "api_general": cls.RATE_LIMITS.API_GENERAL,
        }
        return rate_limits.get(endpoint_category, cls.RATE_LIMITS.API_GENERAL)
    
    @classmethod
    def get_endpoint_category(cls, path: str) -> str:
        """Get endpoint category for rate limiting"""
        for endpoint_prefix, category in cls.ENDPOINT_CATEGORIES.items():
            if path.startswith(endpoint_prefix):
                return category
        return "api_general"
    
    @classmethod
    def is_security_endpoint(cls, path: str, security_type: str) -> bool:
        """Check if endpoint requires specific security protection"""
        endpoints = cls.SECURITY_ENDPOINTS.get(security_type, [])
        return any(path.startswith(endpoint) for endpoint in endpoints)


# Export settings instance
security_settings = SecuritySettings()