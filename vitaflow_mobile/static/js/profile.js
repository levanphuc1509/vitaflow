/* Hồ sơ & nhật ký body (dùng chung PC & mobile) */
(function () {
  const cd = document.getElementById('chart-data'), cv = document.getElementById('chart');
  if (cd && cv && window.Chart) { const CD = JSON.parse(cd.textContent);
new Chart(document.getElementById('chart'), { type: 'line', data: { labels: CD.labels, datasets: [
  { label: 'Cân nặng (kg)', data: CD.weight, borderColor: '#DB2777', backgroundColor: 'rgba(244,114,182,.18)', fill: true, tension: .35, yAxisID: 'y' },
  { label: 'Vòng eo (cm)', data: CD.waist, borderColor: '#8B5CF6', backgroundColor: 'rgba(167,139,250,.15)', fill: true, tension: .35, yAxisID: 'y1' }] },
  options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'bottom' } },
    scales: { y: { position: 'left', title: { display: true, text: 'kg' } }, y1: { position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'cm' } } } } });

  }
})();
document.getElementById('vis').onchange = async function () { const j = await VitaFlow.post('/app/profile/visibility', { visibility: this.value }); j.ok && VitaFlow.toast('Đã cập nhật quyền xem ảnh.'); };
const uf = document.getElementById('unlock-form');
if (uf) uf.onsubmit = async (e) => { e.preventDefault(); const j = await VitaFlow.post('/app/profile/unlock', { password: document.getElementById('unlock-pass').value }); j.ok ? location.reload() : document.getElementById('unlock-err').classList.remove('hidden'); };
const bl = document.getElementById('btn-lock'); if (bl) bl.onclick = async () => { await VitaFlow.post('/app/profile/unlock', { lock: 1 }); location.reload(); };
