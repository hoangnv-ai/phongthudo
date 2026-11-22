import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from app import storage
from app.api import product, tryon
from app.config import STATIC_DIR, settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.jobs_root().mkdir(parents=True, exist_ok=True)
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    cleaner = asyncio.create_task(storage.cleanup_loop())
    yield
    cleaner.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await cleaner
    await app.state.redis.aclose()


app = FastAPI(title="Phòng thử đồ", lifespan=lifespan)
app.include_router(product.router, prefix="/api")
app.include_router(tryon.router, prefix="/api")


@app.get("/api/health")
async def health():
    redis_ok = True
    try:
        await app.state.redis.ping()
    except Exception:
        redis_ok = False
    return {"ok": redis_ok, "redis": redis_ok}


# Đặt cuối cùng: mọi đường dẫn không phải /api/* trả về giao diện tĩnh
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
