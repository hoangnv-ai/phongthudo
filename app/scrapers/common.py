import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = "PhongThuDo/0.1 (+link-resolver)"
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Chỉ tải ảnh từ CDN của các sàn (tránh SSRF: không cho server gọi URL tuỳ ý)
IMAGE_HOST_SUFFIXES = (
    "susercontent.com",   # Shopee CDN
    "shopee.vn",
    "tiktokcdn.com",
    "tiktokcdn-us.com",
    "ibyteimg.com",
)


class FetchError(Exception):
    """Lỗi có thông điệp hiển thị được cho người dùng."""


@dataclass
class ProductInfo:
    source: str
    product_id: str | None = None
    title: str | None = None
    images: list[str] = field(default_factory=list)
    offer_link: str | None = None


def extract_url(text: str) -> str | None:
    """Người dùng hay dán cả câu 'Xem sản phẩm này trên Shopee: https://...'."""
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(".,;)") if m else None


def host_matches(host: str | None, suffixes: tuple[str, ...]) -> bool:
    host = (host or "").lower()
    return any(host == s or host.endswith("." + s) for s in suffixes)


async def expand_short_link(url: str, allowed_suffixes: tuple[str, ...], max_hops: int = 5) -> str:
    """Đi theo redirect của link rút gọn, chỉ trong các domain cho phép, không tải nội dung trang."""
    async with httpx.AsyncClient(
        follow_redirects=False, timeout=5, headers={"User-Agent": USER_AGENT}
    ) as client:
        for _ in range(max_hops):
            if not host_matches(urlparse(url).hostname, allowed_suffixes):
                raise FetchError("Link chuyển hướng tới trang không được hỗ trợ")
            async with client.stream("GET", url) as r:
                if not r.is_redirect:
                    return url
                url = urljoin(url, r.headers["location"])
    raise FetchError("Link chuyển hướng quá nhiều lần")


async def fetch_image(url: str, max_bytes: int) -> bytes:
    u = urlparse(url)
    if u.scheme != "https" or not host_matches(u.hostname, IMAGE_HOST_SUFFIXES):
        raise FetchError("Nguồn ảnh không được hỗ trợ")
    try:
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=10, headers={"User-Agent": USER_AGENT}
        ) as client:
            async with client.stream("GET", url) as r:
                if r.status_code != 200:
                    raise FetchError("Không tải được ảnh sản phẩm")
                if not r.headers.get("content-type", "").startswith("image/"):
                    raise FetchError("Link ảnh không trả về ảnh")
                buf = bytearray()
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    if len(buf) > max_bytes:
                        raise FetchError("Ảnh sản phẩm quá lớn")
                return bytes(buf)
    except httpx.HTTPError as e:
        raise FetchError("Không tải được ảnh sản phẩm") from e
