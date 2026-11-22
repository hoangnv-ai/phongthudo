"""Luồng end-to-end: upload → job vào hàng đợi → worker (mock) xử lý → lấy kết quả."""

import io

import fakeredis
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.main import app
from worker.models.mock import MockTryOn
from worker.vton_worker import process_next


def _jpeg(color, size=(300, 600)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    server = fakeredis.FakeServer()
    with TestClient(app) as client:
        app.state.redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
        yield client, fakeredis.FakeRedis(server=server, decode_responses=True)


def test_tryon_end_to_end(env):
    client, sync_redis = env
    res = client.post(
        "/api/tryon",
        files={"person": ("p.jpg", _jpeg("blue"), "image/jpeg"), "garment": ("g.jpg", _jpeg("red", (200, 200)), "image/jpeg")},
        data={"category": "upper"},
    )
    assert res.status_code == 202, res.text
    job_id = res.json()["job_id"]

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "queued" and job["position"] == 1

    assert process_next(sync_redis, MockTryOn(delay=0), timeout=1)

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "done"
    img = client.get(job["result_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"


def test_rejects_non_image(env):
    client, _ = env
    res = client.post(
        "/api/tryon",
        files={"person": ("p.jpg", b"not an image", "image/jpeg"), "garment": ("g.jpg", _jpeg("red"), "image/jpeg")},
    )
    assert res.status_code == 422


def test_rejects_untrusted_garment_url(env):
    client, _ = env
    res = client.post(
        "/api/tryon",
        files={"person": ("p.jpg", _jpeg("blue"), "image/jpeg")},
        data={"garment_url": "http://169.254.169.254/latest/meta-data"},
    )
    assert res.status_code == 422


def test_unknown_job(env):
    client, _ = env
    assert client.get("/api/jobs/../../etc").status_code == 404
    assert client.get("/api/jobs/" + "0" * 32).status_code == 404


def test_resolve_shopee_link(env):
    client, _ = env
    from tests.test_scrapers import SHARE_LINK

    data = client.post("/api/product/resolve", json={"url": f"Xem nè {SHARE_LINK}"}).json()
    assert data["source"] == "shopee"
    assert data["product_id"] == "949645377.48608132750"
    assert data["images"] == ["https://down-vn.img.susercontent.com/file/vn-11134207-81ztc-mmk4xeaosnwo06"]
    assert data["needs_upload"] is False


def test_resolve_unsupported(env):
    client, _ = env
    assert client.post("/api/product/resolve", json={"url": "https://lazada.vn/x"}).status_code == 422
