"""Redis connection pool."""

from redis.asyncio import Redis, from_url


async def create_redis(redis_url: str) -> Redis:
    return from_url(redis_url, decode_responses=True)
