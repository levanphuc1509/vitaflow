"""Tiện ích dùng chung: phân quyền, CSRF, upload ảnh, filter Jinja."""
import re
import secrets
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

import flask
from flask import abort, current_app, flash, redirect, request, session, url_for
from urllib.parse import urljoin, urlsplit
from flask_login import current_user, login_required

HOME_ENDPOINT = {"manager": "manager.dashboard", "coach": "coach.dashboard", "member": "member.feed"}


def home_for(user):
    return url_for(HOME_ENDPOINT.get(user.role, "public.landing"))


def role_required(*roles):
    """Middleware phân quyền: chỉ cho phép các role được liệt kê."""
    def deco(view):
        @wraps(view)
        @login_required
        def wrapped(*a, **kw):
            if current_user.role not in roles:
                if request.accept_mimetypes.best == "application/json" or request.is_json:
                    abort(403)
                flash("Bạn không có quyền truy cập khu vực này.", "warning")
                return redirect(home_for(current_user))
            return view(*a, **kw)
        return wrapped
    return deco


def manager_required(view):
    return role_required("manager")(view)


def coach_required(view):
    return role_required("coach")(view)


def member_required(view):
    return role_required("member")(view)


# ---------- CSRF ----------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


def check_csrf():
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not sent or sent != session.get("_csrf"):
            abort(400, "Phiên làm việc hết hạn, vui lòng tải lại trang.")


# ---------- Upload ảnh ----------
def save_image(file_storage):
    """Lưu ảnh upload, trả về URL tĩnh hoặc None."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in current_app.config["ALLOWED_IMAGE_EXT"]:
        return None
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(folder / name)
    return url_for("static", filename=f"uploads/{name}")


# ---------- Filter ----------
def vnd(value):
    try:
        return f"{int(round(float(value))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def time_ago(dt):
    if not dt:
        return ""
    s = (datetime.now() - dt).total_seconds()
    if s < 60:
        return "Vừa xong"
    if s < 3600:
        return f"{int(s // 60)} phút trước"
    if s < 86400:
        return f"{int(s // 3600)} giờ trước"
    if s < 86400 * 7:
        return f"{int(s // 86400)} ngày trước"
    return dt.strftime("%d/%m/%Y")


def int_or(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_or(value, default=None):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


# ---------- Giao diện PC / Mobile chạy song song ----------
_MOBILE_UA = re.compile(r"Android.+Mobile|iPhone|iPod|Windows Phone|IEMobile|BlackBerry|Opera Mini|Mobile.+Firefox", re.I)


def is_mobile():
    """Ưu tiên lựa chọn thủ công (session['view']); nếu chưa chọn thì đoán theo User-Agent.
    Máy tính bảng (iPad, tablet Android) dùng giao diện PC."""
    pref = session.get("view")
    if pref in ("mobile", "desktop"):
        return pref == "mobile"
    return bool(_MOBILE_UA.search(request.headers.get("User-Agent", "")))


def apply_view_param():
    """?view=mobile|desktop -> ghi nhớ lựa chọn trong phiên."""
    v = request.args.get("view")
    if v in ("mobile", "desktop"):
        session["view"] = v


def safe_next(target, fallback="/"):
    if not target:
        return fallback
    ref, test = urlsplit(request.host_url), urlsplit(urljoin(request.host_url, target))
    return target if test.scheme in ("http", "https") and ref.netloc == test.netloc else fallback


def render_template(name, **ctx):
    """Giống flask.render_template nhưng tự dùng bản mobile `m/<name>` nếu có và thiết bị là điện thoại.
    Nhờ đó cùng một route/logic phục vụ cả hai giao diện."""
    if is_mobile():
        tpl = current_app.jinja_env.select_template([f"m/{name}", name])
        return flask.render_template(tpl, **ctx)
    return flask.render_template(name, **ctx)
