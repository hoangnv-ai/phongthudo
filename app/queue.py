"""Hàng đợi job đơn giản trên Redis, dùng chung giữa API (async) và worker (sync).

- vton:queue        LIST các job_id đang chờ (API RPUSH, worker BLPOP)
- vton:job:<id>     HASH trạng thái job: status, category, error, created_at, ...
"""

import time

from redis.asyncio import Redis

from app.config import settings

QUEUE_KEY = "vton:queue"

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"


def job_key(job_id: str) -> str:
    return f"vton:job:{job_id}"


async def enqueue(r: Redis, job_id: str, fields: dict) -> None:
    now = time.time()
    key = job_key(job_id)
    async with r.pipeline(transaction=True) as p:
        p.hset(key, mapping={**fields, "status": QUEUED, "created_at": now, "updated_at": now})
        p.expire(key, settings.data_ttl_seconds)
        p.rpush(QUEUE_KEY, job_id)
        await p.execute()


async def get_job(r: Redis, job_id: str) -> dict | None:
    data = await r.hgetall(job_key(job_id))
    if not data:
        return None
    data["position"] = None
    if data.get("status") == QUEUED:
        pos = await r.lpos(QUEUE_KEY, job_id)
        data["position"] = pos + 1 if pos is not None else None
    return data
