"""Kiểm thử các yêu cầu để lên CH Play / App Store:  python smoke_test_store.py"""
import os, re, subprocess, sys, tempfile, warnings, sqlite3
warnings.filterwarnings("ignore")
from app import create_app

tmp = tempfile.mkdtemp(); fails = []
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
IPAD_APP = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 VITAFLOWApp/1.0"
def check(name, cond, extra=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  {extra}" if not cond else ""))
    if not cond: fails.append(name)
app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp}/t.db", "UPLOAD_FOLDER": f"{tmp}/up"})

def client(ua="Mozilla/5.0 (Windows NT 10.0) Chrome/120"):
    c = app.test_client(); c.environ_base["HTTP_USER_AGENT"] = ua; return c
def tok(c, url="/login"): return re.search(r'name="csrf_token" value="([^"]+)"', c.get(url).get_data(as_text=True)).group(1)
def login(email, pw, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/120"):
    c = client(ua); c.tok = tok(c); r = c.post("/login", data={"email": email, "password": pw, "csrf_token": c.tok}); assert r.status_code == 302, email; return c
def post(c, url, data=None, **kw): d = dict(data or {}); d["csrf_token"] = c.tok; return c.post(url, data=d, **kw)

print("TRANG PHÁP LÝ"); 
for ua, label in (("Mozilla/5.0 (Windows NT 10.0) Chrome/120", "PC"), (IPHONE, "mobile")):
    c = client(ua)
    for u, key in (("/privacy", "Nghị định 13/2023"), ("/terms", "không khoan nhượng"), ("/support", "Báo cáo nội dung vi phạm")):
        r = c.get(u); check(f"{label} {u}", r.status_code == 200 and key in r.get_data(as_text=True))
    for u in ("/login", "/register"):
        t = c.get(u).get_data(as_text=True); check(f"{label} {u} có liên kết Quyền riêng tư & Điều khoản", "/privacy" in t and "/terms" in t)

print("ĐĂNG KÝ CẦN ĐỒNG Ý ĐIỀU KHOẢN"); c = client(); t = tok(c, "/register")
base = {"full_name": "Nguyễn Test", "email": "new1@x.vn", "password": "abcdef", "phone": "0900", "branch_id": 1, "csrf_token": t}
r = c.post("/register", data=base); check("Thiếu 'agree' -> không tạo tài khoản", r.status_code == 200 and "đồng ý" in r.get_data(as_text=True))
r = c.post("/register", data={**base, "agree": "1"}); check("Có 'agree' -> tạo & đăng nhập", r.status_code == 302)
from models import User, Post, Report, UserBlock, DeviceToken, BodyRecord, Message, Notification
with app.app_context(): check("Tài khoản tồn tại", User.query.filter_by(email="new1@x.vn").first() is not None)

print("BÁO CÁO / CHẶN / KIỂM DUYỆT")
a = login("mai.phuong@gmail.com", "member123"); b = login("lan.chi@gmail.com", "member123"); mg = login("manager@vitaflow.vn", "manager123")
post(a, "/app/post", {"body": "Nội dung xấu cần gỡ", "kind": "general"})
with app.app_context(): pid = Post.query.filter(Post.body == "Nội dung xấu cần gỡ").first().id; aid = User.query.filter_by(email="mai.phuong@gmail.com").first().id
t = b.get("/app/").get_data(as_text=True); check("Bảng tin có nút báo cáo & chặn", f'data-report-post="{pid}"' in t and f'data-block-user="{aid}"' in t)
check("Không tự báo cáo bài của mình", post(a, f"/app/post/{pid}/report", {"reason": "x"}).status_code == 400)
j = post(b, f"/app/post/{pid}/report", {"reason": "Phản cảm"}).get_json(); check("Báo cáo bài viết", j["ok"])
post(b, f"/app/post/{pid}/report", {"reason": "Phản cảm"})
with app.app_context(): check("Không nhân đôi báo cáo", Report.query.filter_by(post_id=pid, status="open").count() == 1)
t = mg.get("/manager/reports").get_data(as_text=True); check("Quản lý thấy báo cáo (PC)", "Nội dung xấu cần gỡ" in t and "Phản cảm" in t)
mgm = login("manager@vitaflow.vn", "manager123", IPHONE); t = mgm.get("/manager/reports").get_data(as_text=True); check("Quản lý thấy báo cáo (mobile)", "Nội dung xấu cần gỡ" in t and "is-mobile" in t)
check("Dashboard có thẻ báo cáo", "Báo cáo vi phạm" in mg.get("/manager/").get_data(as_text=True))
check("Hội viên không vào được /manager/reports", b.get("/manager/reports").status_code == 302)
j = post(b, f"/app/user/{aid}/block").get_json(); check("Chặn người dùng", j["ok"])
check("Bảng tin ẩn bài người đã chặn", "Nội dung xấu cần gỡ" not in b.get("/app/").get_data(as_text=True))
check("Không chặn Coach/Quản lý", post(b, "/app/user/1/block").status_code == 400)
check("Hồ sơ liệt kê người đã chặn + bỏ chặn", "Bỏ chặn" in b.get("/app/profile").get_data(as_text=True))
post(b, f"/app/user/{aid}/unblock"); check("Bỏ chặn", "Nội dung xấu cần gỡ" in b.get("/app/").get_data(as_text=True))
with app.app_context(): rid = Report.query.filter_by(post_id=pid).first().id
post(mg, f"/manager/reports/{rid}/suspend")
with app.app_context():
    check("Gỡ bài + khoá tài khoản", Post.query.get(pid) is None and User.query.get(aid).active is False)
    check("Tác giả nhận thông báo gỡ", Notification.query.filter(Notification.user_id == aid, Notification.text.like("%bị gỡ%")).count() == 1)
tk = client(); tk.tok = tok(tk); r = tk.post("/login", data={"email": "mai.phuong@gmail.com", "password": "member123", "csrf_token": tk.tok})
check("Tài khoản bị khoá không đăng nhập được", "tạm khoá" in r.get_data(as_text=True))
with app.app_context(): u = User.query.get(aid); u.active = True; from extensions import db; db.session.commit()
# comment report
a = login("mai.phuong@gmail.com", "member123"); post(a, "/app/post/1/comment", {"body": "bình luận lạ"}); 
with app.app_context(): from models import PostComment; cid = PostComment.query.filter_by(body="bình luận lạ").first().id
bj = post(b, f"/app/comment/{cid}/report", {"reason": "spam"}).get_json(); check("Báo cáo bình luận", bj["ok"])
with app.app_context(): rid2 = Report.query.filter_by(comment_id=cid).first().id
post(mg, f"/manager/reports/{rid2}/dismiss")
with app.app_context(): check("Bỏ qua báo cáo", Report.query.get(rid2).status == "dismissed")

print("XOÁ TÀI KHOẢN")
n = login("new1@x.vn", "abcdef"); post(n, "/app/post", {"body": "bài của n", "kind": "general"}); post(n, "/app/profile/record", {"weight_kg": 55, "waist_cm": 65})
post(n, "/api/device/register", {"token": "T" * 40, "platform": "android"})
with app.app_context(): nid = User.query.filter_by(email="new1@x.vn").first().id; check("Có dữ liệu trước khi xoá", Post.query.filter_by(user_id=nid).count() == 1 and BodyRecord.query.filter_by(user_id=nid).count() == 1 and DeviceToken.query.filter_by(user_id=nid).count() == 1)
t = n.get("/app/profile").get_data(as_text=True); check("Hồ sơ có mục Xoá tài khoản", "m-delete" in t and "/app/account/delete" in t)
nm = login("new1@x.vn", "abcdef", IPHONE); check("Mobile cũng có mục Xoá tài khoản", "/app/account/delete" in nm.get("/app/profile").get_data(as_text=True))
r = post(n, "/app/account/delete", {"password": "sai", "confirm": "1"}); 
with app.app_context(): check("Sai mật khẩu -> không xoá", User.query.get(nid) is not None)
r = post(n, "/app/account/delete", {"password": "abcdef"}); 
with app.app_context(): check("Thiếu xác nhận -> không xoá", User.query.get(nid) is not None)
r = post(n, "/app/account/delete", {"password": "abcdef", "confirm": "1"})
with app.app_context(): check("Xoá sạch dữ liệu", User.query.get(nid) is None and Post.query.filter_by(user_id=nid).count() == 0 and BodyRecord.query.filter_by(user_id=nid).count() == 0 and DeviceToken.query.filter_by(user_id=nid).count() == 0)
check("Sau khi xoá bị đăng xuất", n.get("/app/").status_code == 302)
tk = client(); tk.tok = tok(tk); r = tk.post("/login", data={"email": "new1@x.vn", "password": "abcdef", "csrf_token": tk.tok}); check("Không đăng nhập lại được", "chưa đúng" in r.get_data(as_text=True))
check("Coach không dùng được route xoá tài khoản hội viên", post(login("mai.anh@vitaflow.vn", "coach123"), "/app/account/delete", {"password": "coach123", "confirm": "1"}).status_code == 302)

print("PUSH NOTIFICATION")
u = login("mai.phuong@gmail.com", "member123")
check("Token quá ngắn bị từ chối", post(u, "/api/device/register", {"token": "abc"}).status_code == 400)
check("Đăng ký token", post(u, "/api/device/register", {"token": "A" * 50, "platform": "ios"}).get_json()["ok"])
post(u, "/api/device/register", {"token": "A" * 50, "platform": "ios"})
with app.app_context(): check("Không trùng token", DeviceToken.query.filter_by(token="A" * 50).count() == 1)
check("Huỷ đăng ký token", post(u, "/api/device/unregister", {"token": "A" * 50}).get_json()["ok"])
import push
with app.app_context():
    uid = User.query.filter_by(email="mai.phuong@gmail.com").first().id; db.session.add(DeviceToken(user_id=uid, token="GOOD" * 12, platform="android")); db.session.add(DeviceToken(user_id=uid, token="DEAD" * 12, platform="android")); db.session.commit()
sent = []
def fake(tokens, title, body, url): sent.append((tokens, body, url)); return ["DEAD" * 12]
push.dispatch(app, [(uid, "Chào bạn", "/app/")], sender=fake)
with app.app_context(): left = [d.token for d in DeviceToken.query.filter_by(user_id=uid)]
check("Gửi push tới mọi token & dọn token chết", len(sent) == 1 and len(sent[0][0]) == 2 and left == ["GOOD" * 12])
# ---- iOS: APNs
import json, httpx, jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
priv = ec.generate_private_key(ec.SECP256R1()); pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
kp = os.path.join(tmp, "AuthKey_TEST.p8"); open(kp, "wb").write(pem)
os.environ.update(APNS_KEY_PATH=kp, APNS_KEY_ID="KEYID12345", APNS_TEAM_ID="TEAMID1234", APNS_BUNDLE_ID="vn.VITAFLOW.app", APNS_USE_SANDBOX="1")
seen = []
def handler(req):
    seen.append(req)
    if req.url.path.endswith("IOS_DEAD" * 8): return httpx.Response(410, json={"reason": "Unregistered"})
    return httpx.Response(200)
push._client_factory = lambda: httpx.Client(transport=httpx.MockTransport(handler))
with app.app_context():
    db.session.add(DeviceToken(user_id=uid, token="IOS_GOOD" * 8, platform="ios")); db.session.add(DeviceToken(user_id=uid, token="IOS_DEAD" * 8, platform="ios")); db.session.commit()
push._jwt_cache.update(t=0, v=None); sent.clear()
push.dispatch(app, [(uid, "Xin chào iOS", "/app/")], sender=fake)
with app.app_context(): left = sorted(d.token for d in DeviceToken.query.filter_by(user_id=uid))
check("iOS gửi qua APNs (sandbox), Android qua FCM, không lẫn", len(seen) == 2 and all("api.sandbox.push.apple.com" in str(r.url) for r in seen) and len(sent) == 1 and len(sent[0][0]) == 1, f"{len(seen)} {len(sent)}")
hdr = seen[0].headers; claims = pyjwt.decode(hdr["authorization"].split()[1], priv.public_key(), algorithms=["ES256"])
check("JWT APNs đúng (ES256, kid, iss)", pyjwt.get_unverified_header(hdr["authorization"].split()[1])["kid"] == "KEYID12345" and claims["iss"] == "TEAMID1234" and hdr["apns-topic"] == "vn.VITAFLOW.app" and hdr["apns-push-type"] == "alert")
check("Payload APNs có alert + url", json.loads(seen[0].content)["aps"]["alert"]["body"] == "Xin chào iOS" and json.loads(seen[0].content)["url"] == "/app/")
check("Token iOS hết hạn (410) bị xoá", "IOS_DEAD" * 8 not in left and "IOS_GOOD" * 8 in left, str(left))
for k in ("APNS_KEY_PATH", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID", "APNS_USE_SANDBOX"): os.environ.pop(k)
sent.clear(); push.dispatch(app, [(uid, "x", "/")])
check("Chưa cấu hình FCM/APNs -> không gửi gì, không lỗi", not sent)
os.environ["FIREBASE_CREDENTIALS"] = "/tmp/x.json"; captured = []; orig = push.dispatch_async; push.dispatch_async = lambda ap, items: captured.extend(items)
c2 = login("mai.phuong@gmail.com", "member123"); post(c2, "/api/chat/send", {"peer": 2, "body": "alo coach"})
check("Gửi chat -> xếp hàng push cho Coach", any(i[0] == 2 and "alo coach" in i[1] for i in captured), str(captured))
captured.clear(); post(c2, "/app/water", {"ml": 250}); check("Không có thông báo thì không push", not captured)
push.dispatch_async = orig; os.environ.pop("FIREBASE_CREDENTIALS")

print("APP NATIVE (User-Agent VITAFLOWApp)")
c = login("mai.phuong@gmail.com", "member123", IPAD_APP); t = c.get("/app/").get_data(as_text=True)
check("iPad + VITAFLOWApp luôn dùng giao diện mobile", "is-mobile" in t)
check("Có meta vitaflow-auth & native.js", 'name="vitaflow-auth"' in t and "js/native.js" in t)
check("Ẩn lối chuyển giao diện PC (data-web-only)", 'data-web-only' in t)
check("Chưa đăng nhập: không có vitaflow-auth", 'name="vitaflow-auth"' not in client(IPAD_APP).get("/login").get_data(as_text=True))

print("AN TOÀN KHI CHẠY THẬT (APP_ENV=production)")
try: create_app({"APP_ENV": "production", "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp}/p0.db"}); ok = False
except RuntimeError: ok = True
check("Từ chối khởi động nếu thiếu SECRET_KEY", ok)
os.environ.pop("SEED_DEMO", None)
pa = create_app({"TESTING": True, "APP_ENV": "production", "SECRET_KEY": "k" * 40, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp}/p1.db", "UPLOAD_FOLDER": f"{tmp}/up2"})
with pa.app_context(): check("Không nạp dữ liệu demo", User.query.count() == 0)
pc = pa.test_client(); t = pc.get("/login").get_data(as_text=True); check("Trang đăng nhập không lộ tài khoản demo", "mai.anh@vitaflow.vn" not in t and "member123" not in t)
check("Cookie phiên có cờ Secure", pa.config["SESSION_COOKIE_SECURE"] is True)
env = {**os.environ, "APP_ENV": "production", "SECRET_KEY": "k" * 40, "DATABASE_URL": f"sqlite:///{tmp}/p2.db"}
r1 = subprocess.run([sys.executable, "manage.py", "create-branch", "--name", "Cơ sở thật"], env=env, capture_output=True, text=True)
r2 = subprocess.run([sys.executable, "manage.py", "create-manager", "--email", "boss@congty.vn", "--name", "Chủ phòng tập", "--password", "MatKhau#12345"], env=env, capture_output=True, text=True)
r3 = subprocess.run([sys.executable, "manage.py", "create-manager", "--email", "x@y.vn", "--name", "X", "--password", "123"], env=env, capture_output=True, text=True)
rows = sqlite3.connect(f"{tmp}/p2.db").execute("select email, role from user").fetchall()
check("manage.py tạo cơ sở + Quản lý đầu tiên (không có demo)", r1.returncode == 0 and r2.returncode == 0 and rows == [("boss@congty.vn", "manager")], f"{r1.stderr[-200:]} {r2.stderr[-200:]} {rows}")
check("manage.py từ chối mật khẩu yếu", r3.returncode != 0)
print("\nKẾT QUẢ STORE:", "TẤT CẢ ĐẠT" if not fails else f"{len(fails)} LỖI: {fails}")
sys.exit(1 if fails else 0)
