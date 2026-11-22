"""Model giả: dán ảnh sản phẩm lên vùng thân người. Dùng để chạy thử luồng end-to-end khi chưa có GPU."""

import time

from PIL import Image, ImageDraw

from worker.models.base import TryOnModel

# (top, width) theo tỉ lệ chiều cao / chiều rộng ảnh người
_BOXES = {
    "upper": (0.20, 0.42),
    "lower": (0.48, 0.36),
    "dress": (0.20, 0.46),
}


class MockTryOn(TryOnModel):
    name = "mock"

    def __init__(self, delay: float = 2.0) -> None:
        self.delay = delay

    def run(self, person: Image.Image, garment: Image.Image, category: str) -> Image.Image:
        time.sleep(self.delay)  # giả lập thời gian chạy model
        out = person.convert("RGB").copy()
        W, H = out.size
        top, width = _BOXES.get(category, _BOXES["upper"])

        g = garment.convert("RGB")
        tw = max(1, int(W * width))
        th = max(1, int(g.height * tw / g.width))
        g = g.resize((tw, th), Image.Resampling.LANCZOS)
        mask = g.convert("L").point(lambda v: 0 if v > 235 else 230)  # bỏ nền trắng
        out.paste(g, ((W - tw) // 2, int(H * top)), mask)

        draw = ImageDraw.Draw(out)
        draw.rectangle((0, H - 28, W, H), fill=(242, 201, 76))
        draw.text((10, H - 22), "MOCK RESULT - model that chua duoc ket noi", fill=(20, 20, 20))
        return out
