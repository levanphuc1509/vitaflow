"""vitaflow_mobile/tests/test_api_rbac_security.py

Kiểm thử bảo mật truy cập chéo vai trò / chéo người dùng cho API JSON + cổng HTML.
Chạy:  cd vitaflow_mobile ; python -m pytest tests/test_api_rbac_security.py -v

ĐIỂM THÍCH ỨNG DUY NHẤT: hàm make_app() bên dưới. Nó phải khởi tạo app trên một file SQLite TẠM
(tên chứa "_test.db"). Nếu app của bạn không đọc biến DATABASE_URL, hãy sửa hàm này cho đúng cách
bạn cấu hình DB. Có chốt an toàn: nếu DB không phải file tạm, test sẽ DỪNG để không ghi vào vitaflow.db thật.

Giả định: login bằng cách ghi trực tiếp session Flask-Login (không phụ thuộc form /login).
"""
import os
import tempfile
from datetime import time

import pytest

PWD = "Passw0rd!x"


# ----------------------------------------------------------------------------- app & dữ liệu
def make_app():
    fd, path = tempfile.mkstemp(suffix="_test.db")
    os.close(fd)
    os.environ["DATABASE_URL"] = "sqlite:///" + path.replace("\\", "/")
    from app import create_app
    app = create_app()
    app.config.update(TESTING=True, SESSION_PROTECTION=None)
    if "_test.db" not in str(app.config.get("SQLALCHEMY_DATABASE_URI", "")):
        pytest.exit("DỪNG: app không dùng DB tạm. Sửa make_app() để trỏ DB test, tránh ghi vào DB thật.", 2)
    app.login_manager.session_protection = None
    app._test_db_path = path
    return app


@pytest.fixture(scope="module")
def app():
    app = make_app()
    from extensions import db
    with app.app_context():
        db.create_all()          # chỉ cho DB test tạm; DB thật dùng Flask-Migrate
    yield app
    try:
        os.remove(app._test_db_path)
    except OSError:
        pass


@pytest.fixture(scope="module")
def ids(app):
    from extensions import db
    from models import Branch, Shift, User
    with app.app_context():
        br = Branch(name="Test", address="x", lat=10.8, lng=106.7)
        db.session.add(br)
        db.session.flush()

        def mk(role, email, name, **kw):
            u = User(full_name=name, email=email, role=role, active=True, **kw)
            u.set_password(PWD)
            db.session.add(u)
            db.session.flush()
            return u

        mgr = mk("manager", "mgr@t.vn", "Manager", branch_id=br.id)
        ca = mk("coach", "ca@t.vn", "Coach A", branch_id=br.id)
        cb = mk("coach", "cb@t.vn", "Coach B", branch_id=br.id)
        ma = mk("member", "ma@t.vn", "Member A", branch_id=br.id, member_code="HV-901", coach_id=ca.id)
        mb = mk("member", "mb@t.vn", "Member B", branch_id=br.id, member_code="HV-902", coach_id=cb.id)
        mx = mk("member", "mx@t.vn", "Member Locked", branch_id=br.id, member_code="HV-903", coach_id=ca.id)
        mx.active = False
        shift = Shift(branch_id=br.id, name="Ca 1", title="Ca sáng", start=time(6), end=time(7), capacity=15)
        shift.coaches.append(ca)
        db.session.add(shift)
        db.session.commit()
        return dict(mgr=mgr.id, ca=ca.id, cb=cb.id, ma=ma.id, mb=mb.id, mx=mx.id, shift=shift.id)


@pytest.fixture(autouse=True)
def _clean_throttle(app):
    from extensions import db
    from throttle import AuthThrottle
    with app.app_context():
        AuthThrottle.query.delete()
        db.session.commit()
    yield


CSRF = "test-csrf-token"


def anon(app, user_agent="VitaFlowApp/1.0"):
    """Client chua dang nhap nhung co token CSRF hop le (giong app that gui X-CSRF-Token)."""
    c = app.test_client(); c.environ_base["HTTP_USER_AGENT"] = user_agent
    c.environ_base["HTTP_X_CSRF_TOKEN"] = CSRF
    with c.session_transaction() as s:
        s["_csrf"] = CSRF
    return c


