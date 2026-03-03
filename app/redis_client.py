"""Redis connection manager."""
import redis.asyncio as redis
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

_redis_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis | None:
    """Get a Redis connection. Returns None if Redis is unavailable."""
    global _redis_pool
    if _redis_pool is None:
        try:
            settings = get_settings()
            _redis_pool = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await _redis_pool.ping()
        except Exception as e:
            logger.warning("redis_unavailable", error=str(e))
            _redis_pool = None
            return None
    return _redis_pool


async def close_redis():
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
