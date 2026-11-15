# VitaFlow – Hệ thống quản lý phòng tập

Flask + SQLite + Tailwind CSS (CDN) + Material Symbols. Ba cổng theo vai trò, mỗi cổng một màu nhận diện:

| Vai trò | Màu | Khu vực |
|---|---|---|
| Quản lý | Emerald `#006039` + Champagne Gold `#C5A059`, nền `#F4F6F5` | `/manager` |
| Coach | Coral `#FF5A36`, nền `#FAF9F6` | `/coach` |
| Thành viên | Pink `#F472B6` + Lavender `#A78BFA`, nền `#FAF5F5` | `/app` |

## Giao diện PC + Mobile chạy song song
Một backend, hai giao diện: điện thoại tự vào bản mobile (`templates/m/`), máy tính/tablet vào bản PC. Có nút chuyển đổi thủ công
(`/view/mobile`, `/view/desktop`). Chức năng, API và phân quyền hoàn toàn giống nhau. Đối chiếu từng màn thiết kế: `docs/UI_MOBILE_MAPPING.md`.
Kiểm thử: `python smoke_test.py` (PC) và `python smoke_test_mobile.py` (mobile).

## Chạy trên máy (local)
```bash
python -m venv venv
venv\Scripts\activate          # Windows   |   source venv/bin/activate  (macOS/Linux)
pip install -r requirements.txt
copy .env.example .env         # (cp trên macOS/Linux) rồi điền khoá nếu cần
python app.py                  # mở http://127.0.0.1:5000
```
Lần chạy đầu tự tạo `instance/vitaflow.db` và nạp dữ liệu demo. Tạo lại từ đầu: `python seed.py --reset`.
Kiểm thử toàn bộ route + phân quyền: `python smoke_test.py`.

**Tài khoản demo** (có nút điền nhanh ở trang đăng nhập)
- Quản lý: `manager@vitaflow.vn` / `manager123`
- Coach: `mai.anh@vitaflow.vn` / `coach123` (còn `yen.vy@…`, `thuy.duong@…`)
- Thành viên: `mai.phuong@gmail.com` / `member123` (hạng cao, có dữ liệu); `ngoc.diep@gmail.com` là hội viên **hết hạn** để thử cảnh báo.

## Cấu trúc
```
app.py            app factory, nav theo vai trò, context chung
config.py · extensions.py · models.py · seed.py
services.py       nghiệp vụ: hạng, streak, điểm danh, gia hạn cộng dồn, chat, thực đơn, QR
utils.py          @role_required, CSRF, upload ảnh, filter
blueprints/       auth · public · api (chat, thông báo) · manager · coach · member
ai_engine/        calculator (BMR/TDEE) · llm (Gemini) · rag (catalog món Việt) – tái dùng từ GYMFlow
templates/        layout.html + manager/ coach/ member/ partials/   (PC)
                  m/ …                                              (mobile, cùng cấu trúc)
static/           css/app.css (theme theo vai trò) · css/mobile.css · js/*.js dùng chung PC & mobile
```

## Phân quyền
`@manager_required`, `@coach_required`, `@member_required` (trong `utils.py`) chặn theo `role`; vào nhầm cổng sẽ được đưa về trang của mình.
Coach chỉ thao tác trên học viên được phân công (kiểm tra ở server, không chỉ ẩn nút). Chat chỉ cho các cặp hợp lệ (Quản lý↔mọi người, Coach↔học viên của mình, Hội viên↔Coach của mình/Quản lý + nhóm ca). Mọi POST có CSRF token.

## Luồng nghiệp vụ chính
- **Điểm danh:** Coach hiển thị QR ca (tự đổi mỗi 60 giây, ký bằng `itsdangerous`) → hội viên quét bằng camera điện thoại; hoặc Coach quét QR cá nhân của hội viên (camera) / nhập mã `HV-102`. Gói hết hạn sẽ bị từ chối và hiện ở danh sách cảnh báo. *Privacy Mode* che mọi thông tin, chỉ còn QR; thoát cần nhập lại mật khẩu Coach.
- **Streak & hạng:** điểm = 10/buổi (30 ngày) + 8/ngày streak + điểm “ăn chuẩn AI” + giảm cân. Diamond ≥ 400, Gold ≥ 250, Silver ≥ 120, còn lại Bronze (chỉnh ở `config.py`). Bật “kỳ nghỉ sinh lý” thì streak không bị ngắt khi nghỉ.
- **Nạp gói:** chọn gói/cơ sở/ca/Coach/voucher → mã VietQR + nội dung `VF HV102 G3T` → “Tôi đã chuyển khoản” → Quản lý xác nhận → **cộng dồn** ngày vào hạn hiện tại, gán Coach, đánh dấu voucher đã dùng.
- **Bảo lưu thẻ:** hội viên xin → Quản lý duyệt → hạn gói được cộng bù.
- **AI dinh dưỡng:** tính BMR/TDEE/macro → Gemini chọn món từ catalog món Việt. **Không có API key vẫn chạy** bằng thực đơn gợi ý offline.

## Cấu hình `.env`
`SECRET_KEY`, `GEMINI_API_KEY` (tuỳ chọn), `BANK_ID`/`BANK_ACCOUNT`/`BANK_ACCOUNT_NAME` (QR chuyển khoản), `DATABASE_URL` (mặc định SQLite).

## Lưu ý
- Tailwind, font, icon, Chart.js, thời tiết (Open-Meteo), VietQR và thư viện quét QR đều tải qua internet.
- Quét QR bằng camera cần HTTPS hoặc `localhost`. Muốn thử trên điện thoại: chạy HTTPS (ví dụ ngrok) hoặc dùng ô nhập mã.
- Khi đưa lên môi trường thật: đặt `SECRET_KEY` mạnh, chạy bằng gunicorn/waitress, `debug=False`, cân nhắc PostgreSQL.
