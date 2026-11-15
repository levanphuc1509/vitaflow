"""VITAFLOW - Hệ thống quản lý phòng tập dành cho nữ.  Chạy: python app.py"""
import os
from datetime import date
from pathlib import Path

from flask import Flask, g, request
from flask_login import current_user

from config import BASE_DIR, Config
from extensions import db, migrate, login_manager
from utils import apply_view_param, check_csrf, csrf_token, is_mobile, is_native_app, render_template, time_ago, vnd
from security import init_security
import throttle  # noqa

NAV = {
    "manager": [("manager.dashboard", "Tổng quan", "grid_view"),
                ("manager.staff", "Nhân sự & Cơ sở", "badge"),
                ("manager.members", "Tiến độ & Hồ sơ Body", "monitoring"),
                ("manager.shifts", "Ca tập & Điểm danh", "event_available"),
                ("manager.nutrition", "AI Diet & Messenger", "forum"),
                ("manager.rewards", "Phân hạng & Gia hạn", "workspace_premium"),
                ("manager.reports", "Kiểm duyệt nội dung", "shield")],
    "coach": [("coach.dashboard", "Tổng quan", "grid_view"),
              ("coach.progress", "Tiến độ học viên", "monitoring"),
              ("coach.checkin", "Ca tập & Quét QR", "qr_code_scanner"),
              ("coach.nutrition", "Dinh dưỡng AI & Chat", "restaurant_menu"),
              ("coach.rewards", "Phân hạng & Gifting", "redeem")],
    "member": [("member.feed", "Bảng tin", "dynamic_feed"),
               ("member.profile", "Hồ sơ & Độ Body", "accessibility_new"),
               ("member.schedule", "Lịch ca & Đặt chỗ", "calendar_month"),
               ("member.nutrition", "AI Coach & Bữa ăn", "nutrition"),
               ("member.qr", "Mã QR của tôi", "qr_code_2"),
               ("member.messages", "Tin nhắn", "chat"),
               ("member.rewards", "Xếp hạng & Ví quà", "emoji_events"),
               ("member.membership", "Gói tập của tôi", "card_membership"),
               ("member.shop", "Nạp gói", "add_card")],
}
NAV_MOBILE = {  # (endpoint khớp, nhãn, icon, nút giữa nổi bật)
    "manager": [(("manager.dashboard",), "Tổng Quan", "grid_view", False),
                (("manager.staff",), "Nhân Sự", "badge", False),
                (("manager.members",), "Hồ Sơ Body", "monitoring", False),
                (("manager.shifts",), "Ca Tập", "event_available", False),
                (("manager.nutrition", "manager.rewards"), "Chat & Quà", "forum", False)],
    "coach": [(("coach.dashboard",), "Tổng Quan", "grid_view", False),
              (("coach.progress",), "Học Viên", "groups", False),
              (("coach.checkin",), "Quét QR", "qr_code_scanner", True),
              (("coach.nutrition",), "Chat & AI", "smart_toy", False),
              (("coach.rewards",), "Thưởng Rank", "emoji_events", False)],
    "member": [(("member.feed",), "Bảng Tin", "dynamic_feed", False),
               (("member.schedule",), "Lịch Ca", "calendar_month", False),
               (("member.qr", "member.shift_checkin"), "Quét QR", "qr_code_scanner", True),
               (("member.nutrition",), "AI Coach", "nutrition", False),
               (("member.profile", "member.rewards", "member.membership", "member.shop", "member.order", "member.messages"),
                "Hồ Sơ & Nạp", "account_circle", False)],
}
ROLE_LABEL = {"manager": "Quản lý", "coach": "Huấn luyện viên", "member": "Thành viên"}


