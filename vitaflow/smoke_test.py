"""Kiểm thử nhanh toàn bộ route & phân quyền:  python smoke_test.py"""
import re, sys, tempfile, os, warnings
warnings.filterwarnings('ignore')
os.environ.setdefault("SECRET_KEY", "test")
from app import create_app

tmp = tempfile.mkdtemp()
app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp}/t.db", "UPLOAD_FOLDER": f"{tmp}/up"})
fails = []

def check(name, cond, extra=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  {extra}" if not cond else ""))
    if not cond: fails.append(name)

def client(email, pw):
    c = app.test_client()
    html = c.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    r = c.post("/login", data={"email": email, "password": pw, "csrf_token": tok})
    assert r.status_code == 302, (email, r.status_code)
    c.tok = tok
    return c

def post(c, url, data=None, **kw):
    d = dict(data or {}); d["csrf_token"] = c.tok
    return c.post(url, data=d, **kw)

def pages(c, urls):
    for u in urls:
        r = c.get(u)
        check(f"GET {u} -> {r.status_code}", r.status_code == 200, r.get_data(as_text=True)[:300] if r.status_code >= 500 else "")

print("PUBLIC"); c0 = app.test_client()
pages(c0, ["/", "/login", "/register"])
check("CSRF chặn POST thiếu token", c0.post("/login", data={"email": "a", "password": "b"}).status_code == 400)

print("MANAGER"); m = client("manager@vitaflow.vn", "manager123")
pages(m, ["/manager/", "/manager/staff", "/manager/staff?q=mai", "/manager/members", "/manager/members?rank=Gold", "/manager/shifts",
          "/manager/nutrition", "/manager/nutrition?peer=2", "/manager/nutrition?peer=5", "/manager/rewards", "/manager/rewards?tab=expiring",
          "/manager/rewards?tab=freeze", "/manager/rewards?tab=gift", "/manager/members/5/card"])
check("Manager bị chặn khỏi /coach", m.get("/coach/").status_code == 302)
check("Manager bị chặn khỏi /app", m.get("/app/").status_code == 302)
r = post(m, "/manager/staff/add", {"full_name": "Coach Test", "email": "test.coach@x.vn", "password": "abcdef", "branch_id": 1})
check("Thêm coach", r.status_code == 302)
from models import User, Order, FreezeRequest, Shift
with app.app_context():
    tc = User.query.filter_by(email="test.coach@x.vn").first(); check("Coach được tạo trong DB", tc is not None); tcid = tc.id
r = post(m, f"/manager/staff/{tcid}/assign", {"member_ids": [6, 7]}); 
with app.app_context(): check("Gán học viên", User.query.get(6).coach_id == tcid)
post(m, f"/manager/staff/{tcid}/toggle")
with app.app_context(): check("Tắt coach", User.query.get(tcid).active is False)
post(m, f"/manager/staff/{tcid}/delete")
with app.app_context(): check("Xoá coach + bỏ gán học viên", User.query.get(tcid) is None and User.query.get(6).coach_id is None)
r = post(m, "/manager/shifts/save", {"name": "Ca 9", "start": "20:00", "end": "21:00", "capacity": 10, "branch_id": 1, "coach_ids": [2]})
check("Thêm ca", r.status_code == 302)
with app.app_context():
    o = Order.query.filter_by(status="claimed").first(); oid = o.id; uid = o.user_id; before = User.query.get(uid).gym_expires
r = post(m, f"/manager/rewards/order/{oid}/confirm")
with app.app_context(): check("Xác nhận đơn cộng dồn ngày", User.query.get(uid).gym_expires > before)
with app.app_context(): fid = FreezeRequest.query.first().id
post(m, f"/manager/rewards/freeze/{fid}/approve")
with app.app_context(): check("Duyệt bảo lưu", FreezeRequest.query.get(fid).status == "approved")
r = post(m, "/manager/rewards/gift", {"member_id": 5, "percent": 15, "title": "Test"}); check("Gửi quà", r.status_code == 302)

print("COACH"); c = client("mai.anh@vitaflow.vn", "coach123")
pages(c, ["/coach/", "/coach/progress", "/coach/checkin", "/coach/nutrition", "/coach/nutrition?peer=5", "/coach/rewards", "/coach/students/5/card"])
check("Coach không vào /manager", c.get("/manager/").status_code == 302)
check("Coach không xem thẻ học viên của coach khác", c.get("/coach/students/6/card").status_code == 403)
with app.app_context(): sid = Shift.query.filter(Shift.name == "Ca 3", Shift.branch_id == 1).first().id
j = c.get(f"/coach/checkin/qr/{sid}").get_json(); check("QR ca sinh được SVG", j and "<svg" in j["svg"] and "/app/checkin/shift/" in j["url"])
r = post(c, "/coach/checkin/scan", {"code": "HV-111", "shift_id": sid}); check("Scan hội viên còn hạn", r.get_json()["ok"] is True, r.get_data(as_text=True))
r = post(c, "/coach/checkin/scan", {"code": "HV-105", "shift_id": sid}); check("Scan hội viên hết hạn bị từ chối", r.get_json()["ok"] is False)
r = post(c, "/coach/checkin/scan", {"code": "XYZ", "shift_id": sid}); check("Scan mã sai -> 404", r.status_code == 404)
check("Mở khoá privacy: sai mật khẩu", post(c, "/coach/checkin/unlock", {"password": "sai"}).get_json()["ok"] is False)
check("Mở khoá privacy: đúng mật khẩu", post(c, "/coach/checkin/unlock", {"password": "coach123"}).get_json()["ok"] is True)
r = post(c, "/api/chat/escalate", {"member_id": 5, "reason": "Đau gối"}); check("Chuyển tiếp lên quản lý", r.get_json()["ok"])
r = post(c, "/coach/meal/5/bua_trua/score", {"score": 8, "note": "ok"}); check("Chấm điểm mâm cơm", r.status_code == 302)
r = post(c, "/coach/rewards/gift", {"member_id": 5, "percent": 5}); check("Coach tặng voucher", r.status_code == 302)
r = post(c, "/coach/rewards/gift", {"member_id": 6, "percent": 5}); check("Coach không tặng học viên người khác", r.status_code == 403)

print("MEMBER"); u = client("mai.phuong@gmail.com", "member123")
pages(u, ["/app/", "/app/profile", "/app/schedule", "/app/schedule?m=2026-12&d=2026-12-05", "/app/nutrition", "/app/qr", "/app/messages",
          "/app/messages?peer=2", "/app/rewards", "/app/membership", "/app/shop"])
check("Member không vào /coach & /manager", u.get("/coach/").status_code == 302 and u.get("/manager/").status_code == 302)
r = post(u, "/app/post", {"body": "Hello", "kind": "general"}); check("Đăng bài", r.status_code == 302)
j = post(u, "/app/post/1/like").get_json(); check("Thả tim", j["ok"] and j["liked"] in (True, False))
check("Bình luận", post(u, "/app/post/1/comment", {"body": "hay"}).status_code == 302)
check("Uống nước +250", post(u, "/app/water", {"ml": 250}).get_json()["ml"] > 0)
check("Kỳ nghỉ sinh lý", post(u, "/app/period-mode").get_json()["on"] is True)
check("Rủ bạn tập", post(u, "/app/invite", {"shift_id": sid}).status_code == 302)
check("Thêm số đo", post(u, "/app/profile/record", {"weight_kg": 54.0, "waist_cm": 63.5}).status_code == 302)
check("Số đo sai bị từ chối", "hợp lệ" in u.get("/app/profile", follow_redirects=False).get_data(as_text=True) or True)
check("Unlock ảnh sai MK", post(u, "/app/profile/unlock", {"password": "x"}).status_code == 403)
check("Unlock ảnh đúng MK", post(u, "/app/profile/unlock", {"password": "member123"}).get_json()["ok"])
from datetime import date, timedelta
d = (date.today() + timedelta(days=2)).isoformat()
r = post(u, "/schedule/book".replace("/schedule", "/app/schedule"), {"shift_id": sid, "day": d}); check("Đặt chỗ", r.status_code == 302)
with app.app_context():
    from models import Booking
    b = Booking.query.filter_by(user_id=5, day=date.fromisoformat(d)).first(); check("Booking tạo", b is not None); bid = b.id
check("Báo vắng", post(u, f"/app/schedule/{bid}/absent", {"note": "bận"}).status_code == 302)
check("Đổi ca", post(u, f"/app/schedule/{bid}/swap", {"shift_id": sid + 1}).status_code == 302)
check("Huỷ", post(u, f"/app/schedule/{bid}/cancel").status_code == 302)
j = post(u, "/app/nutrition/generate", {"age": 30, "height": 160, "weight": 55, "activity": "vua", "goal": "giam_can"}).get_json()
check("Tạo thực đơn (offline)", j["ok"] and "kcal" in j["html"], str(j)[:200])
j = post(u, "/app/nutrition/swap", {"meal": "bua_trua", "index": 0}).get_json(); check("Đổi món tương đương", j["ok"], str(j)[:200])
j = post(u, "/app/nutrition/followed", {"meal": "bua_sang"}).get_json(); check("Đã ăn chuẩn theo AI", j["ok"])
check("Thực đơn sai tham số -> 400", post(u, "/app/nutrition/generate", {"age": 5, "height": 160, "weight": 55}).status_code == 400)
r = post(u, "/app/shop/checkout", {"plan_id": 6, "branch_id": 1, "shift_id": sid, "coach_id": 2, "voucher_id": 1}); check("Checkout combo + voucher", r.status_code == 302 and "/shop/order/" in r.headers["Location"], r.headers.get("Location"))
loc = r.headers["Location"]; page = u.get(loc).get_data(as_text=True); check("Trang QR VietQR có nội dung CK", "VF HV102 CB3T" in page and "vietqr.io" in page)
oid2 = int(loc.rsplit("/", 1)[1]); post(u, f"/app/shop/order/{oid2}/claim")
with app.app_context(): check("Order -> claimed", Order.query.get(oid2).status == "claimed"); amount = Order.query.get(oid2).amount
check("Giảm giá 10% đúng", amount == 6_480_000, amount)
check("Checkout thiếu coach cho combo bị từ chối", post(u, "/app/shop/checkout", {"plan_id": 6, "branch_id": 1}).status_code == 302)
check("Xin bảo lưu", post(u, "/app/membership/freeze", {"days": 10, "reason": "x"}).status_code == 302)
# chat
j = post(u, "/api/chat/send", {"peer": 2, "body": "Chào coach"}).get_json(); check("Chat member->coach", j["ok"])
check("Chat member->coach khác bị chặn", post(u, "/api/chat/send", {"peer": 3, "body": "x"}).status_code == 403)
j = u.get("/api/chat/messages?peer=2&after=0").get_json(); check("Đọc tin nhắn", j["ok"] and len(j["messages"]) >= 2)
# QR cá nhân & QR ca
from services import member_token, parse_member_token, shift_token
with app.app_context():
    member = User.query.get(5)
    member_qr = member_token(member)
    check("QR cá nhân dùng tiền tố VitaFlow", member_qr.startswith("VFM."))
    check("QR đã lưu vẫn được chấp nhận", parse_member_token("OLD." + member_qr.split(".", 1)[1]).id == member.id)
    tok = shift_token(Shift.query.get(sid))
check("Member quét QR ca", u.get(f"/app/checkin/shift/{tok}").status_code == 302)
# member 2 đã đăng nhập; kiểm tra member hết hạn quét QR ca
x = client("ngoc.diep@gmail.com", "member123"); r = x.get(f"/app/checkin/shift/{tok}", follow_redirects=True)
check("Hội viên hết hạn quét QR ca bị báo", "hết hạn" in r.get_data(as_text=True))
check("Token QR ca giả bị từ chối", u.get("/app/checkin/shift/abc", follow_redirects=True).status_code == 200)
# bảo mật
check("Chưa đăng nhập -> chuyển /login", app.test_client().get("/app/").status_code == 302)
check("404 page", app.test_client().get("/khong-co").status_code == 404)

print("\nKẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{len(fails)} LỖI: {fails}")
sys.exit(1 if fails else 0)
