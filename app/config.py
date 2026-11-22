import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"


class Settings:
    def __init__(self) -> None:
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.storage_dir = Path(os.getenv("STORAGE_DIR", ROOT_DIR / "storage")).resolve()
        self.data_ttl_seconds = int(float(os.getenv("DATA_TTL_HOURS", "6")) * 3600)
        self.max_upload_bytes = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
        self.vton_model = os.getenv("VTON_MODEL", "mock")
        self.shopee_affiliate_app_id = os.getenv("SHOPEE_AFFILIATE_APP_ID", "")
        self.shopee_affiliate_secret = os.getenv("SHOPEE_AFFILIATE_SECRET", "")


settings = Settings()
