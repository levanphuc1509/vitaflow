/* Cửa hàng nạp gói (dùng chung PC & mobile) */
const D = JSON.parse(document.getElementById('shop-data').textContent), $ = (s) => document.querySelector(s), fmt = (n) => Math.round(n).toLocaleString('vi-VN') + 'đ';
function fill() {
  const b = D.branches[$('#sel-branch').value] || { shifts: [], coaches: [] };
  $('#sel-shift').innerHTML = '<option value="">Linh hoạt (chưa chọn ca)</option>' + b.shifts.map(s => '<option value="' + s.id + '">' + VitaFlow.esc(s.label) + (s.title ? ' · ' + VitaFlow.esc(s.title) : '') + '</option>').join('');
  $('#sel-coach').innerHTML = '<option value="">Không chọn</option>' + b.coaches.map(c => '<option value="' + c.id + '">' + VitaFlow.esc(c.name) + (c.spec ? ' · ' + VitaFlow.esc(c.spec) : '') + '</option>').join('');
}
function calc() {
  const pid = (document.querySelector('[name=plan_id]:checked') || {}).value, p = D.plans[pid];
  const v = document.querySelector('[name=voucher_id]:checked'), pct = v && v.dataset.percent ? +v.dataset.percent : 0;
  const needCoach = p && p.kind !== 'gym'; $('#sel-coach').required = !!needCoach; $('#coach-hint').classList.toggle('hidden', !needCoach);
  $('#sum-plan').textContent = p ? p.name : '—'; const price = p ? p.price : 0, disc = Math.round(price * pct / 100 / 1000) * 1000;
  $('#sum-price').textContent = fmt(price); $('#sum-disc').textContent = '-' + fmt(price * pct / 100); $('#sum-total').textContent = fmt(price - price * pct / 100);
}
$('#sel-branch').onchange = fill; $('#shop').addEventListener('change', calc); fill(); calc();
document.querySelectorAll('.kind-tab').forEach(t => t.onclick = () => {
  document.querySelectorAll('.kind-tab').forEach(x => x.classList.toggle('tab-active', x === t));
  document.querySelectorAll('.plan-card').forEach(c => c.style.display = (t.dataset.kind === 'all' || c.dataset.kind === t.dataset.kind) ? '' : 'none'); });
