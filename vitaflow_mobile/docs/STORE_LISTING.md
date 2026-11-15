# Nội dung & hồ sơ đăng cửa hàng ứng dụng

> Quy định của Apple/Google thay đổi hằng năm. Danh sách dưới đây dựa trên hiểu biết đến thời điểm viết; **đối chiếu lại với trang chính thức** (App Review Guidelines, Play Console Policy Center) trước khi nộp. Văn bản mẫu cần bạn chỉnh theo thực tế phòng tập.

## 1. Thông tin cơ bản
| Mục | Nội dung gợi ý |
|---|---|
| Tên app | VITAFLOW |
| Phụ đề iOS (≤30 ký tự) | Gym, Coach & dinh dưỡng nữ |
| Mô tả ngắn Google Play (≤80) | Lịch tập, Coach 1:1, thực đơn AI và cộng đồng dành riêng cho phái đẹp. |
| Danh mục | Health & Fitness (Sức khoẻ & Thể hình) |
| Từ khoá iOS (≤100) | gym,fitness,yoga,pilates,phụ nữ,giảm cân,dinh dưỡng,thực đơn,coach,tập luyện |
| URL quyền riêng tư | `https://<domain>/privacy` |
| URL điều khoản | `https://<domain>/terms` |
| URL hỗ trợ | `https://<domain>/support` |
| URL yêu cầu xoá tài khoản (Google Data safety) | `https://<domain>/support#xoa-tai-khoan` |
| Email liên hệ | giá trị `SUPPORT_EMAIL` |

## 2. Mô tả đầy đủ (tiếng Việt)
**VITAFLOW – không gian chăm sóc vóc dáng & dinh dưỡng dành riêng cho phái đẹp.**

Quản lý toàn bộ hành trình tập luyện tại phòng tập boutique của bạn ngay trên điện thoại:

• **Điểm danh bằng QR** – quét mã tại phòng tập, tự động cộng chuỗi chuyên cần (streak).
• **Lịch ca & đặt chỗ** – xem ca còn trống, đặt chỗ, báo vắng, đổi ca linh hoạt.
• **Coach 1:1** – nhắn tin trực tiếp với huấn luyện viên và nhóm ca tập.
• **Thực đơn AI từ món ăn gia đình Việt** – tính BMR/TDEE, gợi ý 3 bữa, đổi món tương đương, gửi ảnh mâm cơm để Coach chấm điểm.
• **Nhật ký Body** – theo dõi cân nặng, số đo ba vòng, ảnh Before/After được khoá riêng tư.
• **Cộng đồng** – chia sẻ khoảnh khắc, rủ bạn tập cùng, chế độ “kỳ nghỉ sinh lý” bảo vệ chuỗi streak.
• **Hạng thành viên & quà tặng** – tích điểm chuyên cần, nhận voucher từ Coach và phòng tập.
• **Gói tập & nạp gói nhanh** – theo dõi thời hạn, gia hạn bằng mã VietQR, ngày tập được cộng dồn.

Gợi ý dinh dưỡng và bài tập chỉ mang tính tham khảo, không thay thế tư vấn y tế. Bạn có thể xoá tài khoản và toàn bộ dữ liệu bất cứ lúc nào trong Hồ sơ.

## 3. Ghi chú cho người duyệt (App Review Information) – tiếng Anh
```
VITAFLOW is the member app for a women-only boutique gym chain in Vietnam. Members use it to check in at the gym with QR codes,
book class slots, chat with their assigned coach, track body measurements, and renew memberships.

NATIVE FEATURES (not just a website): camera QR scanner (ML Kit), push notifications (APNs), native splash/offline screen and
Android back-button handling. The UI is a dedicated mobile layout served by our backend so we can ship fixes without resubmitting.

SIGN-IN
  Member:  <email> / <password>
  Coach:   <email> / <password>
How to test QR check-in: sign in as Coach -> bottom tab "QR" shows a rotating class QR code. Sign in as Member on a second device
-> "QR" tab -> "Quét mã ca tập" and scan it. (Alternative: Coach enters member code HV-xxx manually.)

USER-GENERATED CONTENT (Guideline 1.2): every post/comment has Report (flag) and Block buttons; reports go to the manager's
moderation queue and are handled within 24 hours; Terms prohibit objectionable content; users must accept Terms at sign-up.
ACCOUNT DELETION (5.1.1(v)): Profile -> "Privacy & account" -> "Xoá tài khoản của tôi" (deletes all personal data immediately).
PAYMENTS (3.1.3(e)): memberships are for in-person gym services; paid by bank transfer outside the app. No digital goods are sold.
HEALTH DATA (5.1.3): body measurements/photos are entered by the user, stored privately, shown to the user's coach only with consent
(Profile -> photo visibility), never used for advertising. AI meal suggestions send age/height/weight/goal only (no name/email).
Contact: <email>, <phone>
```

