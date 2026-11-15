/* Hội viên quét QR của ca ngay trong trình duyệt điện thoại / app (thay vì mở camera hệ thống). */
(function () {
  const btn = document.getElementById('btn-scan-shift'), box = document.getElementById('shift-reader'), msg = document.getElementById('shift-scan-msg');
  if (!btn) return; let scanner = null, done = false;
  function handle(txt) {
    if (done) return; let u; try { u = new URL(txt); } catch (e) { msg.textContent = 'Mã QR không hợp lệ.'; return; }
    if (!u.pathname.startsWith('/app/checkin/shift/')) { msg.textContent = 'Đây không phải mã QR điểm danh của ca tập.'; return; }
    done = true; if (scanner) scanner.stop().catch(() => {}); location.href = u.pathname;   // luôn dùng cùng máy chủ hiện tại
  }
  document.addEventListener('vitaflow:qr', (e) => handle(e.detail));   // camera native (app)
  btn.onclick = async () => {
    if (scanner) { await scanner.stop().catch(() => {}); scanner = null; box.classList.add('hidden'); return; }
    if (!window.Html5Qrcode) await new Promise((ok, no) => { const s = document.createElement('script'); s.src = 'https://cdn.jsdelivr.net/npm/html5-qrcode@2.3.8/html5-qrcode.min.js'; s.onload = ok; s.onerror = no; document.head.appendChild(s); }).catch(() => { msg.textContent = 'Không tải được thư viện quét QR (cần internet).'; });
    if (!window.Html5Qrcode) return;
    box.classList.remove('hidden'); scanner = new Html5Qrcode('shift-reader');
    scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: 230 }, handle)
      .catch(() => { msg.textContent = 'Không mở được camera. Hãy cấp quyền camera cho trình duyệt.'; box.classList.add('hidden'); scanner = null; });
  };
})();
