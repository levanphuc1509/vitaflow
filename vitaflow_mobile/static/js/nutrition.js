/* AI Coach & nhật ký bữa ăn (dùng chung PC & mobile) */
const area = document.getElementById('menu-area');
function showStats(s) { if (!s) return; document.querySelectorAll('[data-hero-kcal]').forEach(e => { e.firstChild.textContent = Math.round(s.calo_muc_tieu); }); const b = document.getElementById('stats-box'); b.classList.remove('hidden');
  ['bmr', 'tdee', 'calo_muc_tieu'].forEach(k => b.querySelector('[data-stat=' + k + ']').textContent = Math.round(s[k]));
  b.querySelector('[data-stat=macro]').textContent = s.macro.protein_g + ' / ' + s.macro.carb_g + ' / ' + s.macro.fat_g + 'g'; }
document.getElementById('nutri-form').onsubmit = async (e) => {
  e.preventDefault(); const btn = document.getElementById('btn-gen'), fd = new FormData(e.target); fd.set('fresh', area.querySelector('[data-followed],[data-swap]') ? '1' : '');
  btn.disabled = true; btn.lastElementChild.textContent = 'AI đang chọn món…';
  const j = await VitaFlow.post('/app/nutrition/generate', fd); btn.disabled = false; btn.lastElementChild.textContent = 'Tạo lại thực đơn';
  if (j.ok) { area.innerHTML = j.html; showStats(j.stats); document.querySelectorAll('.modal').forEach(m => m.classList.add('hidden')); } else VitaFlow.toast(j.error, 'error'); };
area.addEventListener('click', async (e) => {
  const sw = e.target.closest('[data-swap]'), fl = e.target.closest('[data-followed]'), ph = e.target.closest('[data-photo-meal]');
  if (ph) document.getElementById('photo-meal').value = ph.dataset.photoMeal;
  if (sw) { sw.disabled = true; const j = await VitaFlow.post('/app/nutrition/swap', { meal: sw.dataset.meal, index: sw.dataset.index }); j.ok ? area.innerHTML = j.html : (VitaFlow.toast(j.error, 'error'), sw.disabled = false); }
  if (fl) { const j = await VitaFlow.post('/app/nutrition/followed', { meal: fl.dataset.meal });
    if (j.ok) { fl.outerHTML = '<span class="btn btn-ghost btn-sm cursor-default"><span class="material-symbols-outlined text-[18px]" style="font-variation-settings:\'FILL\' 1">check_circle</span>Đã ăn chuẩn theo AI</span>'; j.gained && VitaFlow.toast('+' + j.gained + ' điểm chuyên cần! 🎉'); } }
});
