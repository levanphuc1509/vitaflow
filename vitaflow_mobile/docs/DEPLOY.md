# Triển khai máy chủ (bắt buộc trước khi lên cửa hàng ứng dụng)

App Android/iOS chỉ là "vỏ" mở website của bạn, nên **máy chủ phải chạy HTTPS ổn định 24/7 trước khi nộp app**. Reviewer của Apple/Google sẽ dùng app thật với máy chủ thật.

## 1. Chọn nơi chạy
Bất kỳ nơi nào chạy được Docker/Python và có HTTPS: VPS (Ubuntu + nginx + certbot), Render, Fly.io, Railway… Cần: tên miền (vd `app.tencongty.vn`), **PostgreSQL**, và **ổ đĩa bền vững** cho thư mục `static/uploads` (ảnh hội viên) — nếu dùng nền tảng có đĩa tạm, hãy gắn volume hoặc chuyển ảnh sang S3 trước khi chạy thật.

## 2. Biến môi trường
Sao chép `.env.example`, điền đủ. Tối thiểu: `APP_ENV=production`, `SECRET_KEY`, `DATABASE_URL`, `BEHIND_PROXY=1`, thông tin `COMPANY_NAME/SUPPORT_EMAIL/SUPPORT_PHONE`, tài khoản ngân hàng VietQR.
Nếu thiếu `SECRET_KEY`, ứng dụng **từ chối khởi động** (cố ý) khi `APP_ENV=production`.

## 3. Chạy
```bash
docker build -t vitaflow .
docker run -d --name vitaflow --env-file .env -p 8000:8000 -v vitaflow_uploads:/app/static/uploads vitaflow
```
Đặt nginx/Caddy phía trước, trỏ domain → cổng 8000 và bật HTTPS (Let's Encrypt). Kiểm tra `https://domain/login`.

## 4. Tạo dữ liệu thật (KHÔNG có tài khoản demo khi production)
```bash
docker exec -it vitaflow python manage.py create-branch --name "Cơ sở 1" --address "Địa chỉ"
docker exec -it vitaflow python manage.py create-manager --email quanly@tencongty.vn --name "Họ tên"
```
Quản lý đăng nhập → thêm Coach (Nhân sự & Cơ sở), tạo ca tập, gói. Hội viên tự đăng ký trong app.
Quên mật khẩu: `python manage.py reset-password --email ...`.

## 5. Tài khoản cho reviewer (bắt buộc với Apple, nên có với Google)
Tạo 1 tài khoản **hội viên** và 1 **Coach** thật có dữ liệu mẫu (gói còn hạn, vài buổi tập, tin nhắn) rồi điền vào mục "App Review Information / Sign-in required". Đừng dùng tài khoản của khách thật.

## 6. Thông báo đẩy (tuỳ chọn nhưng nên có)
- **Android (FCM):** tạo project Firebase → Project settings → Service accounts → tạo khoá JSON → đặt đường dẫn vào `FIREBASE_CREDENTIALS`. File `google-services.json` của app Android tải ở cùng project.
- **iOS (APNs):** trên Apple Developer → Keys → tạo **APNs Auth Key (.p8)**, đặt vào `APNS_KEY_PATH`, điền `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_BUNDLE_ID` (trùng appId). Chỉ khi chạy bản **Debug cài thẳng từ Xcode** mới đặt `APNS_USE_SANDBOX=1`; bản **TestFlight và App Store dùng APNs production** (không đặt biến này). *(Capacitor trên iOS trả về token APNs, nên server gửi thẳng tới APNs, không đi qua Firebase.)*
Không cấu hình thì app vẫn chạy bình thường, chỉ không có push. Phần gửi APNs đã kiểm thử với máy chủ Apple giả lập, **chưa thử với Apple thật** — hãy thử trên máy thật qua TestFlight.

## 7. Việc nên làm trước khi có dữ liệu thật
- **Migration CSDL:** dự án dùng `db.create_all()` (tạo bảng lần đầu, *không* sửa bảng đã có). Trước khi có dữ liệu thật hãy thêm Flask-Migrate/Alembic để thay đổi cấu trúc sau này không mất dữ liệu.
- Sao lưu PostgreSQL hằng ngày + sao lưu thư mục uploads.
- Giới hạn tần suất đăng nhập (rate limit) ở nginx hoặc Flask-Limiter để chống dò mật khẩu.
- Giám sát lỗi (Sentry) và uptime.
- Nhờ luật sư rà soát **Chính sách quyền riêng tư & Điều khoản** (`templates/public/legal.html`) — đây là bản mẫu theo đúng luồng dữ liệu của app, chưa phải tư vấn pháp lý.
