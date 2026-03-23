# Redis removed — stub kept for import compatibility only
class RedisManager:
    async def get_client(self): return None
    async def close(self): pass

class RedisService:
    async def _get_redis(self): return None

class RedisKeyManager:
    CART_PREFIX = "cart"
    RATE_LIMIT_PREFIX = "rate_limit"
    SECURITY_PREFIX = "security"
    PRODUCT_CACHE_PREFIX = "product"
    INVENTORY_LOCK_PREFIX = "inventory_lock"
    USER_CACHE_PREFIX = "user"

    @staticmethod
    def cart_key(user_id: str) -> str: return f"cart:{user_id}"
    @staticmethod
    def rate_limit_key(identifier: str, endpoint: str) -> str: return f"rate_limit:{identifier}:{endpoint}"
    @staticmethod
    def security_key(key_suffix: str) -> str: return f"security:{key_suffix}"
    @staticmethod
    def product_cache_key(product_id: str) -> str: return f"product:{product_id}"
    @staticmethod
    def inventory_lock_key(variant_id: str) -> str: return f"inventory_lock:{variant_id}"
    @staticmethod
    def user_cache_key(user_id: str) -> str: return f"user:{user_id}"

redis_manager = RedisManager()

async def get_redis():
    return None
