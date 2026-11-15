# VitaFlow – App Android & iOS (Capacitor)

App là một **vỏ native** mở website VitaFlow (bản giao diện mobile) và bổ sung những thứ trình duyệt không làm tốt: **quét QR bằng camera gốc, thông báo đẩy, nút Back Android, màn hình chờ/không có mạng**. Toàn bộ logic nằm ở máy chủ Flask nên sửa web là app tự cập nhật, không cần nộp lại cửa hàng (trừ khi đổi phần native).

```
Điện thoại ── VitaFlow.app ──HTTPS──▶ https://app.tencongty.vn  (Flask, thư mục cha)
              ├ WebView mở giao diện mobile (User-Agent có "VITAFLOWApp/1.0" -> server tự chọn bản mobile)
              └ Plugin native: camera quét QR · push · splash · nút Back
```

## 0. Điều kiện cần
| Thứ | Ghi chú |
|---|---|
| Máy chủ HTTPS đang chạy | Xem `../docs/DEPLOY.md`. **Làm trước.** |
| Node ≥ 22 | `node -v` |
| Android Studio (JDK có sẵn) | build file `.aab` cho CH Play |
| Mac + Xcode | **Bắt buộc** để build/nộp iOS (không làm được trên Windows/Linux) |
| Tài khoản Google Play Console | phí 25 USD một lần |
| Apple Developer Program | 99 USD/năm |
| Firebase project (miễn phí) | cho push Android |

## 1. Cấu hình
```bash
cd mobile-app
npm install
npm run configure -- --url https://app.tencongty.vn --appId vn.VITAFLOW.app --name "VitaFlow"
```
> ⚠ **`appId` không đổi được sau khi phát hành.** Chọn kỹ (dạng tên miền ngược). Nên đặt cùng giá trị ở `APNS_BUNDLE_ID` trên máy chủ.

## 2. Tạo project native
```bash
npm run add:android          # tạo thư mục android/ + thêm quyền camera, thông báo
npm run add:ios              # (trên Mac) tạo thư mục ios/ + thêm mô tả quyền
npm run assets               # sinh icon + splash từ resources/ (thay bằng logo thật của bạn, giữ đúng tên/kích thước)
npm run sync
```
`resources/icon.png` (1024×1024), `icon-foreground.png`/`icon-background.png` (Android adaptive), `splash.png`/`splash-dark.png` (2732×2732) hiện là logo mẫu chữ “H”.

## 3. Android
1. **Push:** Firebase Console → thêm app Android với đúng `appId` → tải `google-services.json` đặt vào `android/app/`.
2. `npm run android` (mở Android Studio) → chờ Gradle sync.
3. Thử trên máy thật/giả lập: đăng nhập, quét QR, nhận thông báo.
4. **Ký và build bản phát hành:** Build ▸ Generate Signed App Bundle ▸ *Android App Bundle* → tạo **keystore mới** (đặt tên `vitaflow-release.jks`).
   **Sao lưu keystore + mật khẩu ở nơi an toàn.** Mất là không cập nhật được app nữa. Bật *Play App Signing* khi tải lên.
5. Play Console → Tạo ứng dụng → tải file `.aab` lên **Internal testing** trước.
6. `targetSdk` mà Capacitor 8 sinh ra là **36** (đã kiểm tra). Yêu cầu của Google đổi hằng năm — đối chiếu trang *Target API level requirements* trước khi nộp.

## 4. iOS (trên Mac)
1. `npm run ios` → Xcode. Chọn target **App** ▸ *Signing & Capabilities* ▸ chọn Team, đặt Bundle Identifier = `appId`.
2. **+ Capability** ▸ **Push Notifications** và **Background Modes ▸ Remote notifications**.
3. Apple Developer ▸ Keys ▸ tạo **APNs Auth Key (.p8)** → điền các biến `APNS_*` trên máy chủ (xem `../docs/DEPLOY.md` mục 6).
4. Chọn *Any iOS Device (arm64)* ▸ **Product ▸ Archive** ▸ Distribute App ▸ App Store Connect ▸ Upload.
5. App Store Connect ▸ **TestFlight**: thử trên iPhone thật (quét QR, push, đăng xuất…), rồi mới nộp duyệt.

## 5. Điều gì làm app bị từ chối & cách đã xử lý
| Quy định | Đã có trong dự án |
|---|---|
| Apple 4.2 – app chỉ “bọc web” | Có tính năng native thật: camera QR, push, splash/offline; giao diện mobile riêng. **Rủi ro vẫn còn** vì nội dung tải từ web — nêu rõ tính năng native trong *Review Notes* (xem `../docs/STORE_LISTING.md`). |
| Apple 1.2 / Google UGC – nội dung người dùng đăng | Báo cáo bài/bình luận, chặn người dùng, trang kiểm duyệt cho Quản lý, điều khoản cấm nội dung vi phạm, đồng ý điều khoản khi đăng ký |
| Apple 5.1.1(v) / Google – xoá tài khoản | Hồ sơ ▸ Xoá tài khoản (xoá toàn bộ dữ liệu) + URL web `…/support#xoa-tai-khoan` cho form Data safety |
| Chính sách quyền riêng tư | `/privacy`, `/terms`, `/support` (có thể mở không cần đăng nhập) |
| Dữ liệu sức khoẻ (Apple 5.1.3) | Nêu trong chính sách; có tuyên bố “không thay thế tư vấn y tế” ở thực đơn AI và Điều khoản |
| Thanh toán (Apple 3.1.3(e)) | Gói tập là dịch vụ dùng **tại phòng tập** → được phép thanh toán ngoài app (chuyển khoản). Không bán nội dung số trong app |
| Cần tài khoản demo cho reviewer | Xem `../docs/DEPLOY.md` mục 5 |
| Mã hoá xuất khẩu | Đã khai `ITSAppUsesNonExemptEncryption = false` (chỉ dùng HTTPS) |

## 6. Cập nhật sau này
- Sửa web/logic: chỉ cần triển khai lại máy chủ.
- Đổi plugin/quyền/icon/phiên bản: `npm run sync`, tăng `versionCode`/`versionName` (Android) và Build number (iOS), build lại và nộp.

## 7. Sự cố thường gặp
- **Màn hình “Không có kết nối mạng”**: sai `--url`, máy chủ chưa HTTPS hợp lệ, hoặc `allowNavigation` không khớp domain → chạy lại `npm run configure`.
- **Camera không bật trên Android**: kiểm tra đã chạy `npm run add:android` (vá quyền) và cấp quyền camera trong cài đặt.
- **Không nhận push iOS**: thiếu Push capability, sai `APNS_BUNDLE_ID` hoặc khoá `.p8`. Lưu ý: bản **TestFlight/App Store** dùng APNs **production**; chỉ bản Debug cài thẳng từ Xcode mới cần `APNS_USE_SANDBOX=1`.
- **Đăng nhập xong bị văng**: cookie `Secure` cần HTTPS thật; kiểm tra `BEHIND_PROXY=1` khi đứng sau proxy.

## Đã kiểm thử / chưa kiểm thử
Đã chạy được: `cap add android/ios`, `cap sync`, tạo icon/splash, bản vá quyền (idempotent), và logic `static/js/native.js` bằng Capacitor giả lập (push, camera QR, nút Back, đăng xuất). **Chưa thể kiểm thử ở đây:** build `.aab`/`.ipa`, chạy trên máy thật, nhận push thật, quét camera thật, và quá trình duyệt của cửa hàng.
