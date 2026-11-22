"""Đọc link Shopee VN → shop_id, item_id, ảnh sản phẩm.

Thứ tự:
1. Link rút gọn (s.shopee.vn, shp.ee) → đi theo redirect để lấy link đầy đủ.
2. Tách link: shop_id, item_id, image_ids (link chia sẻ từ app thường có sẵn image_ids).
3. image_ids → URL ảnh trên CDN, không cần gọi Shopee.
4. Có cấu hình Affiliate Open API → lấy thêm ảnh chính + tên + link affiliate.
"""

import logging
import re
from urllib.parse import parse_qs, unquote, urlparse

from app.scrapers import shopee_affiliate
from app.scrapers.common import ProductInfo, expand_short_link, host_matches

log = logging.getLogger(__name__)

CDN_URL = "https://down-vn.img.susercontent.com/file/{}"
SHOPEE_HOSTS = ("shopee.vn",)
SHORT_HOSTS = ("s.shopee.vn", "shp.ee", "shope.ee")

_ID_PATTERNS = [
    re.compile(r"-i\.(\d+)\.(\d+)"),        # /ten-san-pham-i.SHOP.ITEM
    re.compile(r"/product/(\d+)/(\d+)"),    # /product/SHOP/ITEM
    re.compile(r"^/[^/]+/(\d+)/(\d+)"),     # /ten-shop/SHOP/ITEM
]
_IMAGE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,}$")


def is_shopee_host(host: str | None) -> bool:
    return host_matches(host, SHOPEE_HOSTS) or host_matches(host, SHORT_HOSTS)


def is_short_link(host: str | None) -> bool:
    return (host or "").lower() in SHORT_HOSTS


def image_url(image_id: str) -> str:
    return CDN_URL.format(image_id)


def parse_shopee_url(url: str) -> dict:
    """Tách link Shopee đầy đủ (không gọi mạng)."""
    u = urlparse(url)
    if not host_matches(u.hostname, SHOPEE_HOSTS):
        raise ValueError("Không phải link Shopee VN")

    path = unquote(u.path)
    shop_id = item_id = None
    for pattern in _ID_PATTERNS:
        if m := pattern.search(path):
            shop_id, item_id = m.groups()
            break

    q = parse_qs(u.query)
    image_ids: list[str] = []
    for raw in q.get("image_ids", []):
        for i in raw.split(","):
            i = i.strip()
            if _IMAGE_ID_RE.match(i) and i not in image_ids:
                image_ids.append(i)

    title = None
    if m := re.match(r"^/(.+)-i\.\d+\.\d+$", path):
        title = re.sub(r"\s+", " ", m.group(1).replace("-", " ")).strip() or None

    return {
        "shop_id": shop_id,
        "item_id": item_id,
        "image_ids": image_ids,
        "title": title,
    }


async def resolve_shopee(url: str) -> ProductInfo:
    if is_short_link(urlparse(url).hostname):
        url = await expand_short_link(url, SHORT_HOSTS + SHOPEE_HOSTS)

    p = parse_shopee_url(url)
    if not p["item_id"] and not p["image_ids"]:
        raise ValueError("Link Shopee không chứa mã sản phẩm")

    info = ProductInfo(
        source="shopee",
        product_id=f"{p['shop_id']}.{p['item_id']}" if p["item_id"] else None,
        title=p["title"],
        images=[image_url(i) for i in p["image_ids"]],
    )

    if p["item_id"] and shopee_affiliate.is_configured():
        try:
            offer = await shopee_affiliate.get_product(p["shop_id"], p["item_id"])
        except Exception:
            log.exception("Shopee Affiliate API lỗi")
            offer = None
        if offer:
            if offer.get("imageUrl") and offer["imageUrl"] not in info.images:
                info.images.append(offer["imageUrl"])
            info.title = offer.get("productName") or info.title
            info.offer_link = offer.get("offerLink")

    return info
