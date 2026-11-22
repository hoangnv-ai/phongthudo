# Phòng thử đồ

Dán link sản phẩm Shopee/TikTok cùng ảnh toàn thân, nhận lại ảnh bạn mặc sản phẩm đó.

## Kiến trúc

```
Trình duyệt (static/: HTML + CSS + JS thuần)
   │  POST /api/product/resolve   link → ảnh sản phẩm
   │  POST /api/tryon             ảnh người + ảnh đồ → job_id
   │  GET  /api/jobs/{id}         hỏi trạng thái (1.5s/lần)
   ▼
FastAPI (app/)  ──RPUSH──►  Redis  ──BLPOP──►  Worker GPU (worker/)
   │                                               │
   └──────────── storage/jobs/<id>/ (dùng chung) ◄─┘
                 person.jpg  garment.jpg  result.jpg
```

| Thư mục | Vai trò |
|---|---|
| `app/main.py` | FastAPI, phục vụ API + giao diện tĩnh, dọn file hết hạn |
| `app/api/product.py` | Đọc link sản phẩm → danh sách ảnh |
| `app/api/tryon.py` | Nhận ảnh, đưa job vào hàng đợi, trả kết quả |
| `app/scrapers/` | `shopee.py`, `shopee_affiliate.py`, `tiktok.py`, `common.py` |
| `app/queue.py`, `app/storage.py` | Hàng đợi Redis, lưu ảnh theo job |
| `worker/vton_worker.py` | Vòng lặp lấy job → chạy model → ghi kết quả |
| `worker/models/` | `mock.py` (giả lập), `catvton.py` (khung cho model thật) |
| `static/` | Giao diện |

## Chạy trên máy

```bash
make install          # tạo .venv bằng uv, cài thư viện
cp .env.example .env

make redis            # terminal 1
make api              # terminal 2 → http://localhost:8000
make worker           # terminal 3
make test
```

Hoặc dùng Docker: `docker compose up --build` → http://localhost:8000

## Đọc link Shopee

1. Link rút gọn (`s.shopee.vn`, `shp.ee`) → đi theo redirect, chỉ trong domain Shopee.
2. Tách `shop_id`, `item_id`, `image_ids` từ link.
3. `image_ids` (link chia sẻ từ app thường có) → `https://down-vn.img.susercontent.com/file/<id>`.
4. Có `SHOPEE_AFFILIATE_APP_ID/SECRET` → gọi Affiliate Open API lấy ảnh chính, tên và link affiliate
   (nút "Mua sản phẩm" trên kết quả dùng link này).
5. Không lấy được ảnh → giao diện mở phần "Tải ảnh sản phẩm lên".

Không gọi API nội bộ của Shopee hay giả danh bot: vừa vi phạm điều khoản, vừa hay hỏng.
TikTok hiện chỉ tách `product_id`, người dùng tự tải ảnh lên (chờ TikTok Shop Affiliate API).

## Gắn model thật

1. Viết class kế thừa `TryOnModel` trong `worker/models/` (`load()` 1 lần, `run(person, garment, category)`).
2. Đăng ký trong `worker/models/__init__.py`, đặt `VTON_MODEL=<tên>`.
3. Build worker bằng `Dockerfile.gpu`, bật khối `deploy` GPU trong `docker-compose.yml`.

Mỗi tiến trình worker giữ 1 model / 1 GPU. Muốn tăng tải: chạy thêm worker, chúng tự chia job qua Redis.

## Bảo mật & quyền riêng tư

- Ảnh và trạng thái job tự xoá sau `DATA_TTL_HOURS` (mặc định 6 giờ).
- Server chỉ tải ảnh từ CDN Shopee/TikTok (chống SSRF), không theo redirect.
- Ảnh được kiểm tra, xoay theo EXIF, giới hạn kích thước và số pixel.

## Việc nên làm tiếp

- [ ] Kiểm chứng với Shopee thật: link rút gọn có trả 30x không, CDN có chặn hotlink không.
- [ ] Đăng ký Shopee Affiliate, đối chiếu chữ ký/tên trường trong `shopee_affiliate.py`.
- [ ] Gắn model thật (CatVTON, IDM-VTON, …) + bước tách áo khỏi ảnh có người mẫu/chữ.
- [ ] Hàng đợi tin cậy hơn: job đang chạy mà worker chết sẽ kẹt ở `running` (dùng BLMOVE + danh sách processing).
- [ ] Giới hạn tần suất theo IP, captcha nếu public.
- [ ] Chạy sau reverse proxy (nginx/Caddy) có HTTPS, giới hạn kích thước body.
