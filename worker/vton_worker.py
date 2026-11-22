"""Worker chạy model: lấy job từ Redis, đọc ảnh trong storage, ghi kết quả.

Chạy: python -m worker.vton_worker
Mỗi tiến trình giữ 1 model trên 1 GPU. Muốn tăng thông lượng → chạy thêm tiến trình/GPU.
"""

import logging
import signal
import time

from PIL import Image
from redis import Redis
from redis.exceptions import RedisError

from app import queue, storage
from app.config import settings
from worker.models import TryOnModel, get_model

log = logging.getLogger("vton_worker")
_running = True


def _stop(*_):
    global _running
    _running = False
    log.info("Nhận tín hiệu dừng, sẽ thoát sau job hiện tại")


def process_job(r: Redis, model: TryOnModel, job_id: str) -> None:
    key = queue.job_key(job_id)
    if not r.exists(key):
        log.info("Bỏ qua job %s (đã hết hạn)", job_id)
        return

    r.hset(key, mapping={"status": queue.RUNNING, "updated_at": time.time()})
    try:
        d = storage.job_dir(job_id)
        with Image.open(d / storage.PERSON) as p, Image.open(d / storage.GARMENT) as g:
            person, garment = p.convert("RGB"), g.convert("RGB")
        category = r.hget(key, "category") or "upper"

        t0 = time.time()
        result = model.run(person, garment, category)
        storage.save_image(result.convert("RGB"), d / storage.RESULT)
        duration = round(time.time() - t0, 2)

        r.hset(key, mapping={"status": queue.DONE, "updated_at": time.time(), "duration": duration})
        log.info("Xong job %s trong %.2fs", job_id, duration)
    except Exception:
        log.exception("Job %s lỗi", job_id)
        r.hset(
            key,
            mapping={
                "status": queue.FAILED,
                "error": "Không xử lý được ảnh, vui lòng thử lại với ảnh khác.",
                "updated_at": time.time(),
            },
        )


def process_next(r: Redis, model: TryOnModel, timeout: int = 5) -> bool:
    item = r.blpop([queue.QUEUE_KEY], timeout=timeout)
    if not item:
        return False
    process_job(r, model, item[1])
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    r = Redis.from_url(settings.redis_url, decode_responses=True)
    model = get_model(settings.vton_model)
    log.info("Đang tải model '%s'...", model.name)
    model.load()
    log.info("Worker sẵn sàng, chờ job trên %s", queue.QUEUE_KEY)

    while _running:
        try:
            process_next(r, model)
        except RedisError:
            # Redis khởi động lại / mất mạng: chờ rồi thử lại thay vì để worker chết
            log.warning("Mất kết nối Redis, thử lại sau 3s", exc_info=log.isEnabledFor(logging.DEBUG))
            time.sleep(3)


if __name__ == "__main__":
    main()
