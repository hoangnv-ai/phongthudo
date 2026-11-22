"""Đọc link TikTok Shop → product_id.

Link TikTok không chứa sẵn mã ảnh như Shopee. Muốn lấy ảnh một cách chính thống cần
TikTok Shop Affiliate / Partner API (chưa tích hợp). Hiện tại trả product_id và yêu cầu
người dùng tải ảnh sản phẩm lên.
"""

import re
from urllib.parse import parse_qs, urlparse

from app.scrapers.common import ProductInfo, expand_short_link, host_matches

TIKTOK_HOSTS = ("tiktok.com",)
SHORT_HOSTS = ("vt.tiktok.com", "vm.tiktok.com")
_PRODUCT_RE = re.compile(r"/product/(\d+)")


def is_tiktok_host(host: str | None) -> bool:
    return host_matches(host, TIKTOK_HOSTS)


def parse_tiktok_url(url: str) -> dict:
    u = urlparse(url)
    if not is_tiktok_host(u.hostname):
        raise ValueError("Không phải link TikTok")
    product_id = None
    if m := _PRODUCT_RE.search(u.path):
        product_id = m.group(1)
    else:
        q = parse_qs(u.query)
        for key in ("product_id", "productId"):
            if q.get(key) and q[key][0].isdigit():
                product_id = q[key][0]
                break
    return {"product_id": product_id}


async def resolve_tiktok(url: str) -> ProductInfo:
    if (urlparse(url).hostname or "").lower() in SHORT_HOSTS:
        url = await expand_short_link(url, TIKTOK_HOSTS)
    p = parse_tiktok_url(url)
    if not p["product_id"]:
        raise ValueError("Link TikTok này không phải trang sản phẩm TikTok Shop")
    # TODO: gọi TikTok Shop Affiliate API để lấy ảnh khi có quyền truy cập.
    return ProductInfo(source="tiktok", product_id=p["product_id"])
