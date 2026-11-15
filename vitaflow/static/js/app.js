/* VITAFLOW - JS dùng chung: modal, toast, CSRF, thông báo, hover-card, sao chép, đồng hồ */
(function () {
  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;
  const VitaFlow = window.VitaFlow = {
    csrf,
    async post(url, data) {
      const body = data instanceof FormData ? data : new URLSearchParams(data || {});
      const res = await fetch(url, { method: 'POST', body, headers: { 'X-CSRF-Token': csrf(), 'Accept': 'application/json' } });
      let json = {};
      try { json = await res.json(); } catch (e) {}
      if (!res.ok && json.ok === undefined) json = { ok: false, error: 'Có lỗi xảy ra (' + res.status + ').' };
      return json;
    },
    toast(msg, type) {
      const el = document.createElement('div');
      el.className = 'toast toast-' + (type || 'success');
      el.innerHTML = '<span class="material-symbols-outlined text-[20px]">' + (type === 'error' ? 'error' : 'check_circle') + '</span><span></span>';
      el.lastChild.textContent = msg;
      document.getElementById('toasts').appendChild(el);
      setTimeout(() => el.remove(), 4000);
    },
    esc(s) { const d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; },
  };

  // Toast tự tắt
  document.querySelectorAll('#toasts .toast').forEach(t => setTimeout(() => t.remove(), 5000));

  // Modal
  document.addEventListener('click', (e) => {
    const open = e.target.closest('[data-modal-open]');
    if (open) { const m = document.getElementById(open.dataset.modalOpen); if (m) { m.classList.remove('hidden'); const f = m.querySelector('input:not([type=hidden]),select,textarea'); f && setTimeout(() => f.focus(), 50); } return; }
    if (e.target.closest('[data-modal-close]')) { const m = e.target.closest('.modal'); m && m.classList.add('hidden'); }
    const st = e.target.closest('[data-side-toggle]');
    if (st) { document.getElementById('sidebar').classList.toggle('-translate-x-full'); document.getElementById('side-overlay').classList.toggle('hidden'); }
    const cp = e.target.closest('[data-copy]');
    if (cp) { navigator.clipboard && navigator.clipboard.writeText(cp.dataset.copy).then(() => VitaFlow.toast('Đã sao chép: ' + cp.dataset.copy)); }
    const cf = e.target.closest('[data-confirm]');
    if (cf && !confirm(cf.dataset.confirm)) e.preventDefault();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') document.querySelectorAll('.modal:not(.hidden)').forEach(m => m.classList.add('hidden')); });

  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (!(form instanceof HTMLFormElement) || e.defaultPrevented || form.target === '_blank' || form.hasAttribute('data-no-loading')) return;
    if (form.dataset.submitting === 'true') { e.preventDefault(); return; }
    const submitter = e.submitter || form.querySelector('button[type="submit"],button:not([type]),input[type="submit"]');
    if (!submitter || submitter.disabled) return;
    form.dataset.submitting = 'true';
    form.setAttribute('aria-busy', 'true');
    submitter.setAttribute('aria-disabled', 'true');
    const spinner = document.createElement('span');
    spinner.className = 'submit-spinner';
    spinner.setAttribute('aria-hidden', 'true');
    if (submitter instanceof HTMLButtonElement) submitter.prepend(spinner);
    else submitter.insertAdjacentElement('afterend', spinner);
  });

  // Đánh dấu đã đọc thông báo (giao diện mobile)
  document.addEventListener('click', (e) => { const m = e.target.closest('[data-mark-read]'); if (m) { VitaFlow.post('/api/notifications/read'); document.querySelectorAll('[data-notes-badge]').forEach(b => b.remove()); } });

  // Chuông thông báo
  const bell = document.getElementById('bell'), panel = document.getElementById('bell-panel');
  if (bell) {
    bell.addEventListener('click', (e) => {
      e.stopPropagation(); panel.classList.toggle('hidden');
      const c = document.getElementById('bell-count');
      if (c) { VitaFlow.post('/api/notifications/read'); c.remove(); }
    });
    document.addEventListener('click', (e) => { if (!panel.contains(e.target)) panel.classList.add('hidden'); });
  }

  // Hover-card hồ sơ hội viên (hover trên desktop, click trên điện thoại)
  const cache = {}; let card = null, timer = null;
  function hide() { if (card) { card.remove(); card = null; } const bd = document.getElementById('m-backdrop'); bd && bd.remove(); }
  async function show(el) {
    const url = el.dataset.cardUrl; if (!url) return;
    if (!cache[url]) { try { cache[url] = await (await fetch(url)).text(); } catch (e) { return; } }
    hide();
    card = document.createElement('div'); card.className = 'hover-card'; card.innerHTML = cache[url];
    if (document.body.classList.contains('is-mobile')) { const bd = document.createElement('div'); bd.id = 'm-backdrop'; bd.className = 'm-backdrop'; bd.onclick = hide; document.body.appendChild(bd); document.body.appendChild(card); return; }
    document.body.appendChild(card);
    const r = el.getBoundingClientRect(), w = card.offsetWidth, h = card.offsetHeight;
    let x = r.right + 12; if (x + w > innerWidth - 8) x = Math.max(8, r.left - w - 12);
    let y = Math.min(Math.max(8, r.top - 20), innerHeight - h - 8);
    if (innerWidth < 640) { x = (innerWidth - w) / 2; y = Math.max(8, (innerHeight - h) / 2); }
    card.style.left = x + 'px'; card.style.top = y + 'px';
    card.addEventListener('mouseenter', () => clearTimeout(timer));
    card.addEventListener('mouseleave', () => { timer = setTimeout(hide, 150); });
  }
  const canHover = matchMedia('(hover:hover)').matches;
  document.addEventListener('mouseover', (e) => { if (!canHover) return; const el = e.target.closest('[data-card-url]'); if (el) { clearTimeout(timer); timer = setTimeout(() => show(el), 250); } });
  document.addEventListener('mouseout', (e) => { if (!canHover) return; if (e.target.closest('[data-card-url]')) { clearTimeout(timer); timer = setTimeout(hide, 250); } });
  document.addEventListener('click', (e) => { const el = e.target.closest('[data-card-url]'); if (el && !canHover) { show(el); return; } if (card && !card.contains(e.target)) hide(); });

  // Đồng hồ thời gian thực
  const clock = document.getElementById('live-clock');
  if (clock) { const t = () => { const d = new Date(); clock.textContent = d.toLocaleTimeString('vi-VN') + ' · ' + d.toLocaleDateString('vi-VN', { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' }); }; t(); setInterval(t, 1000); }

  // Thời tiết (Open-Meteo, không cần API key)
  const wx = document.getElementById('weather');
  if (wx) {
    const codes = { 0: ['Trời quang', 'wb_sunny'], 1: ['Ít mây', 'wb_sunny'], 2: ['Có mây', 'partly_cloudy_day'], 3: ['Nhiều mây', 'cloud'], 45: ['Sương mù', 'foggy'], 61: ['Mưa nhẹ', 'rainy'], 63: ['Mưa', 'rainy'], 65: ['Mưa to', 'rainy'], 80: ['Mưa rào', 'rainy'], 95: ['Dông', 'thunderstorm'] };
    fetch('https://api.open-meteo.com/v1/forecast?latitude=' + wx.dataset.lat + '&longitude=' + wx.dataset.lng + '&current=temperature_2m,weather_code,relative_humidity_2m&timezone=auto')
      .then(r => r.json()).then(j => { const c = j.current, k = codes[c.weather_code] || ['Thời tiết', 'partly_cloudy_day'];
        wx.innerHTML = '<span class="material-symbols-outlined text-[28px] text-primary">' + k[1] + '</span><div><div class="font-head text-xl font-bold">' + Math.round(c.temperature_2m) + '°C</div><div class="text-xs text-muted">' + k[0] + ' · ẩm ' + c.relative_humidity_2m + '%</div></div>'; })
      .catch(() => { wx.innerHTML = '<span class="text-xs text-muted">Không tải được thời tiết</span>'; });
  }

  // Lọc danh sách theo ô tìm kiếm (data-filter="#selector")
  document.querySelectorAll('[data-filter]').forEach(inp => inp.addEventListener('input', () => {
    const q = inp.value.toLowerCase().trim();
    document.querySelectorAll(inp.dataset.filter).forEach(el => { el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none'; });
  }));
})();
