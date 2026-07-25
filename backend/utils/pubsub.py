import json
import logging
from datetime import date, datetime
from typing import Any

import redis.asyncio as aioredis

from core.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def _json_default(obj: Any) -> Any:
    """JSON serializer fallback — converts datetime/date to ISO strings."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Close shared Async Redis connection on shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("Closed Redis client connection")


async def publish_job_update(job_id: int, data: dict[str, Any]) -> None:
    """Publish a job update to the per-job channel so SSE can deliver it
    only to the user who owns that job.

    Channel name: ``resume_job:{job_id}``
    """
    redis = await get_redis()
    # Strip None values and serialise — datetime fields are converted to ISO strings
    payload = {k: v for k, v in {"job_id": job_id, **data}.items() if v is not None}
    channel = f"resume_job:{job_id}"
    try:
        await redis.publish(channel, json.dumps(payload, default=_json_default))
        logger.debug("Published job update on %s: %s", channel, payload)
    except Exception as e:
        logger.error("Failed to publish job update for job %s: %s", job_id, e)
