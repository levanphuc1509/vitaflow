/* Trạm quét QR của Coach (dùng chung PC & mobile) */
(function () {
  const SID = +document.getElementById('checkin-root').dataset.shift; let left = 0, timer;
  const holder = document.getElementById('qr-holder'), pq = document.getElementById('privacy-qr'), cnt = document.getElementById('qr-count');
  async function loadQR() {
    try { const j = await (await fetch('/coach/checkin/qr/' + SID)).json(); holder.innerHTML = j.svg; pq.innerHTML = j.svg; left = 60; } catch (e) { holder.textContent = 'Không tạo được mã QR'; }
  }
  loadQR(); setInterval(() => { left--; cnt.textContent = Math.max(left, 0); if (left <= 0) loadQR(); }, 1000);

  // Privacy mode
  const priv = document.getElementById('privacy'), pc = document.getElementById('privacy-clock');
  setInterval(() => { pc.textContent = new Date().toLocaleTimeString('vi-VN'); }, 1000);
  document.getElementById('btn-privacy').onclick = () => { priv.classList.remove('hidden'); priv.classList.add('flex'); (document.documentElement.requestFullscreen || (() => {})).call(document.documentElement).catch?.(() => {}); };
  document.getElementById('btn-exit').onclick = () => { document.getElementById('m-exit').classList.remove('hidden'); document.getElementById('exit-pass').focus(); };
  document.getElementById('exit-form').onsubmit = async (e) => {
    e.preventDefault(); const j = await VitaFlow.post('/coach/checkin/unlock', { password: document.getElementById('exit-pass').value });
    if (j.ok) { priv.classList.add('hidden'); priv.classList.remove('flex'); document.getElementById('m-exit').classList.add('hidden'); document.exitFullscreen && document.fullscreenElement && document.exitFullscreen(); e.target.reset(); }
    else document.getElementById('exit-err').classList.remove('hidden');
  };

  // Quét / nhập mã hội viên
  const res = document.getElementById('scan-result');
  async function submitCode(code) {
    const j = await VitaFlow.post('/coach/checkin/scan', { code, shift_id: SID });
    res.classList.remove('hidden', 'bg-emerald-50', 'bg-red-50', 'text-emerald-700', 'text-red-700');
    res.classList.add(j.ok ? 'bg-emerald-50' : 'bg-red-50', j.ok ? 'text-emerald-700' : 'text-red-700');
    res.textContent = j.message || j.error;
    if (j.ok) setTimeout(() => location.reload(), 1200);
  }
  document.getElementById('manual-form').onsubmit = (e) => { e.preventDefault(); const v = document.getElementById('manual-code').value.trim(); if (v) submitCode(v); };
  let scanner = null;
  document.getElementById('btn-camera').onclick = async function () {
    const box = document.getElementById('reader');
    if (scanner) { await scanner.stop().catch(() => {}); scanner = null; box.classList.add('hidden'); this.lastChild.textContent = 'Bật camera quét QR cá nhân'; return; }
    if (!window.Html5Qrcode) { await new Promise((ok, no) => { const s = document.createElement('script'); s.src = 'https://cdn.jsdelivr.net/npm/html5-qrcode@2.3.8/html5-qrcode.min.js'; s.onload = ok; s.onerror = no; document.head.appendChild(s); }).catch(() => VitaFlow.toast('Không tải được thư viện quét QR (cần internet).', 'error')); }
    if (!window.Html5Qrcode) return;
    box.classList.remove('hidden'); scanner = new Html5Qrcode('reader'); let busy = false;
    scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: 220 }, async (txt) => { if (busy) return; busy = true; await submitCode(txt); setTimeout(() => busy = false, 2500); })
      .catch(() => { VitaFlow.toast('Không mở được camera. Hãy cấp quyền hoặc nhập mã tay.', 'error'); box.classList.add('hidden'); scanner = null; });
    this.lastChild.textContent = 'Tắt camera';
  };
})();
