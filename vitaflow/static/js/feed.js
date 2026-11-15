/* Bảng tin: thả tim, nước uống, kỳ nghỉ sinh lý (dùng chung PC & mobile) */
document.querySelectorAll('[data-like]').forEach(b => b.onclick = async () => {
  const j = await VitaFlow.post('/app/post/' + b.dataset.like + '/like'); if (!j.ok) return;
  b.classList.toggle('text-rose-600', j.liked); b.classList.toggle('text-muted', !j.liked);
  b.querySelector('.material-symbols-outlined').style.fontVariationSettings = "'FILL' " + (j.liked ? 1 : 0); b.querySelector('.like-count').textContent = j.count; });
document.querySelectorAll('[data-water]').forEach(b => b.onclick = async () => {
  const j = await VitaFlow.post('/app/water', { ml: b.dataset.water }); if (!j.ok) return;
  document.getElementById('water-ml').textContent = j.ml; document.getElementById('water-bar').style.width = Math.min(100, Math.round(j.ml / j.goal * 100)) + '%'; });
document.getElementById('period').onclick = async function () {
  const j = await VitaFlow.post('/app/period-mode'); if (!j.ok) return;
  this.className = 'w-12 h-7 rounded-full transition relative ' + (j.on ? 'bg-primary-dark' : 'bg-slate-300');
  this.firstElementChild.className = 'absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-all ' + (j.on ? 'left-[22px]' : 'left-0.5');
  VitaFlow.toast(j.on ? 'Đã bật kỳ nghỉ sinh lý. Streak của bạn được bảo vệ 💗' : 'Đã tắt chế độ kỳ nghỉ sinh lý.'); };
