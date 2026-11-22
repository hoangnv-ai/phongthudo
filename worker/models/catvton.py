"""CatVTON: https://github.com/Zheng-Chong/CatVTON

CatVTON không phải package pip, cần clone mã nguồn:
    git clone https://github.com/Zheng-Chong/CatVTON third_party/CatVTON
    uv pip install --python .venv/bin/python -r third_party/CatVTON/requirements.txt
rồi đặt VTON_MODEL=catvton (và CATVTON_SRC nếu clone chỗ khác).

Cách gọi dưới đây viết theo app.py của repo CatVTON, CHƯA chạy kiểm chứng ở đây.
Nếu repo đổi tên hàm/tham số, đối chiếu lại với app.py của họ.
"""

import logging
import os
import sys
from pathlib import Path

from PIL import Image

from app.config import ROOT_DIR
from worker.models.base import TryOnModel

log = logging.getLogger(__name__)

CATVTON_SRC = Path(os.getenv("CATVTON_SRC", ROOT_DIR / "third_party" / "CatVTON"))
BASE_CKPT = os.getenv("CATVTON_BASE_CKPT", "booksforcharlie/stable-diffusion-inpainting")
ATTN_REPO = os.getenv("CATVTON_ATTN_REPO", "zhengchong/CatVTON")
STEPS = int(os.getenv("CATVTON_STEPS", "30"))      # 50 = đẹp hơn, chậm hơn
GUIDANCE = float(os.getenv("CATVTON_GUIDANCE", "2.5"))
WIDTH, HEIGHT = 768, 1024

# category của app → cloth_type của CatVTON
_CLOTH_TYPE = {"upper": "upper", "lower": "lower", "dress": "overall"}


class CatVTONTryOn(TryOnModel):
    name = "catvton"

    def load(self) -> None:
        if not CATVTON_SRC.exists():
            raise RuntimeError(f"Không thấy mã nguồn CatVTON ở {CATVTON_SRC} (xem docstring)")
        sys.path.insert(0, str(CATVTON_SRC))

        import torch
        from diffusers.image_processor import VaeImageProcessor
        from huggingface_hub import snapshot_download
        from model.cloth_masker import AutoMasker
        from model.pipeline import CatVTONPipeline
        from utils import resize_and_crop, resize_and_padding

        if not torch.cuda.is_available():
            raise RuntimeError("CatVTON cần GPU CUDA")

        self._torch = torch
        self._resize_and_crop = resize_and_crop
        self._resize_and_padding = resize_and_padding

        repo_path = snapshot_download(repo_id=ATTN_REPO)  # tải 1 lần, lần sau lấy từ cache HF
        self.pipeline = CatVTONPipeline(
            base_ckpt=BASE_CKPT,
            attn_ckpt=repo_path,
            attn_ckpt_version="mix",
            weight_dtype=torch.float16,
            use_tf32=True,
            device="cuda",
        )
        self.automasker = AutoMasker(
            densepose_ckpt=os.path.join(repo_path, "DensePose"),
            schp_ckpt=os.path.join(repo_path, "SCHP"),
            device="cuda",
        )
        self.mask_processor = VaeImageProcessor(
            vae_scale_factor=8, do_normalize=False, do_binarize=True, do_convert_grayscale=True
        )
        self._warmup()

    def _warmup(self) -> None:
        """Chạy 1 lần với ảnh trắng để job đầu tiên của người dùng không bị chậm."""
        log.info("Warmup CatVTON...")
        blank = Image.new("RGB", (WIDTH, HEIGHT), "white")
        mask = Image.new("L", (WIDTH, HEIGHT), 255)
        with self._torch.inference_mode():
            self.pipeline(image=blank, condition_image=blank, mask=mask,
                          num_inference_steps=2, guidance_scale=GUIDANCE)

    def run(self, person: Image.Image, garment: Image.Image, category: str) -> Image.Image:
        person = self._resize_and_crop(person, (WIDTH, HEIGHT))
        garment = self._resize_and_padding(garment, (WIDTH, HEIGHT))

        mask = self.automasker(person, _CLOTH_TYPE.get(category, "upper"))["mask"]
        mask = self.mask_processor.blur(mask, blur_factor=9)

        generator = self._torch.Generator(device="cuda").manual_seed(42)
        with self._torch.inference_mode():
            result = self.pipeline(
                image=person,
                condition_image=garment,
                mask=mask,
                num_inference_steps=STEPS,
                guidance_scale=GUIDANCE,
                generator=generator,
            )[0]
        self._torch.cuda.empty_cache()
        return result
