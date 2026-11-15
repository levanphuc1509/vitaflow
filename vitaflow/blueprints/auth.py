from flask import Blueprint, current_app, flash, redirect, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from urllib.parse import urljoin, urlsplit

from extensions import db
from models import Branch, User
from seed import DEMO_ACCOUNTS
from services import next_member_code
from utils import render_template, home_for

bp = Blueprint("auth", __name__)


def _safe(target):
    if not target:
        return None
    ref, test = urlsplit(request.host_url), urlsplit(urljoin(request.host_url, target))
    return target if test.scheme in ("http", "https") and ref.netloc == test.netloc else None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(request.form.get("password", "")):
            if not user.active:
                flash("Tài khoản của bạn đang bị tạm khoá. Vui lòng liên hệ Quản lý.", "error")
            else:
                login_user(user, remember=bool(request.form.get("remember")))
                return redirect(_safe(request.args.get("next")) or home_for(user))
        else:
            flash("Email hoặc mật khẩu chưa đúng.", "error")
    return render_template("auth/login.html", demo=DEMO_ACCOUNTS)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(home_for(current_user))
    branches = Branch.query.all()
    if request.method == "POST":
        f = request.form
        name, email, pw = f.get("full_name", "").strip(), f.get("email", "").strip().lower(), f.get("password", "")
        if not name or "@" not in email or len(pw) < 6:
            flash("Vui lòng nhập đủ họ tên, email hợp lệ và mật khẩu từ 6 ký tự.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Email này đã được đăng ký.", "error")
        else:
            u = User(full_name=name, email=email, role="member", phone=f.get("phone", "").strip(),
                     branch_id=request.form.get("branch_id", type=int) or (branches[0].id if branches else None),
                     member_code=next_member_code())
            u.set_password(pw)
            db.session.add(u)
            db.session.commit()
            login_user(u)
            flash(f"Chào mừng bạn đến với {current_app.config['COMPANY_NAME']}! Hãy nạp gói để bắt đầu hành trình.", "success")
            return redirect(url_for("member.shop"))
    return render_template("auth/register.html", branches=branches)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("public.landing"))