def login(app, uid, user_agent="VitaFlowApp/1.0"):
    c = anon(app, user_agent)
    with c.session_transaction() as s:
        s["_user_id"] = str(uid)
        s["_fresh"] = True
    return c


def assert_denied(resp, must_not_contain=None):
    """Bị từ chối = 401/403/404, hoặc 302 chuyển đi nơi khác (không phải 200)."""
    assert resp.status_code in (302, 401, 403, 404), f"Không bị chặn! status={resp.status_code}"
    if resp.status_code == 302 and must_not_contain:
        assert must_not_contain not in (resp.headers.get("Location") or "")


# ----------------------------------------------------------------------------- 1. Chưa đăng nhập
def test_anonymous_gets_json_401_not_redirect(app):
    c = anon(app)
    for method, url in [("get", "/api/chat/messages?peer=1"), ("post", "/api/chat/send"),
                        ("post", "/api/chat/escalate"), ("post", "/api/notifications/read"),
                        ("post", "/api/device/register"), ("post", "/api/device/unregister")]:
        r = getattr(c, method)(url)
        assert r.status_code == 401, (url, r.status_code)
        assert r.get_json()["ok"] is False


def test_locked_account_with_live_session_is_rejected(app, ids):
    r = login(app, ids["mx"]).post("/api/notifications/read")
    assert r.status_code in (401, 403)


# ----------------------------------------------------------------------------- 2. Coach A -> học viên của Coach B
def test_coach_cannot_escalate_other_coachs_member(app, ids):
    from models import Escalation
    r = login(app, ids["cb"]).post("/api/chat/escalate", data={"member_id": ids["ma"], "reason": "x"})
    assert r.status_code == 403
    with app.app_context():
        assert Escalation.query.filter_by(member_id=ids["ma"]).count() == 0


