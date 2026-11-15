// Đặt địa chỉ máy chủ thật và (tuỳ chọn) bundle id / phiên bản cho app.
//   node scripts/configure.js --url https://app.tencongty.vn [--appId vn.VITAFLOW.app] [--name "VitaFlow"] [--ua 1.0.0]
const fs = require('fs');
const arg = (k) => { const i = process.argv.indexOf('--' + k); return i > -1 ? process.argv[i + 1] : null; };
const url = arg('url');
if (!url || !/^https:\/\/[a-z0-9.-]+(:\d+)?\/?$/i.test(url)) { console.error('Cần --url https://ten-mien (bắt buộc HTTPS, không có đường dẫn phía sau).'); process.exit(1); }
const clean = url.replace(/\/$/, ''), host = new URL(clean).host;
const cfg = JSON.parse(fs.readFileSync('capacitor.config.json', 'utf8'));
cfg.server.url = clean; cfg.server.allowNavigation = [host];
if (arg('appId')) cfg.appId = arg('appId');
if (arg('name')) cfg.appName = arg('name');
if (arg('ua')) cfg.appendUserAgent = 'VITAFLOWApp/' + arg('ua');
fs.writeFileSync('capacitor.config.json', JSON.stringify(cfg, null, 2) + '\n');
for (const f of ['www/index.html', 'www/offline.html']) {
  let s = fs.readFileSync(f, 'utf8'); s = s.replace(/https:\/\/[a-z0-9.-]+(:\d+)?(?=["'])/gi, clean); fs.writeFileSync(f, s);
}
console.log('Đã cấu hình:', clean, '| appId:', cfg.appId);
