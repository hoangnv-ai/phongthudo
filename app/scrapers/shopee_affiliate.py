"""Shopee Affiliate Open API (GraphQL), cách chính thống để lấy thông tin sản phẩm.

Đăng ký tại https://affiliate.shopee.vn để có AppID + Secret.
LƯU Ý: endpoint, cách ký và tên trường dưới đây viết theo tài liệu Open API công khai,
CHƯA được kiểm chứng với tài khoản thật. Hãy đối chiếu tài liệu trong trang affiliate trước khi dùng.

Ký request: Authorization: SHA256 Credential={AppId}, Timestamp={ts}, Signature={sha256(AppId+ts+payload+Secret)}
"""

import hashlib
import json
import time

import httpx

from app.config import settings

ENDPOINT = "https://open-api.affiliate.shopee.vn/graphql"


def is_configured() -> bool:
    return bool(settings.shopee_affiliate_app_id and settings.shopee_affiliate_secret)


def _sign(payload: str, ts: int) -> str:
    app_id = settings.shopee_affiliate_app_id
    raw = f"{app_id}{ts}{payload}{settings.shopee_affiliate_secret}"
    sig = hashlib.sha256(raw.encode()).hexdigest()
    return f"SHA256 Credential={app_id}, Timestamp={ts}, Signature={sig}"


async def get_product(shop_id: str | None, item_id: str) -> dict | None:
    """Trả về {productName, imageUrl, offerLink} hoặc None."""
    args = f"itemId:{int(item_id)}"
    if shop_id:
        args += f",shopId:{int(shop_id)}"
    query = "{productOfferV2(%s){nodes{productName imageUrl offerLink}}}" % args
    payload = json.dumps({"query": query}, separators=(",", ":"))
    ts = int(time.time())

    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.post(
            ENDPOINT,
            content=payload,
            headers={"Content-Type": "application/json", "Authorization": _sign(payload, ts)},
        )
        r.raise_for_status()
        data = r.json()

    nodes = (((data or {}).get("data") or {}).get("productOfferV2") or {}).get("nodes") or []
    return nodes[0] if nodes else None
