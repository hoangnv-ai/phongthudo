"""CatVTON cho worker.

Khác với khung cũ ở ba điểm, và cả ba đều là thứ chỉ phát hiện được khi chạy thật:

1. **Repo GitHub đã chết.** `git clone https://github.com/Zheng-Chong/CatVTON` trả về 404
   (kiểm cùng lúc với `pytorch/pytorch` -> 200 từ cùng máy, nên là repo mất chứ không phải mạng
   chặn). Nguồn mã còn sống duy nhất là HF Space `zhengchong/CatVTON`, và ta tải nó bằng
   `snapshot_download(repo_type="space")` -- một lần, rồi nằm trong cache HF.

2. **Ghim revision, không dùng `main`.** Một Space có thể bị sửa bất cứ lúc nào; nếu baseline đổi
   giữa hai lần chạy mà không ai biết thì nó không còn là baseline. Nâng `CATVTON_SPACE_REV` một
   cách có chủ đích, không bao giờ để "lấy bản mới nhất".

3. **`AutoMasker` cần detectron2.** `model/DensePose/__init__.py` của họ import
   `detectron2.config` / `detectron2.engine`. detectron2 KHÔNG có trên PyPI và KHÔNG nằm trong
   requirements.txt của Space, nên `Dockerfile.gpu` phải tự build nó. Không có detectron2 thì
   không có mask, và không có mask thì không chạy được trên ảnh người dùng thô.
   Lỗi ở đây được bắt và diễn giải lại, vì `ModuleNotFoundError: detectron2` không gợi ý gì cho
   người đọc log lúc 2 giờ sáng.

Chưa chạy được đầu-cuối ở máy phát triển: cần GPU CUDA. Phần nạp mã, ghim revision và thông điệp
lỗi đã kiểm; phần suy luận thì chưa.
"""

import logging
import os
import sys
from pathlib import Path

from PIL import Image

from worker.models.base import TryOnModel

log = logging.getLogger(__name__)

# Chuỗi nguồn, thử theo thứ tự. Repo GitHub đã chết một lần rồi, nên không phụ thuộc vào đúng
# một nguồn nữa.
#   1. Mirror của chính mình (đặt CATVTON_SPACE), nếu đã sao lưu. Giấy phép CatVTON là
#      cc-by-nc-sa-4.0 nên sao lưu và phân phối lại ĐƯỢC PHÉP, miễn ghi công và giữ nguyên giấy
#      phép cho bản phái sinh.
#   2. Space gốc của tác giả.
#   3. Hai Space của người khác dùng lại cùng mã. Model repo liệt kê hơn 100 Space như vậy, nên
#      khả năng tất cả cùng biến mất là rất thấp. Chúng là mã của NGƯỜI KHÁC chép lại, nên chỉ
#      dùng khi hai nguồn trên hỏng, và log sẽ nói rõ đang lấy từ đâu.
SPACE_FALLBACKS = [
    "zhengchong/CatVTON",
    "multimodalart/CatVTON-zerogpu",
    "Nymbo/CatVTON",
]
SPACE = os.getenv("CATVTON_SPACE", "")          # mirror riêng, thử trước mọi nguồn khác
# Revision của Space gốc, đọc từ header redirect của HF lúc tích hợp (24/11/2026). Chỉ áp dụng cho
# `zhengchong/CatVTON`: một Space khác có lịch sử commit khác, nên ghim revision của nguồn này vào
# nguồn kia sẽ hỏng. Nguồn dự phòng lấy `main` và log cảnh báo là nó KHÔNG được ghim.
SPACE_REV = os.getenv("CATVTON_SPACE_REV", "24a6952918a8c6168b89ae32ad61e7e447e3987b")
WEIGHTS_REPO = os.getenv("CATVTON_WEIGHTS_REPO", "zhengchong/CatVTON")
BASE_CKPT = os.getenv("CATVTON_BASE_CKPT", "booksforcharlie/stable-diffusion-inpainting")
STEPS = int(os.getenv("CATVTON_STEPS", "30"))        # 50 = như paper, đẹp hơn và chậm hơn
GUIDANCE = float(os.getenv("CATVTON_GUIDANCE", "2.5"))
SEED = int(os.getenv("CATVTON_SEED", "42"))
WIDTH, HEIGHT = 768, 1024

# category của app -> cloth_type của CatVTON. 'overall' xoá cả thân lẫn chân, là thứ một chiếc váy
# liền cần; đưa váy vào mask 'upper' sẽ để lại chân váy cũ trong ảnh.
_CLOTH_TYPE = {"upper": "upper", "lower": "lower", "dress": "overall"}


