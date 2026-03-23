"""
Redis Configuration and Connection Management
Implements Redis best practices for e-commerce MVP
"""
import redis.asyncio as redis
import json
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timedelta
from core.config import settings
import pickle
import hashlib
from uuid import UUID
from core.logging import get_structured_logger

logger = get_structured_logger(__name__)

class RedisManager:
    """
    Redis connection manager with connection pooling and best practices
    """
    
    def __init__(self):
        self._pool = None
        self._client = None
    
    async def get_client(self) -> redis.Redis:
        """Get Redis client with connection pooling"""
        if self._client is None:
            self._pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=20,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            self._client = redis.Redis(connection_pool=self._pool)
        return self._client
    
    async def close(self):
        """Close Redis connections"""
        if self._client:
            await self._client.close()
        if self._pool:
            await self._pool.disconnect()

# Global Redis manager instance
redis_manager = RedisManager()

async def get_redis() -> redis.Redis:
    """Get Redis client instance"""
    return await redis_manager.get_client()

class RedisService:
    """
    Base Redis service with common operations and best practices
    """
    
    def __init__(self):
        self.redis = None
    
    async def _get_redis(self) -> redis.Redis:
        """Get Redis client"""
        if self.redis is None:
            self.redis = await get_redis()
        return self.redis
    
    def _serialize_data(self, data: Any) -> str:
        """Serialize data for Redis storage"""
        def json_default(o):
            if isinstance(o, UUID):
                return str(o)
            if isinstance(o, datetime):
                return o.isoformat()
            raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

        if isinstance(data, (dict, list)):
            return json.dumps(data, default=json_default)
        elif isinstance(data, (int, float, str, bool)):
            return str(data)
        elif isinstance(data, UUID):
            return str(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        else:
            # For any other complex, non-JSON-serializable objects, fall back to pickle
            logger.warning(f"Serializing complex object with pickle: {type(data)}")
            return pickle.dumps(data).hex()
    
    def _deserialize_data(self, data: str, data_type: str = "json") -> Any:
        """Deserialize data from Redis"""
        if not data:
            return None
        
        try:
            if data_type == "json":
                # Attempt to parse JSON
                parsed_data = json.loads(data)
                
                # Recursively convert UUID strings back to UUID objects in dicts/lists
                return self._convert_uuids_in_data(parsed_data)
            elif data_type == "pickle":
                return pickle.loads(bytes.fromhex(data))
            else:
                return data
        except json.JSONDecodeError:
            # If JSON decoding fails, it might be a simple string (e.g., a direct UUID string)
            # Or it might be a pickled item that wasn't marked as such
            try:
                # Try to convert to UUID if it's a UUID string
                return UUID(data)
            except ValueError:
                return data
        except ValueError as e: # For bytes.fromhex errors etc.
            logger.error(f"Failed to deserialize Redis data: {e}")
            return None

    def _convert_uuids_in_data(self, data: Any) -> Any:
        """Helper to recursively convert UUID strings to UUID objects"""
        if isinstance(data, dict):
            return {k: self._convert_uuids_in_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._convert_uuids_in_data(elem) for elem in data]
        elif isinstance(data, str):
            try:
                # Attempt to convert string to UUID object
                return UUID(data)
            except ValueError:
                return data
        return data
    
    async def set_with_expiry(
        self, 
        key: str, 
        value: Any, 
        expiry_seconds: int = 3600,
        data_type: str = "json"
    ) -> bool:
        """Set key with expiry time"""
        try:
            redis_client = await self._get_redis()
            serialized_value = self._serialize_data(value)
            return await redis_client.setex(key, expiry_seconds, serialized_value)
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            return False
    
    async def get_data(self, key: str, data_type: str = "json") -> Any:
        """Get data from Redis"""
        try:
            redis_client = await self._get_redis()
            data = await redis_client.get(key)
            if data:
                return self._deserialize_data(data.decode('utf-8'), data_type)
            return None
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None
    
    async def delete_key(self, key: str) -> bool:
        """Delete key from Redis"""
        try:
            redis_client = await self._get_redis()
            return bool(await redis_client.delete(key))
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis"""
        try:
            redis_client = await self._get_redis()
            return bool(await redis_client.exists(key))
        except Exception as e:
            logger.error(f"Redis EXISTS error for key {key}: {e}")
            return False
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter in Redis"""
        try:
            redis_client = await self._get_redis()
            return await redis_client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis INCR error for key {key}: {e}")
            return 0
    
    async def set_hash(self, key: str, mapping: Dict[str, Any], expiry_seconds: Optional[int] = None) -> bool:
        """Set hash in Redis"""
        try:
            redis_client = await self._get_redis()
            # Serialize all values in the mapping
            serialized_mapping = {k: self._serialize_data(v) for k, v in mapping.items()}
            result = await redis_client.hset(key, mapping=serialized_mapping)
            
            if expiry_seconds:
                await redis_client.expire(key, expiry_seconds)
            
            return bool(result)
        except Exception as e:
            logger.error(f"Redis HSET error for key {key}: {e}")
            return False
    
    async def get_hash(self, key: str) -> Optional[Dict[str, Any]]:
        """Get hash from Redis"""
        try:
            redis_client = await self._get_redis()
            data = await redis_client.hgetall(key)
            if data:
                # Deserialize all values
                return {k.decode('utf-8'): self._deserialize_data(v.decode('utf-8')) 
                       for k, v in data.items()}
            return None
        except Exception as e:
            logger.error(f"Redis HGETALL error for key {key}: {e}")
            return None
    
    async def get_hash_field(self, key: str, field: str) -> Any:
        """Get specific field from hash"""
        try:
            redis_client = await self._get_redis()
            data = await redis_client.hget(key, field)
            if data:
                return self._deserialize_data(data.decode('utf-8'))
            return None
        except Exception as e:
            logger.error(f"Redis HGET error for key {key}, field {field}: {e}")
            return None
    
    async def set_list(self, key: str, items: List[Any], expiry_seconds: Optional[int] = None) -> bool:
        """Set list in Redis"""
        try:
            redis_client = await self._get_redis()
            # Clear existing list and add new items
            await redis_client.delete(key)
            if items:
                serialized_items = [self._serialize_data(item) for item in items]
                await redis_client.lpush(key, *serialized_items)
            
            if expiry_seconds:
                await redis_client.expire(key, expiry_seconds)
            
            return True
        except Exception as e:
            logger.error(f"Redis LIST SET error for key {key}: {e}")
            return False
    
    async def get_list(self, key: str) -> List[Any]:
        """Get list from Redis"""
        try:
            redis_client = await self._get_redis()
            data = await redis_client.lrange(key, 0, -1)
            if data:
                return [self._deserialize_data(item.decode('utf-8')) for item in data]
            return []
        except Exception as e:
            logger.error(f"Redis LIST GET error for key {key}: {e}")
            return []

class RedisKeyManager:
    """
    Centralized Redis key management with consistent naming conventions
    """
    
    # Key prefixes for different data types
    CART_PREFIX = "cart"
    RATE_LIMIT_PREFIX = "rate_limit"
    SECURITY_PREFIX = "security"
    PRODUCT_CACHE_PREFIX = "product"
    INVENTORY_LOCK_PREFIX = "inventory_lock"
    USER_CACHE_PREFIX = "user"
    
    @staticmethod
    def cart_key(user_id: str) -> str:
        """Generate cart key for user"""
        return f"{RedisKeyManager.CART_PREFIX}:{user_id}"
    
    @staticmethod
    def rate_limit_key(identifier: str, endpoint: str) -> str:
        """Generate rate limit key"""
        return f"{RedisKeyManager.RATE_LIMIT_PREFIX}:{identifier}:{endpoint}"
    
    @staticmethod
    def security_key(key_suffix: str) -> str:
        """Generate security-related key"""
        return f"{RedisKeyManager.SECURITY_PREFIX}:{key_suffix}"
    
    @staticmethod
    def product_cache_key(product_id: str) -> str:
        """Generate product cache key"""
        return f"{RedisKeyManager.PRODUCT_CACHE_PREFIX}:{product_id}"
    
    @staticmethod
    def product_list_cache_key(filters_hash: str) -> str:
        """Generate product list cache key based on filters"""
        return f"{RedisKeyManager.PRODUCT_CACHE_PREFIX}:list:{filters_hash}"
    
    @staticmethod
    def inventory_lock_key(variant_id: str) -> str:
        """Generate inventory lock key"""
        return f"{RedisKeyManager.INVENTORY_LOCK_PREFIX}:{variant_id}"
    
    @staticmethod
    def user_cache_key(user_id: str) -> str:
        """Generate user cache key"""
        return f"{RedisKeyManager.USER_CACHE_PREFIX}:{user_id}"
    
    @staticmethod
    def generate_filters_hash(filters: Dict[str, Any]) -> str:
        """Generate consistent hash for filter combinations"""
        # Sort filters for consistent hashing
        sorted_filters = json.dumps(filters, sort_keys=True)
        return hashlib.md5(sorted_filters.encode()).hexdigest()[:16]