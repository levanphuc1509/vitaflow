"""Kiểm thử giao diện mobile chạy song song với PC:  python smoke_test_mobile.py"""
import re, sys, tempfile, os, warnings
warnings.filterwarnings("ignore")
from datetime import date, timedelta
from app import create_app

tmp = tempfile.mkdtemp()
app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp}/t.db", "UPLOAD_FOLDER": f"{tmp}/up"})
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
IPAD = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
fails = []

def check(name, cond, extra=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  {extra}" if not cond else ""))
    if not cond: fails.append(name)

def client(email, pw, ua):
    c = app.test_client(); c.environ_base["HTTP_USER_AGENT"] = ua
    tok = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").get_data(as_text=True)).group(1)
    assert c.post("/login", data={"email": email, "password": pw, "csrf_token": tok}).status_code == 302
    c.tok = tok; return c

def post(c, url, data=None, **kw):
    d = dict(data or {}); d["csrf_token"] = c.tok; return c.post(url, data=d, **kw)

def sweep(c, urls, mobile=True):
    for u in urls:
        r = c.get(u); t = r.get_data(as_text=True)
        ok = r.status_code == 200 and (("is-mobile" in t) == mobile)
        check(f"{'M' if mobile else 'D'} {u} -> {r.status_code}", ok, (t[:200] if r.status_code >= 500 else f"is-mobile={'is-mobile' in t}"))

MGR = ["/manager/", "/manager/staff", "/manager/staff?q=mai", "/manager/members", "/manager/members?rank=Gold&coach=2", "/manager/shifts", "/manager/shifts?shift=3",
       "/manager/nutrition", "/manager/nutrition?peer=2", "/manager/nutrition?peer=5", "/manager/nutrition?shift=3", "/manager/rewards", "/manager/rewards?tab=expiring",
       "/manager/rewards?tab=freeze", "/manager/rewards?tab=gift"]
COACH = ["/coach/", "/coach/progress", "/coach/checkin", "/coach/checkin?shift=3", "/coach/nutrition", "/coach/nutrition?peer=5", "/coach/nutrition?shift=3", "/coach/rewards"]
MEMBER = ["/app/", "/app/profile", "/app/schedule", "/app/schedule?m=2026-12&d=2026-12-05", "/app/nutrition", "/app/qr", "/app/messages", "/app/messages?peer=2",
          "/app/messages?shift=3", "/app/rewards", "/app/membership", "/app/shop", "/app/shop?plan=6"]

print("PUBLIC"); 
for ua, label, mob in ((IPHONE, "iPhone", True), (ANDROID, "Android", True), (IPAD, "iPad", False), (DESKTOP, "Desktop", False)):
    c = app.test_client(); c.environ_base["HTTP_USER_AGENT"] = ua
    for u in ("/", "/login", "/register"):
        t = c.get(u).get_data(as_text=True); check(f"{label}: {u} -> {'mobile' if mob else 'PC'}", ("is-mobile" in t) == mob)
c = app.test_client(); c.environ_base["HTTP_USER_AGENT"] = IPHONE
c.get("/view/desktop?next=/login"); check("Chọn tay 'desktop' trên iPhone được ghi nhớ", "is-mobile" not in c.get("/login").get_data(as_text=True))
c.get("/view/mobile?next=/login"); check("Chọn lại 'mobile'", "is-mobile" in c.get("/login").get_data(as_text=True))
r = c.get("/view/mobile?next=http://evil.example/x"); check("Chặn open-redirect ở /view", r.headers["Location"] in ("/", "http://localhost/") or "evil" not in r.headers["Location"])
c2 = app.test_client(); c2.environ_base["HTTP_USER_AGENT"] = DESKTOP; c2.get("/login?view=mobile")
check("?view=mobile ép giao diện mobile trên PC", "is-mobile" in c2.get("/login").get_data(as_text=True))

print("MANAGER (mobile)"); m = client("manager@vitaflow.vn", "manager123", IPHONE); sweep(m, MGR)
t = m.get("/manager/").get_data(as_text=True); check("Bottom nav quản lý có 5 mục", t.count('class="') and all(x in t for x in ("Tổng Quan", "Nhân Sự", "Hồ Sơ Body", "Ca Tập", "Chat &amp; Quà")))
check("Chat thread ẩn bottom nav", 'class="m-nav"' not in m.get("/manager/nutrition?peer=5").get_data(as_text=True))
check("Quản lý vẫn bị chặn khỏi /coach (mobile)", m.get("/coach/").status_code == 302)
check("Popup hồ sơ hội viên", "Trần Mai Phương" in m.get("/manager/members/5/card").get_data(as_text=True))
print("COACH (mobile)"); c = client("mai.anh@vitaflow.vn", "coach123", ANDROID); sweep(c, COACH)
t = c.get("/coach/nutrition?peer=5").get_data(as_text=True); check("Coach chat: nút chuyển tiếp + chấm điểm", "m-escalate" in t and "/coach/meal/5/" in t)
t = c.get("/coach/checkin").get_data(as_text=True); check("Coach QR: đủ phần tử cho checkin.js", all(x in t for x in ('id="checkin-root"', 'id="qr-holder"', 'id="privacy"', 'id="btn-camera"', 'id="manual-form"', 'id="m-exit"', 'id="exit-form"')))
check("Coach không xem học viên của coach khác", c.get("/coach/students/6/card").status_code == 403)
print("MEMBER (mobile)"); u = client("mai.phuong@gmail.com", "member123", IPHONE); sweep(u, MEMBER)
t = u.get("/app/").get_data(as_text=True); check("Bottom nav hội viên + nút QR giữa", all(x in t for x in ("Bảng Tin", "Lịch Ca", "Quét QR", "AI Coach", "Hồ Sơ &amp; Nạp")) and "fab" in t)
t = u.get("/app/shop").get_data(as_text=True); check("Shop: có đủ id cho shop.js", all(x in t for x in ('id="sel-branch"', 'id="sum-total"', 'id="shop-data"', 'name="plan_id"')))
t = u.get("/app/shop?plan=6").get_data(as_text=True); check("Shop ?plan= chọn sẵn gói", re.search(r'value="6"[^>]*checked', t) is not None)
check("Member bị chặn khỏi /manager (mobile)", u.get("/manager/").status_code == 302)

print("CHỨC NĂNG GIỐNG PC (gọi bằng UA mobile)")
sid = 3
j = post(u, "/app/nutrition/generate", {"age": 30, "height": 160, "weight": 55, "activity": "vua", "goal": "giam_can"}).get_json(); check("Tạo thực đơn AI", j["ok"] and "kcal" in j["html"])
check("Đổi món / ăn chuẩn AI", post(u, "/app/nutrition/swap", {"meal": "bua_trua", "index": 0}).get_json()["ok"] and post(u, "/app/nutrition/followed", {"meal": "bua_sang"}).get_json()["ok"])
check("Đăng bài + thả tim + nước + kỳ nghỉ", post(u, "/app/post", {"body": "m", "kind": "general"}).status_code == 302 and post(u, "/app/post/1/like").get_json()["ok"] and post(u, "/app/water", {"ml": 250}).get_json()["ok"] and post(u, "/app/period-mode").get_json()["ok"])
d = (date.today() + timedelta(days=3)).isoformat()
check("Đặt chỗ ca", post(u, "/app/schedule/book", {"shift_id": sid, "day": d}).status_code == 302)
r = post(u, "/app/shop/checkout", {"plan_id": 6, "branch_id": 1, "shift_id": sid, "coach_id": 2, "voucher_id": 1}); loc = r.headers["Location"]
page = u.get(loc).get_data(as_text=True); check("Checkout -> trang QR (mobile)", "is-mobile" in page and "VF HV102 CB3T" in page and "vietqr.io" in page)
post(u, loc.replace("/app/shop/order/", "/app/shop/order/") + "/claim")
j = post(u, "/api/chat/send", {"peer": 2, "body": "Chào coach (mobile)"}).get_json(); check("Chat gửi/nhận", j["ok"] and any("mobile" in x["body"] for x in u.get("/api/chat/messages?peer=2&after=0").get_json()["messages"]))
check("Xin bảo lưu", post(u, "/app/membership/freeze", {"days": 10, "reason": "x"}).status_code == 302)
j = post(c, "/coach/checkin/scan", {"code": "HV-111", "shift_id": sid}).get_json(); check("Coach quét/nhập mã hội viên", j["ok"])
check("Coach chuyển tiếp + chấm điểm + tặng quà", post(c, "/api/chat/escalate", {"member_id": 5, "reason": "x"}).get_json()["ok"] and post(c, "/coach/meal/5/bua_trua/score", {"score": 9}).status_code == 302 and post(c, "/coach/rewards/gift", {"member_id": 5, "percent": 5}).status_code == 302)
from models import Order
with app.app_context(): oid = Order.query.filter_by(transfer_code="VF HV102 CB3T").first().id
check("Quản lý xác nhận đơn", post(m, f"/manager/rewards/order/{oid}/confirm").status_code == 302)
check("Quản lý thêm/xoá Coach", post(m, "/manager/staff/add", {"full_name": "M Test", "email": "m.test@x.vn", "password": "abcdef", "branch_id": 1}).status_code == 302)
check("Quản lý lưu ca", post(m, "/manager/shifts/save", {"name": "Ca 9", "start": "20:00", "end": "21:00", "capacity": 10, "branch_id": 1}).status_code == 302)
check("Đăng xuất (POST)", post(u, "/logout").status_code == 302 and u.get("/app/").status_code == 302)
print("\nKẾT QUẢ MOBILE:", "TẤT CẢ ĐẠT" if not fails else f"{len(fails)} LỖI: {fails}")
sys.exit(1 if fails else 0)
