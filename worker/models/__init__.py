from worker.models.base import TryOnModel
from worker.models.catvton import CatVTONTryOn
from worker.models.mock import MockTryOn

REGISTRY: dict[str, type[TryOnModel]] = {
    "mock": MockTryOn,
    "catvton": CatVTONTryOn,
}


def get_model(name: str) -> TryOnModel:
    try:
        return REGISTRY[name]()
    except KeyError:
        raise ValueError(f"Model không tồn tại: {name}. Có: {', '.join(REGISTRY)}") from None
