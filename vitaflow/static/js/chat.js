/* Messenger dùng chung cho Manager / Coach / Member. Cần #chat có data-peer hoặc data-shift. */
(function () {
  const box = document.getElementById('chat'); if (!box) return;
  const list = document.getElementById('chat-list'), form = document.getElementById('chat-form');
  const q = box.dataset.peer ? 'peer=' + box.dataset.peer : 'shift=' + box.dataset.shift;
  let last = 0, busy = false;
  const bubble = (m) => {
    const wrap = document.createElement('div'); wrap.className = 'flex gap-2 ' + (m.mine ? 'justify-end' : 'justify-start');
    let inner = '';
    if (m.image) inner += '<a href="' + m.image + '" target="_blank"><img src="' + m.image + '" class="rounded-xl mb-1 max-h-56 object-cover" alt="Ảnh"></a>';
    if (m.body) inner += VitaFlow.esc(m.body);
    wrap.innerHTML = '<div class="' + (m.mine ? 'items-end' : 'items-start') + ' flex flex-col max-w-[82%]">' +
      (!m.mine && box.dataset.shift ? '<span class="text-[11px] font-semibold text-muted ml-1">' + VitaFlow.esc(m.sender) + '</span>' : '') +
      '<div class="bubble ' + (m.mine ? 'bubble-me' : 'bubble-them') + '">' + inner + '</div><span class="text-[10px] text-muted mx-1 mt-0.5">' + m.time + '</span></div>';
    return wrap;
  };
  async function poll() {
    if (busy) return; busy = true;
    try {
      const r = await fetch('/api/chat/messages?' + q + '&after=' + last, { headers: { Accept: 'application/json' } });
      const j = await r.json();
      if (j.ok && j.messages.length) {
        const nearBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 120 || last === 0;
        j.messages.forEach(m => { list.appendChild(bubble(m)); last = Math.max(last, m.id); });
        if (nearBottom) list.scrollTop = list.scrollHeight;
      }
    } catch (e) {} finally { busy = false; }
  }
  poll(); setInterval(poll, 4000);
  if (form) {
    const file = form.querySelector('input[type=file]'), preview = document.getElementById('chat-file-name');
    file && file.addEventListener('change', () => { preview.textContent = file.files[0] ? file.files[0].name : ''; });
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(form); if (box.dataset.peer) fd.set('peer', box.dataset.peer); else fd.set('shift', box.dataset.shift);
      const body = fd.get('body'); if (!String(body).trim() && !(file && file.files[0])) return;
      const j = await VitaFlow.post('/api/chat/send', fd);
      if (j.ok) { form.reset(); preview && (preview.textContent = ''); poll(); } else VitaFlow.toast(j.error || 'Không gửi được', 'error');
    });
  }
  const esc = document.getElementById('escalate-form');
  if (esc) esc.addEventListener('submit', async (e) => {
    e.preventDefault(); const j = await VitaFlow.post('/api/chat/escalate', new FormData(esc));
    if (j.ok) { VitaFlow.toast(j.message); esc.closest('.modal').classList.add('hidden'); esc.reset(); } else VitaFlow.toast(j.error, 'error');
  });
})();
