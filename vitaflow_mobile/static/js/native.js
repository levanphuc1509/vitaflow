/* Cầu nối app native (Capacitor). Chỉ chạy khi trang được mở trong app Android/iOS; trình duyệt thường bỏ qua hoàn toàn. */
(function () {
  const C = window.Capacitor;
  if (!C || !C.isNativePlatform || !C.isNativePlatform()) return;
  document.documentElement.classList.add('is-native');
  const P = C.Plugins || {};
  const authed = !!document.querySelector('meta[name="vitaflow-auth"]');
  const csrf = () => (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

  // 1) Thông báo đẩy: xin quyền -> lấy token FCM/APNs -> gửi lên máy chủ
  async function setupPush() {
    const PN = P.PushNotifications;
    if (!PN || !authed || sessionStorage.getItem('hf_push_done')) return;
    try {
      let perm = await PN.checkPermissions();
      if (perm.receive === 'prompt' || perm.receive === 'prompt-with-rationale') perm = await PN.requestPermissions();
      if (perm.receive !== 'granted') return;
      PN.addListener('registration', async (t) => {
        localStorage.setItem('hf_push_token', t.value);
        await VitaFlow.post('/api/device/register', { token: t.value, platform: C.getPlatform() });
      });
      PN.addListener('registrationError', (e) => console.warn('Đăng ký push lỗi', e));
      PN.addListener('pushNotificationActionPerformed', (a) => {   // bấm vào thông báo -> mở đúng trang
        const u = a && a.notification && a.notification.data && a.notification.data.url;
        if (u && u.charAt(0) === '/') location.href = u;
      });
      await PN.register();
      sessionStorage.setItem('hf_push_done', '1');
    } catch (e) { console.warn('Push:', e); }
  }

  // 2) Quét QR bằng camera gốc (ML Kit) thay cho html5-qrcode
  async function scanQR() {
    const BS = P.BarcodeScanner; if (!BS) return null;
    const perm = await BS.requestPermissions();
    if (perm.camera !== 'granted' && perm.camera !== 'limited') { VitaFlow.toast('Cần cấp quyền camera để quét mã QR.', 'error'); return null; }
    if (C.getPlatform() === 'android' && BS.isGoogleBarcodeScannerModuleAvailable) {
      const r = await BS.isGoogleBarcodeScannerModuleAvailable();
      if (!r.available) await BS.installGoogleBarcodeScannerModule();
    }
    const res = await BS.scan({ formats: ['QR_CODE'] });
    return res && res.barcodes && res.barcodes[0] ? res.barcodes[0].rawValue : null;
  }
  document.addEventListener('click', async (e) => {
    const b = e.target.closest('#btn-camera, #btn-scan-shift'); if (!b || !P.BarcodeScanner) return;
    e.preventDefault(); e.stopImmediatePropagation();
    try { const v = await scanQR(); if (v) document.dispatchEvent(new CustomEvent('vitaflow:qr', { detail: v })); }
    catch (err) { VitaFlow.toast('Không mở được camera quét mã.', 'error'); }
  }, true);

  // 3) Nút Back của Android: đóng hộp thoại -> lùi trang -> thoát app
  if (P.App && P.App.addListener) P.App.addListener('backButton', (ev) => {
    const open = document.querySelector('.modal:not(.hidden)');
    if (open) { open.classList.add('hidden'); return; }
    if (ev.canGoBack || history.length > 1) history.back(); else P.App.exitApp();
  });

  // 4) Đăng xuất: huỷ token push của thiết bị này rồi mới đăng xuất
  document.addEventListener('submit', async (e) => {
    const f = e.target; if (!f.getAttribute || f.getAttribute('action') !== '/logout') return;
    const t = localStorage.getItem('hf_push_token'); if (!t) return;
    e.preventDefault(); localStorage.removeItem('hf_push_token'); sessionStorage.removeItem('hf_push_done');
    try { await VitaFlow.post('/api/device/unregister', { token: t }); } catch (x) {}
    f.submit();
  }, true);

  // 5) Ẩn thanh trạng thái splash (nếu có plugin)
  if (P.SplashScreen && P.SplashScreen.hide) P.SplashScreen.hide();
  setupPush();
})();
