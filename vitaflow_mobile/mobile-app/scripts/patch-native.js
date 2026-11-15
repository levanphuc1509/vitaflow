// Chạy sau `cap add android|ios` để thêm quyền camera/thông báo (chạy lại nhiều lần vẫn an toàn).
//   node scripts/patch-native.js android|ios
const fs = require('fs'), path = require('path');
const target = process.argv[2];
const CAM = 'VitaFlow cần camera để quét mã QR điểm danh và chụp ảnh mâm cơm / ảnh tiến trình của bạn.';
const PHOTO = 'VitaFlow cần truy cập thư viện ảnh để bạn chọn ảnh đăng bài, gửi Coach hoặc lưu ảnh tiến trình.';
function patchAndroid() {
  const p = path.join('android', 'app', 'src', 'main', 'AndroidManifest.xml');
  if (!fs.existsSync(p)) { console.error('Chưa có thư mục android. Chạy: npm run add:android'); process.exit(1); }
  let s = fs.readFileSync(p, 'utf8'); const add = [];
  const perms = ['<uses-permission android:name="android.permission.CAMERA" />', '<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />',
    '<uses-feature android:name="android.hardware.camera" android:required="false" />'];
  for (const x of perms) if (!s.includes(x.match(/android:name="([^"]+)"/)[1])) add.push('    ' + x);
  if (add.length) s = s.replace(/<\/manifest>/, add.join('\n') + '\n</manifest>');
  if (!s.includes('com.google.mlkit.vision.DEPENDENCIES')) s = s.replace(/<\/application>/, '        <meta-data android:name="com.google.mlkit.vision.DEPENDENCIES" android:value="barcode_ui" />\n    </application>');
  s = s.replace('android:allowBackup="true"', 'android:allowBackup="false"');   // dữ liệu sức khoẻ: không sao lưu lên đám mây
  fs.writeFileSync(p, s); console.log('Android: đã thêm quyền CAMERA, POST_NOTIFICATIONS và module quét mã ML Kit.');
}
function patchIos() {
  const p = path.join('ios', 'App', 'App', 'Info.plist');
  if (!fs.existsSync(p)) { console.error('Chưa có thư mục ios. Chạy: npm run add:ios (trên macOS)'); process.exit(1); }
  let s = fs.readFileSync(p, 'utf8');
  const keys = { NSCameraUsageDescription: CAM, NSPhotoLibraryUsageDescription: PHOTO, NSPhotoLibraryAddUsageDescription: PHOTO };
  for (const [k, v] of Object.entries(keys)) if (!s.includes('<key>' + k + '</key>')) s = s.replace(/<\/dict>\s*<\/plist>/, `\t<key>${k}</key>\n\t<string>${v}</string>\n</dict>\n</plist>`);
  if (!s.includes('ITSAppUsesNonExemptEncryption')) s = s.replace(/<\/dict>\s*<\/plist>/, '\t<key>ITSAppUsesNonExemptEncryption</key>\n\t<false/>\n</dict>\n</plist>');   // chỉ dùng HTTPS chuẩn -> miễn khai báo mã hoá
  if (!s.includes('<key>UIBackgroundModes</key>')) s = s.replace(/<\/dict>\s*<\/plist>/, '\t<key>UIBackgroundModes</key>\n\t<array>\n\t\t<string>remote-notification</string>\n\t</array>\n</dict>\n</plist>');
  fs.writeFileSync(p, s); console.log('iOS: đã thêm mô tả quyền camera/ảnh và chế độ nền thông báo. Còn phải bật Push Notifications trong Xcode (xem README).');
}
if (target === 'android') patchAndroid(); else if (target === 'ios') patchIos(); else { console.error('Dùng: node scripts/patch-native.js android|ios'); process.exit(1); }