def test_coach_can_escalate_own_member(app, ids):
    from models import Escalation
    r = login(app, ids["ca"]).post("/api/chat/escalate", data={"member_id": ids["ma"], "reason": "Cần hỗ trợ"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    with app.app_context():
        assert Escalation.query.filter_by(member_id=ids["ma"], coach_id=ids["ca"]).count() == 1


def test_coach_cannot_escalate_non_member_or_unknown(app, ids):
    c = login(app, ids["ca"])
    assert c.post("/api/chat/escalate", data={"member_id": ids["mgr"], "reason": "x"}).status_code in (403, 404)
    assert c.post("/api/chat/escalate", data={"member_id": 999999, "reason": "x"}).status_code in (403, 404)
    assert c.post("/api/chat/escalate", data={"reason": "x"}).status_code in (403, 404)


def test_coach_cannot_read_other_coachs_member_chat(app, ids):
    """Phụ thuộc services.can_chat: Coach chỉ chat với học viên của mình. Nếu nghiệp vụ khác, chỉnh lại test."""
    r = login(app, ids["cb"]).get(f"/api/chat/messages?peer={ids['ma']}")
    assert r.status_code == 403


def test_coach_cannot_send_to_other_coachs_member(app, ids):
    from models import Message
    r = login(app, ids["cb"]).post("/api/chat/send", data={"peer": ids["ma"], "body": "hi"})
    assert r.status_code == 403
    with app.app_context():
        assert Message.query.filter_by(sender_id=ids["cb"]).count() == 0


def test_chat_unknown_peer_or_shift_is_403(app, ids):
    c = login(app, ids["ma"])
    assert c.get("/api/chat/messages?peer=999999").status_code == 403
    assert c.get("/api/chat/messages?shift=999999").status_code == 403
    assert c.get("/api/chat/messages").status_code == 403           # thiếu tham số
    assert c.get(f"/api/chat/messages?peer={ids['ma']}").status_code == 403   # tự chat với mình


# ----------------------------------------------------------------------------- 3. Member / Manager chéo vai trò
def test_member_cannot_call_coach_only_endpoint(app, ids):
    r = login(app, ids["ma"]).post("/api/chat/escalate", data={"member_id": ids["ma"], "reason": "x"})
    assert r.status_code == 403 and r.get_json()["ok"] is False


def test_manager_cannot_call_coach_only_endpoint(app, ids):
    r = login(app, ids["mgr"]).post("/api/chat/escalate", data={"member_id": ids["ma"], "reason": "x"})
    assert r.status_code == 403


def test_member_cannot_enter_manager_or_coach_portal(app, ids):
    c = login(app, ids["ma"])
    assert_denied(c.get("/manager/"), "/manager")
    assert_denied(c.get("/coach/"), "/coach")


def test_coach_cannot_enter_manager_portal_nor_member_portal(app, ids):
    c = login(app, ids["ca"])
    assert_denied(c.get("/manager/"), "/manager")
    assert_denied(c.get("/app/"), "/app")


def test_coach_student_card_cross_access(app, ids):
    assert login(app, ids["cb"]).get(f"/coach/students/{ids['ma']}/card").status_code == 403
    assert login(app, ids["ca"]).get(f"/coach/students/{ids['ma']}/card").status_code == 200


# ----------------------------------------------------------------------------- 4. Dữ liệu cá nhân: thông báo & thiết bị
def test_notifications_read_only_touches_own(app, ids):
    from extensions import db
    from models import Notification
    from services import notify
    with app.app_context():
        notify(ids["ma"], "cho A")
        notify(ids["mb"], "cho B")
        db.session.commit()
    assert login(app, ids["ma"]).post("/api/notifications/read").status_code == 200
    with app.app_context():
        assert Notification.query.filter_by(user_id=ids["ma"], read=False).count() == 0
        assert Notification.query.filter_by(user_id=ids["mb"], read=False).count() >= 1


def test_device_register_validation_and_unregister_scope(app, ids):
    from models import DeviceToken
    tok = "tok_" + "a" * 30
    a, b = login(app, ids["ma"]), login(app, ids["mb"])
    assert a.post("/api/device/register", data={"token": "ngan", "platform": "android"}).status_code == 400
    assert a.post("/api/device/register", data={"token": tok, "platform": "windows-phone"}).status_code == 400
    assert a.post("/api/device/register", data={"token": tok, "platform": "android"}).status_code == 200
    with app.app_context():
        assert DeviceToken.query.filter_by(token=tok, user_id=ids["ma"]).count() == 1
    b.post("/api/device/unregister", data={"token": tok})            # B không xoá được token của A
    with app.app_context():
        assert DeviceToken.query.filter_by(token=tok, user_id=ids["ma"]).count() == 1
    a.post("/api/device/unregister", data={"token": tok})
    with app.app_context():
        assert DeviceToken.query.filter_by(token=tok).count() == 0


# ----------------------------------------------------------------------------- 5. Rate-limit
def test_chat_send_is_rate_limited(app, ids):
    app.config["RATE_CHAT_SEND"] = (3, 60)
    try:
        c = login(app, ids["ca"])
        codes = [c.post("/api/chat/send", data={"peer": ids["ma"], "body": f"m{i}"}).status_code for i in range(5)]
        assert codes[:3] == [200, 200, 200], codes
        assert codes[3] == 429 and codes[4] == 429, codes
        r = c.post("/api/chat/send", data={"peer": ids["ma"], "body": "x"})
        assert r.get_json()["ok"] is False and r.headers.get("Retry-After")
    finally:
        app.config.pop("RATE_CHAT_SEND", None)


def test_login_throttle_locks_after_5_failures_per_email_and_ip(app):
    from throttle import login_failed, login_guard, login_succeeded
    email = "nan@nhan.vn"
    with app.test_request_context("/auth/login", environ_base={"REMOTE_ADDR": "9.9.9.9"}):
        assert login_guard(email) == 0
        assert [login_failed(email) for _ in range(4)] == [0, 0, 0, 0]
        assert login_failed(email) > 0
        assert login_guard(email) > 0
    # Kẻ xấu khoá cặp (email, IP) của mình KHÔNG khoá được nạn nhân đăng nhập từ IP khác
    with app.test_request_context("/auth/login", environ_base={"REMOTE_ADDR": "1.2.3.4"}):
        assert login_guard(email) == 0
    # Đăng nhập đúng sẽ xoá bộ đếm của cặp
    with app.test_request_context("/auth/login", environ_base={"REMOTE_ADDR": "9.9.9.9"}):
        login_succeeded(email)
        assert login_guard(email) == 0


def test_post_without_csrf_token_is_rejected(app):
    c = app.test_client()
    assert c.post("/api/chat/send", data={"peer": 1, "body": "x"}).status_code == 400