## 4. Google Play – khai báo “Data safety” (gợi ý theo đúng luồng dữ liệu của app)
| Loại dữ liệu | Thu thập | Chia sẻ* | Mục đích |
|---|---|---|---|
| Họ tên, email, số điện thoại | Có | Không | Chức năng app, quản lý tài khoản |
| Thông tin sức khoẻ & thể hình (cân nặng, số đo, ảnh tiến trình, nhật ký ăn) | Có | Không | Chức năng app |
| Ảnh | Có (ảnh bữa ăn, bài đăng, tiến trình) | Không | Chức năng app |
| Tin nhắn trong app | Có | Không | Chức năng app |
| Hoạt động trong app (lịch, điểm danh) | Có | Không | Chức năng app, phân tích nội bộ |
| Mã định danh thiết bị (push token) | Có | Không | Thông báo |
\* Gửi cho nhà cung cấp xử lý *thay mặt bạn* (Google Gemini cho thực đơn AI, FCM/APNs cho push) thường không tính là “chia sẻ” theo định nghĩa của Google; hãy đọc kỹ định nghĩa hiện hành khi điền.
Mã hoá khi truyền: **Có** (HTTPS). Người dùng yêu cầu xoá dữ liệu: **Có** (trong app + URL web ở mục 1).

## 5. App Store – “App Privacy” (nhãn quyền riêng tư)
Khai: Contact Info (tên, email, SĐT), Health & Fitness, Photos or Videos, User Content (bài đăng, tin nhắn), Identifiers (push token), Usage Data (lịch/điểm danh). Tất cả **liên kết với danh tính người dùng**, **không dùng để theo dõi (tracking)**, mục đích *App Functionality*. Không dùng quảng cáo → không cần App Tracking Transparency.

## 6. Hình ảnh cần chuẩn bị
- **Google Play:** icon 512×512, ảnh bìa 1024×500, tối thiểu 2 ảnh chụp điện thoại (tỉ lệ 9:16, khuyến nghị 1080×1920 trở lên).
- **App Store:** ảnh iPhone khổ 6.9" (vd 1320×2868) – bắt buộc; thêm 6.5" nếu cần. App chạy được trên iPad nên cần ảnh iPad (13"), **hoặc** vào Xcode chọn chỉ *iPhone* (Targets ▸ Deployment Info ▸ Devices) để khỏi phải làm.
- Chụp từ app thật (bản mobile), dùng dữ liệu mẫu đẹp, **không để lộ thông tin cá nhân thật**.

## 7. Phân loại độ tuổi
Trả lời trung thực bảng câu hỏi của từng cửa hàng. Lưu ý các mục: *nội dung do người dùng tạo* (có), *dữ liệu sức khoẻ* (có), *quảng cáo* (không), *mua hàng trong app* (không). Điều khoản của app quy định từ 18 tuổi.

## 8. Danh sách kiểm tra trước khi nộp
- [ ] Máy chủ HTTPS ổn định, `APP_ENV=production`, không còn tài khoản demo
- [ ] Chính sách & Điều khoản đã được luật sư rà soát, thông tin liên hệ thật
- [ ] Có tài khoản Member + Coach cho reviewer, dữ liệu mẫu đầy đủ
- [ ] Thử trên **máy thật** (Android + iPhone qua TestFlight): đăng ký, đăng nhập, quét QR, push, báo cáo/chặn, xoá tài khoản, mất mạng
- [ ] Có người xử lý hàng đợi kiểm duyệt trong 24 giờ (đây là cam kết trong Điều khoản)
- [ ] Google Play (tài khoản cá nhân mới): đủ số người thử nghiệm kín trong thời gian yêu cầu hiện hành trước khi lên Production
- [ ] Sao lưu keystore Android + khoá `.p8`/chứng chỉ Apple
