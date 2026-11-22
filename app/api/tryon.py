import asyncio

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from redis.asyncio import Redis

from app import queue, storage
from app.config import settings
from app.scrapers.common import FetchError, fetch_image

router = APIRouter(tags=["tryon"])

CATEGORIES = {"upper", "lower", "dress"}


def _redis(request: Request) -> Redis:
    return request.app.state.redis


async def _read_upload(f: UploadFile) -> bytes:
    data = await f.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"Ảnh quá lớn (tối đa {settings.max_upload_bytes // 2**20}MB)")
    if not data:
        raise HTTPException(422, "File ảnh rỗng")
    return data


@router.post("/tryon", status_code=202)
async def create_tryon(
    request: Request,
    person: UploadFile = File(..., description="Ảnh toàn thân"),
    garment: UploadFile | None = File(None, description="Ảnh sản phẩm (nếu tự tải lên)"),
    garment_url: str | None = Form(None, description="URL ảnh sản phẩm lấy từ /product/resolve"),
    category: str = Form("upper"),
):
    if category not in CATEGORIES:
        raise HTTPException(422, "Loại đồ không hợp lệ")
    if garment is None and not garment_url:
        raise HTTPException(422, "Thiếu ảnh sản phẩm")

    person_bytes = await _read_upload(person)
    if garment is not None:
        garment_bytes = await _read_upload(garment)
    else:
        try:
            garment_bytes = await fetch_image(garment_url, settings.max_upload_bytes)
        except FetchError as e:
            raise HTTPException(422, str(e)) from e

    try:
        person_img = await asyncio.to_thread(storage.normalize_image, person_bytes)
        garment_img = await asyncio.to_thread(storage.normalize_image, garment_bytes)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    job_id = storage.new_job_id()
    d = storage.job_dir(job_id)
    await asyncio.to_thread(storage.save_image, person_img, d / storage.PERSON)
    await asyncio.to_thread(storage.save_image, garment_img, d / storage.GARMENT)
    await queue.enqueue(_redis(request), job_id, {"category": category})
    return {"job_id": job_id, "status": queue.QUEUED}


@router.get("/jobs/{job_id}")
async def get_job(request: Request, job_id: str):
    job = await queue.get_job(_redis(request), job_id) if storage.is_valid_job_id(job_id) else None
    if not job:
        raise HTTPException(404, "Không tìm thấy yêu cầu (có thể đã hết hạn)")
    return {
        "job_id": job_id,
        "status": job["status"],
        "position": job["position"],
        "error": job.get("error"),
        "result_url": f"/api/jobs/{job_id}/result" if job["status"] == queue.DONE else None,
    }


@router.get("/jobs/{job_id}/result")
async def get_result(job_id: str):
    if not storage.is_valid_job_id(job_id):
        raise HTTPException(404)
    path = storage.job_dir(job_id) / storage.RESULT
    if not path.exists():
        raise HTTPException(404, "Chưa có kết quả")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
