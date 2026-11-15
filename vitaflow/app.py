"""VITAFLOW - Há»‡ thá»‘ng quáº£n lĂ½ phĂ²ng táº­p dĂ nh cho ná»¯.  Cháº¡y: python app.py"""
from datetime import date
from pathlib import Path

from flask import Flask, g, request
from flask_login import current_user

from config import BASE_DIR, Config
from extensions import db, migrate, login_manager
from utils import apply_view_param, check_csrf, csrf_token, is_mobile, render_template, time_ago, vnd
from security import init_security
import throttle  # noqa

NAV = {
    "manager": [("manager.dashboard", "Tá»•ng quan", "grid_view"),
                ("manager.staff", "NhĂ¢n sá»± & CÆ¡ sá»Ÿ", "badge"),
                ("manager.members", "Tiáº¿n Ä‘á»™ & Há»“ sÆ¡ Body", "monitoring"),
                ("manager.shifts", "Ca táº­p & Äiá»ƒm danh", "event_available"),
                ("manager.nutrition", "AI Diet & Messenger", "forum"),
                ("manager.rewards", "PhĂ¢n háº¡ng & Gia háº¡n", "workspace_premium")],
    "coach": [("coach.dashboard", "Tá»•ng quan", "grid_view"),
              ("coach.progress", "Tiáº¿n Ä‘á»™ há»c viĂªn", "monitoring"),
              ("coach.checkin", "Ca táº­p & QuĂ©t QR", "qr_code_scanner"),
              ("coach.nutrition", "Dinh dÆ°á»¡ng AI & Chat", "restaurant_menu"),
              ("coach.rewards", "PhĂ¢n háº¡ng & Gifting", "redeem")],
    "member": [("member.feed", "Báº£ng tin", "dynamic_feed"),
               ("member.profile", "Há»“ sÆ¡ & Äá»™ Body", "accessibility_new"),
               ("member.schedule", "Lá»‹ch ca & Äáº·t chá»—", "calendar_month"),
               ("member.nutrition", "AI Coach & Bá»¯a Äƒn", "nutrition"),
               ("member.qr", "MĂ£ QR cá»§a tĂ´i", "qr_code_2"),
               ("member.messages", "Tin nháº¯n", "chat"),
               ("member.rewards", "Xáº¿p háº¡ng & VĂ­ quĂ ", "emoji_events"),
               ("member.membership", "GĂ³i táº­p cá»§a tĂ´i", "card_membership"),
               ("member.shop", "Náº¡p gĂ³i", "add_card")],
}
NAV_MOBILE = {  # (endpoint khá»›p, nhĂ£n, icon, nĂºt giá»¯a ná»•i báº­t)
    "manager": [(("manager.dashboard",), "Tá»•ng Quan", "grid_view", False),
                (("manager.staff",), "NhĂ¢n Sá»±", "badge", False),
                (("manager.members",), "Há»“ SÆ¡ Body", "monitoring", False),
                (("manager.shifts",), "Ca Táº­p", "event_available", False),
                (("manager.nutrition", "manager.rewards"), "Chat & QuĂ ", "forum", False)],
    "coach": [(("coach.dashboard",), "Tá»•ng Quan", "grid_view", False),
              (("coach.progress",), "Há»c ViĂªn", "groups", False),
              (("coach.checkin",), "QuĂ©t QR", "qr_code_scanner", True),
              (("coach.nutrition",), "Chat & AI", "smart_toy", False),
              (("coach.rewards",), "ThÆ°á»Ÿng Rank", "emoji_events", False)],
    "member": [(("member.feed",), "Báº£ng Tin", "dynamic_feed", False),
               (("member.schedule",), "Lá»‹ch Ca", "calendar_month", False),
               (("member.qr", "member.shift_checkin"), "QuĂ©t QR", "qr_code_scanner", True),
               (("member.nutrition",), "AI Coach", "nutrition", False),
               (("member.profile", "member.rewards", "member.membership", "member.shop", "member.order", "member.messages"),
                "Há»“ SÆ¡ & Náº¡p", "account_circle", False)],
}
ROLE_LABEL = {"manager": "Quáº£n lĂ½", "coach": "Huáº¥n luyá»‡n viĂªn", "member": "ThĂ nh viĂªn"}


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    (BASE_DIR / "instance").mkdir(exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

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
                                 COMPANY_NAME=app.config["COMPANY_NAME"],
                                 MEAL_LABELS=services.MEAL_LABELS, today=date.today, ROLE_LABEL=ROLE_LABEL, qr_svg=services.qr_svg)

    @app.context_processor
    def inject():
        ctx = {"theme": current_user.role if current_user.is_authenticated else "manager", "is_mobile": is_mobile()}
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

    with app.app_context():
        db.create_all()
        from seed import seed_demo
        seed_demo()
    return app


app = create_app() if __name__ != "__main__" else None

if __name__ == "__main__":
    create_app().run(debug=True, host="127.0.0.1", port=5000)

