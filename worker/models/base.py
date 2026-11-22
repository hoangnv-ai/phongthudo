from abc import ABC, abstractmethod

from PIL import Image


class TryOnModel(ABC):
    """Giao diện chung cho mọi model thử đồ. Worker chỉ biết tới lớp này."""

    name: str = "base"

    def load(self) -> None:
        """Tải trọng số lên GPU. Gọi một lần khi worker khởi động."""

    @abstractmethod
    def run(self, person: Image.Image, garment: Image.Image, category: str) -> Image.Image:
        """person, garment: ảnh RGB. category: upper | lower | dress. Trả về ảnh RGB."""
