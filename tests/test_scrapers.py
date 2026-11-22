import pytest

from app.scrapers.common import extract_url, host_matches
from app.scrapers.shopee import image_url, is_shopee_host, parse_shopee_url
from app.scrapers.tiktok import parse_tiktok_url

SHARE_LINK = (
    "https://shopee.vn/-Deal-M%E1%BB%9F-B%C3%A1n-%C3%81o-Thun-Nam-N%E1%BB%AF-In-H%C3%ACnh-Form-Oversize-"
    "Cotton100-250GSM-M%C3%A1t-Th%E1%BA%A5m-H%C3%BAt.-DT840-i.949645377.48608132750"
    "?extraParams=%7B%22display_model_id%22%3A375721217756%2C%22model_selection_logic%22%3A3%7D"
    "&image_ids=vn-11134207-81ztc-mmk4xeaosnwo06"
)


def test_shopee_share_link():
    p = parse_shopee_url(SHARE_LINK)
    assert p["shop_id"] == "949645377"
    assert p["item_id"] == "48608132750"
    assert p["image_ids"] == ["vn-11134207-81ztc-mmk4xeaosnwo06"]
    assert p["title"].startswith("Deal Mở Bán Áo Thun")
    assert image_url(p["image_ids"][0]) == (
        "https://down-vn.img.susercontent.com/file/vn-11134207-81ztc-mmk4xeaosnwo06"
    )


@pytest.mark.parametrize(
    "url, shop, item",
    [
        ("https://shopee.vn/product/123/456", "123", "456"),
        ("https://shopee.vn/some-shop/123/456", "123", "456"),
        ("https://shopee.vn/Ao-thun-i.123.456?sp_atk=x", "123", "456"),
    ],
)
def test_shopee_url_formats(url, shop, item):
    p = parse_shopee_url(url)
    assert (p["shop_id"], p["item_id"]) == (shop, item)
    assert p["image_ids"] == []


def test_shopee_rejects_other_hosts():
    with pytest.raises(ValueError):
        parse_shopee_url("https://evilshopee.vn/product/1/2")


def test_image_ids_are_sanitized():
    p = parse_shopee_url("https://shopee.vn/product/1/2?image_ids=../../etc,abc,vn-11134207-ok12345678")
    assert p["image_ids"] == ["vn-11134207-ok12345678"]


def test_extract_url_from_share_text():
    text = "Xem sản phẩm này trên Shopee: https://s.shopee.vn/AbC123xyz."
    assert extract_url(text) == "https://s.shopee.vn/AbC123xyz"
    assert extract_url("không có link") is None


def test_host_matches():
    assert host_matches("down-vn.img.susercontent.com", ("susercontent.com",))
    assert not host_matches("susercontent.com.evil.io", ("susercontent.com",))
    assert is_shopee_host("s.shopee.vn") and is_shopee_host("shopee.vn")


def test_tiktok_product_link():
    assert parse_tiktok_url("https://shop.tiktok.com/view/product/1729384756?region=VN")["product_id"] == "1729384756"
    assert parse_tiktok_url("https://www.tiktok.com/@abc/video/123")["product_id"] is None
