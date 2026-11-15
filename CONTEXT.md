# PROJECT CONTEXT: VITAFLOW (WEB PC & CAPACITOR MOBILE APP)

## 1. CẤU TRÚC THƯ MỤC CHUẨN (Ổ D)
- **Thư mục gốc:** `D:\DevWorkspace\Projects\vitaflow`
- **`vitaflow/`:** Bản Web PC dành cho Quản lý & Coach thao tác trên máy tính.
- **`vitaflow_mobile/`:** Bản Backend Flask + Giao diện Mobile + Vỏ ứng dụng Capacitor Android (`vitaflow_mobile/mobile-app/`).
- *Database mặc định là `instance/vitaflow.db`; khi đổi tên database, giữ nguyên dữ liệu và cập nhật `DATABASE_URL` nếu dùng cấu hình riêng.*

## 2. TỔNG QUAN & PHÂN QUYỀN (RBAC)
- **Nền tảng:** Phòng tập nhóm hiện đại, năng động cho cả nam và nữ (tập theo ca), kết hợp AI Coach dinh dưỡng & mạng xã hội nội bộ.
- **Tech Stack:** Python Flask (Backend), SQLAlchemy + Flask-Migrate (Database), Tailwind CSS + Material Symbols (Frontend), Capacitor 8 (Android APK).
- **3 Tài khoản & Bảng màu bắt buộc:**
  1. **Manager (Quản lý):** Rolex Emerald Green (`#006039`) + Champagne Gold (`#C5A059`), nền `#F4F6F5`.
  2. **Coach (Huấn luyện viên):** Energetic Coral Orange (`#FF5A36`), nền `#FAF9F6`.
  3. **Member (Thành viên):** Soft Pastel Pink (`#F472B6`) + Lavender (`#A78BFA`), nền `#FAF5F5`.

## 3. NGUYÊN TẮC CODE BẤT BIẾN (DÀNH CHO CLAUDE / CHATGPT / DEEPSEEK / CLINE)
- Không nhồi nhét bảng biểu dày đặc; ưu tiên Clean Grid (Avatar + Tên) + Pop-up/Hover chi tiết.
- Kiểm tra chặt chẽ Object-level Authorization ở tầng Server (`manager` thấy tất cả; `coach` chỉ thao tác học viên của mình; `member` chỉ xem dữ liệu của chính mình).
- Khi trả về code, luôn ghi rõ đường dẫn file tương đối (ví dụ: `vitaflow_mobile/models.py` hoặc `vitaflow_mobile/blueprints/api.py`).
- Ảnh từ ComfyUI/Figma lưu tại `static/images/`, không dùng link ảnh chết bên ngoài.