class CatVTONTryOn(TryOnModel):
    name = "catvton"

    def load(self) -> None:
        # Import có diễn giải: image CPU (Dockerfile) cố tình KHÔNG cài torch, nên đặt
        # VTON_MODEL=catvton ở đó sẽ ném "No module named 'torch'" -- đúng về kỹ thuật và vô dụng
        # với người đọc log. Nói thẳng ra nguyên nhân và cách sửa.
        try:
            import torch
            from huggingface_hub import snapshot_download
        except ModuleNotFoundError as e:
            raise RuntimeError(
                f"Thiếu {e.name!r}: worker này build từ Dockerfile (image CPU, không có phụ thuộc "
                "model). CatVTON cần image GPU -- đổi `dockerfile: Dockerfile.gpu` cho service "
                "worker trong docker-compose.yml và bật khối deploy GPU. Chỉ muốn thử luồng thì "
                "đặt VTON_MODEL=mock."
            ) from e

        if not torch.cuda.is_available():
            raise RuntimeError(
                "CatVTON cần GPU CUDA. Worker này đang chạy trên CPU; dùng VTON_MODEL=mock để "
                "thử luồng, hoặc build worker bằng Dockerfile.gpu và bật khối deploy GPU."
            )

        src = self._fetch_code(snapshot_download)
        if src not in sys.path:
            sys.path.insert(0, src)

        try:
            from model.cloth_masker import AutoMasker
            from model.pipeline import CatVTONPipeline
            from utils import resize_and_crop, resize_and_padding
        except ModuleNotFoundError as e:
            if (e.name or "").startswith("detectron2"):
                raise RuntimeError(
                    "Thiếu detectron2, mà AutoMasker của CatVTON import nó trực tiếp. "
                    "detectron2 không có trên PyPI: build từ nguồn trong Dockerfile.gpu "
                    "(pip install 'git+https://github.com/facebookresearch/detectron2.git'). "
                    "Không có nó thì không dựng được mask từ ảnh người dùng."
                ) from e
            raise

        self._torch = torch
        self._crop, self._pad = resize_and_crop, resize_and_padding

        from diffusers.image_processor import VaeImageProcessor

        log.info("Tải trọng số từ %s", WEIGHTS_REPO)
        ckpt = snapshot_download(repo_id=WEIGHTS_REPO)
        self.pipeline = CatVTONPipeline(
            base_ckpt=BASE_CKPT,
            attn_ckpt=ckpt,
            attn_ckpt_version="mix",
            weight_dtype=torch.float16,
            use_tf32=True,
            device="cuda",
        )
        self.automasker = AutoMasker(
            densepose_ckpt=os.path.join(ckpt, "DensePose"),
            schp_ckpt=os.path.join(ckpt, "SCHP"),
            device="cuda",
        )
        self.mask_processor = VaeImageProcessor(
            vae_scale_factor=8, do_normalize=False, do_binarize=True, do_convert_grayscale=True
        )
        self._warmup()

    @staticmethod
    def _fetch_code(snapshot_download):
        """Tải mã của tác giả, thử lần lượt các nguồn cho tới khi được.

        Trả về đường dẫn thư mục đã tải. Ném RuntimeError kèm TẤT CẢ lỗi nếu không nguồn nào chạy:
        một thông điệp chỉ nói nguồn cuối cùng hỏng sẽ giấu mất lý do thật của ba nguồn kia.
        """
        order = ([SPACE] if SPACE else []) + [s for s in SPACE_FALLBACKS if s != SPACE]
        errs = []
        for i, repo in enumerate(order):
            pinned = repo == "zhengchong/CatVTON"
            rev = SPACE_REV if pinned else None
            try:
                path = snapshot_download(repo_id=repo, repo_type="space", revision=rev)
            except Exception as e:                      # repo mất, bị gated, hoặc mạng hỏng
                log.warning("Nguồn %s không dùng được: %s: %s", repo, type(e).__name__, e)
                errs.append(f"{repo}: {type(e).__name__}: {e}")
                continue
            if i > 0 or not pinned:
                log.warning(
                    "Đang dùng nguồn DỰ PHÒNG %s%s. Đây là mã người khác chép lại và KHÔNG được "
                    "ghim revision, nên kết quả có thể khác lần chạy trước. Sao lưu một bản của "
                    "riêng mình rồi đặt CATVTON_SPACE trỏ vào đó.",
                    repo, "" if pinned else " @ main")
            else:
                log.info("Mã CatVTON: %s @ %s", repo, SPACE_REV[:12])
            return path
        raise RuntimeError(
            "Không tải được mã CatVTON từ nguồn nào. Repo GitHub của họ đã 404, nên các nguồn còn "
            "lại đều là HF Space:\n  " + "\n  ".join(errs)
            + "\nGiấy phép là cc-by-nc-sa-4.0, nên được phép tự sao lưu một bản: tải Space về, đẩy "
              "lên repo riêng, rồi đặt CATVTON_SPACE=<owner>/<name>."
        )

    def _warmup(self) -> None:
        """Một lượt 2 bước với ảnh trắng, để job đầu tiên của người dùng không gánh chi phí
        biên dịch kernel và cấp phát bộ nhớ lần đầu."""
        log.info("Warmup CatVTON...")
        blank = Image.new("RGB", (WIDTH, HEIGHT), "white")
        mask = Image.new("L", (WIDTH, HEIGHT), 255)
        with self._torch.inference_mode():
            self.pipeline(image=blank, condition_image=blank, mask=mask,
                          num_inference_steps=2, guidance_scale=GUIDANCE)
        log.info("Warmup xong")

    def run(self, person: Image.Image, garment: Image.Image, category: str) -> Image.Image:
        person = self._crop(person.convert("RGB"), (WIDTH, HEIGHT))
        garment = self._pad(garment.convert("RGB"), (WIDTH, HEIGHT))

        part = _CLOTH_TYPE.get(category, "upper")
        mask = self.automasker(person, part)["mask"]
        # Làm mờ biên mask: biên cứng để lại đường nối thấy rõ ở rìa áo.
        mask = self.mask_processor.blur(mask, blur_factor=9)

        gen = self._torch.Generator(device="cuda").manual_seed(SEED)
        with self._torch.inference_mode():
            out = self.pipeline(
                image=person,
                condition_image=garment,
                mask=mask,
                num_inference_steps=STEPS,
                guidance_scale=GUIDANCE,
                generator=gen,
            )[0]
        self._torch.cuda.empty_cache()
        return out
