import logging
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.scrapers import shopee, tiktok
from app.scrapers.common import FetchError, ProductInfo, extract_url

log = logging.getLogger(__name__)
router = APIRouter(tags=["product"])

UPLOAD_HINT = "Không lấy được ảnh từ link này, hãy tải ảnh sản phẩm lên."


class ResolveRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4000)


class ResolveResponse(BaseModel):
    source: str | None = None
    product_id: str | None = None
    title: str | None = None
    images: list[str] = []
    offer_link: str | None = None
    needs_upload: bool
    message: str | None = None


@router.post("/product/resolve", response_model=ResolveResponse)
async def resolve_product(req: ResolveRequest) -> ResolveResponse:
    url = extract_url(req.url)
    if not url:
        raise HTTPException(422, "Không tìm thấy link trong nội dung đã dán")

    host = urlparse(url).hostname
    if shopee.is_shopee_host(host):
        resolver, source = shopee.resolve_shopee, "shopee"
    elif tiktok.is_tiktok_host(host):
        resolver, source = tiktok.resolve_tiktok, "tiktok"
    else:
        raise HTTPException(422, "Hiện chỉ hỗ trợ link Shopee và TikTok Shop")

    try:
        info: ProductInfo = await resolver(url)
    except (ValueError, FetchError) as e:
        return ResolveResponse(source=source, needs_upload=True, message=f"{e}. {UPLOAD_HINT}")
    except httpx.HTTPError:
        log.warning("Không mở được link %s", url, exc_info=True)
        return ResolveResponse(source=source, needs_upload=True, message=UPLOAD_HINT)

    return ResolveResponse(
        source=info.source,
        product_id=info.product_id,
        title=info.title,
        images=info.images,
        offer_link=info.offer_link,
        needs_upload=not info.images,
        message=None if info.images else UPLOAD_HINT,
    )