def _init_db(retries=4):
    """create_all an toàn khi nhiều worker (gunicorn) khởi động cùng lúc trên CSDL trống:
    worker nào đến sau sẽ gặp 'already exists' -> chờ rồi thử lại (lần sau create_all bỏ qua bảng đã có)."""
    import time
    from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
    for attempt in range(retries):
        try:
            db.create_all()
            return
        except (OperationalError, ProgrammingError, IntegrityError):
            db.session.rollback()
            if attempt == retries - 1:
                raise
            time.sleep(0.3 * (attempt + 1))


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    (BASE_DIR / "instance").mkdir(exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    if app.config["APP_ENV"] == "production":
        app.config["SESSION_COOKIE_SECURE"] = True   # chỉ gửi cookie phiên qua HTTPS
        if app.config["SECRET_KEY"] == app.config["DEFAULT_SECRET"]:
            raise RuntimeError("APP_ENV=production nhưng chưa đặt SECRET_KEY. Hãy đặt một chuỗi ngẫu nhiên dài trong .env")
    if app.config["BEHIND_PROXY"]:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True, compare_type=True)
    login_manager.init_app(app)
    init_security(app)

    from models import Branch, Message, Notification, User

    @login_manager.user_loader
    def load_user(uid):
        try:
            return db.session.get(User, int(uid))
        except (TypeError, ValueError):
            return None

    app.before_request(apply_view_param)
    app.before_request(check_csrf)
    app.add_template_filter(vnd, "vnd")
    app.add_template_filter(time_ago, "time_ago")

    import services
    app.jinja_env.globals.update(csrf_token=csrf_token, rank_info=services.rank_info, sub_status=services.sub_status,
                                 MEAL_LABELS=services.MEAL_LABELS, today=date.today, ROLE_LABEL=ROLE_LABEL, qr_svg=services.qr_svg,
                                 COMPANY_NAME=app.config["COMPANY_NAME"], SUPPORT_EMAIL=app.config["SUPPORT_EMAIL"], SUPPORT_PHONE=app.config["SUPPORT_PHONE"])

    @app.context_processor
    def inject():
        ctx = {"theme": current_user.role if current_user.is_authenticated else "manager", "is_mobile": is_mobile(), "is_native": is_native_app()}
        if current_user.is_authenticated:
            me = current_user
            ctx["nav_items"] = NAV.get(me.role, [])
            ctx["unread_msgs"] = services.unread_count(me)
            notes = Notification.query.filter_by(user_id=me.id).order_by(Notification.id.desc()).limit(8).all()
            ctx["notes"] = notes
            ctx["notes_unread"] = Notification.query.filter_by(user_id=me.id, read=False).count()
            ctx["branches"] = Branch.query.order_by(Branch.id).all()
            if ctx["is_mobile"]:
                ctx["nav_mobile"] = NAV_MOBILE.get(me.role, [])
                if me.role == "member":
                    ctx["me_rank"] = services.rank_info(me)
        return ctx

    from blueprints.api import bp as api_bp
    from blueprints.auth import bp as auth_bp
    from blueprints.coach import bp as coach_bp
    from blueprints.manager import bp as manager_bp
    from blueprints.member import bp as member_bp
    from blueprints.public import bp as public_bp
    for b in (public_bp, auth_bp, api_bp, manager_bp, coach_bp, member_bp):
        app.register_blueprint(b)

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(400)
    def err(e):
        return render_template("error.html", error=e), getattr(e, "code", 500)

    @app.after_request
    def flush_push(resp):
        """Gửi push (nếu đã cấu hình Firebase) sau khi request hoàn tất để không làm chậm người dùng."""
        from flask import g
        import push
        items = g.pop("pending_push", None)
        if items and resp.status_code < 400 and push.enabled():
            push.dispatch_async(app, items)
        return resp

    with app.app_context():
        _init_db()
        # Dữ liệu demo (tài khoản mật khẩu công khai) CHỈ nạp ở môi trường phát triển hoặc khi SEED_DEMO=1
        if app.config["APP_ENV"] != "production" or os.getenv("SEED_DEMO") == "1":
            from seed import seed_demo
            seed_demo()
    return app


app = create_app() if __name__ != "__main__" else None

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    port = int(os.getenv("PORT", "5000"))
    create_app().run(debug=debug, host=host, port=port)

