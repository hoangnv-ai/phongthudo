"""Lưu ảnh của từng job trên đĩa (thư mục dùng chung giữa API và worker).

storage/jobs/<job_id>/person.jpg   ảnh toàn thân
storage/jobs/<job_id>/garment.jpg  ảnh sản phẩm
storage/jobs/<job_id>/result.jpg   kết quả do worker ghi
"""

import asyncio
import io
import logging
import re
import shutil
import time
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings

log = logging.getLogger(__name__)

MAX_SIDE = 1536
Image.MAX_IMAGE_PIXELS = 40_000_000  # chặn ảnh "bom giải nén"
_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")

PERSON = "person.jpg"
GARMENT = "garment.jpg"
RESULT = "result.jpg"


def jobs_root() -> Path:
    return settings.storage_dir / "jobs"


def new_job_id() -> str:
    return uuid.uuid4().hex


def is_valid_job_id(job_id: str) -> bool:
    return bool(_JOB_ID_RE.match(job_id))


def job_dir(job_id: str) -> Path:
    if not is_valid_job_id(job_id):
        raise ValueError("job_id không hợp lệ")
    return jobs_root() / job_id


def normalize_image(data: bytes) -> Image.Image:
    """Mở ảnh, xoay theo EXIF, chuyển RGB (nền trắng nếu có alpha), giới hạn kích thước."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise ValueError("File không phải ảnh hợp lệ") from e

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A"))
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    return img


def save_image(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    img.save(tmp, "JPEG", quality=92)
    tmp.replace(path)  # ghi nguyên tử để không ai đọc phải file dở


def cleanup_expired(now: float | None = None) -> int:
    root = jobs_root()
    if not root.exists():
        return 0
    cutoff = (now or time.time()) - settings.data_ttl_seconds
    removed = 0
    for d in root.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed


async def cleanup_loop(interval: int = 600) -> None:
    while True:
        try:
            n = await asyncio.to_thread(cleanup_expired)
            if n:
                log.info("Đã xoá %d job hết hạn", n)
        except Exception:
            log.exception("Lỗi khi dọn storage")
        await asyncio.sleep(interval)
