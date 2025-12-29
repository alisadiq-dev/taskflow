"""Redis client and utilities."""

from typing import Any, Optional
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import redis.asyncio as redis
from redis.asyncio import ConnectionPool, Redis

from taskflow.core.config import get_settings

settings = get_settings()

# Global connection pool
_pool: Optional[ConnectionPool] = None


async def get_redis_pool() -> ConnectionPool:
    """Get or create Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            str(settings.redis_url),
            max_connections=settings.redis_pool_size,
            decode_responses=settings.redis_decode_responses,
        )
    return _pool


async def get_redis() -> AsyncGenerator[Redis, None]:
    """
    Dependency that provides a Redis client.
    
    Usage:
        @app.get("/cache/{key}")
        async def get_cache(key: str, redis: Redis = Depends(get_redis)):
            return await redis.get(key)
    """
    pool = await get_redis_pool()
    client = Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.close()


@asynccontextmanager
async def get_redis_context() -> AsyncGenerator[Redis, None]:
    """Context manager for Redis connections."""
    pool = await get_redis_pool()
    client = Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.close()


async def close_redis() -> None:
    """Close Redis connection pool."""
    global _pool
    if _pool:
        await _pool.disconnect()
        _pool = None


class RedisCache:
    """
    Redis cache utility class.
    
    Provides simple caching operations with serialization.
    """
    
    def __init__(self, redis: Redis, prefix: str = "taskflow") -> None:
        self.redis = redis
        self.prefix = prefix
    
    def _key(self, key: str) -> str:
        """Generate prefixed key."""
        return f"{self.prefix}:{key}"
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        return await self.redis.get(self._key(key))
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set value in cache with optional TTL."""
        return await self.redis.set(
            self._key(key),
            value,
            ex=ttl,
        )
    
    async def delete(self, key: str) -> int:
        """Delete key from cache."""
        return await self.redis.delete(self._key(key))
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        return await self.redis.exists(self._key(key)) > 0
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """Increment value."""
        return await self.redis.incrby(self._key(key), amount)
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL on existing key."""
        return await self.redis.expire(self._key(key), ttl)
    
    async def ttl(self, key: str) -> int:
        """Get remaining TTL for key."""
        return await self.redis.ttl(self._key(key))


class RedisPubSub:
    """
    Redis Pub/Sub wrapper for real-time events.
    """
    
    def __init__(self, redis: Redis, channel_prefix: str = "taskflow") -> None:
        self.redis = redis
        self.channel_prefix = channel_prefix
        self._pubsub = None
    
    def _channel(self, channel: str) -> str:
        """Generate prefixed channel name."""
        return f"{self.channel_prefix}:{channel}"
    
    async def publish(self, channel: str, message: str) -> int:
        """Publish message to channel."""
        return await self.redis.publish(self._channel(channel), message)
    
    async def subscribe(self, *channels: str) -> None:
        """Subscribe to channels."""
        if self._pubsub is None:
            self._pubsub = self.redis.pubsub()
        
        prefixed = [self._channel(ch) for ch in channels]
        await self._pubsub.subscribe(*prefixed)
    
    async def unsubscribe(self, *channels: str) -> None:
        """Unsubscribe from channels."""
        if self._pubsub:
            prefixed = [self._channel(ch) for ch in channels]
            await self._pubsub.unsubscribe(*prefixed)
    
    async def listen(self) -> AsyncGenerator[dict, None]:
        """Listen for messages."""
        if self._pubsub:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    yield message
    
    async def close(self) -> None:
        """Close pubsub connection."""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
