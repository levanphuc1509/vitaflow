"""vitaflow_mobile/throttle.py

Giới hạn tần suất / chống dò mật khẩu, lưu trong database (bảng `auth_throttle`) nên:
  - hoạt động đúng khi chạy nhiều worker,
  - không mất khi restart server.
Dùng 1 session RIÊNG nên không vô tình commit dữ liệu đang dở của request.
Nếu bảng lỗi/chưa migrate thì "fail-open" (không khoá oan người dùng) và ghi log.

Sau khi thêm file: `flask db migrate -m "add auth_throttle"` -> đọc script -> `python scripts/db_safe_upgrade.py`.
Nhớ `import throttle` ở đâu đó trước khi autogenerate (vd trong app.py) để model được đăng ký.

Hai cách dùng:
  1) Chống dò mật khẩu (auth.py):  login_guard / login_failed / login_succeeded
  2) Giới hạn tần suất endpoint:    @rate_limit("chat_send", config_key="RATE_CHAT_SEND", default=(30, 60))
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from functools import wraps
from math import ceil
from typing import Optional

from flask import abort, current_app, request
from flask_login import current_user
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api_guard import json_error, wants_json
from extensions import db

log = logging.getLogger("vitaflow.security")


class AuthThrottle(db.Model):
    __tablename__ = "auth_throttle"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False)
    hits = db.Column(db.Integer, nullable=False, default=0)
    window_start = db.Column(db.DateTime, nullable=False, default=datetime.now)
    locked_until = db.Column(db.DateTime, nullable=True)


# ---------------------------------------------------------------- Tiện ích
def client_ip() -> str:
    """IP kết nối. Chạy sau nginx/proxy: bọc app bằng werkzeug ProxyFix(x_for=1) để remote_addr đúng.
    KHÔNG đọc X-Forwarded-For thủ công (kẻ tấn công tự gửi header giả được)."""
    return request.remote_addr or "unknown"


def key_for(name: str, ident) -> str:
    """Khoá dạng name:HMAC(ident) - không lưu email/IP dạng rõ trong DB."""
    secret = current_app.config["SECRET_KEY"]
    secret = secret.encode() if isinstance(secret, str) else secret
    digest = hmac.new(secret, str(ident).strip().lower().encode(), hashlib.sha256).hexdigest()[:40]
    return f"{name}:{digest}"


def _run(fn, default=0):
    try:
        with Session(db.engine) as s:
            out = fn(s)
            s.commit()
            return out
    except SQLAlchemyError:
        log.exception("throttle: lỗi lưu trữ (fail-open)")
        return default


def _remaining(row, now) -> int:
    if row is not None and row.locked_until and row.locked_until > now:
        return max(1, ceil((row.locked_until - now).total_seconds()))
    return 0


# ---------------------------------------------------------------- Lõi
def locked_for(key: str) -> int:
    """Số giây còn bị khoá (0 = không bị khoá)."""
    def _do(s):
        now = datetime.now()
        row = s.execute(select(AuthThrottle).where(AuthThrottle.key == key)).scalar_one_or_none()
        return _remaining(row, now)
    return _run(_do)


def register(key: str, limit: int, window: int, lockout: int) -> int:
    """Ghi nhận 1 lần (thất bại / yêu cầu). Đạt `limit` lần trong `window` giây thì khoá `lockout` giây.
    Trả về số giây còn bị khoá sau lần ghi này (0 nếu chưa khoá)."""
    def _do(s):
        now = datetime.now()
        row = s.execute(select(AuthThrottle).where(AuthThrottle.key == key)).scalar_one_or_none()
        if row is None:
            row = AuthThrottle(key=key, hits=0, window_start=now)
            s.add(row)
        active_lock = bool(row.locked_until and row.locked_until > now)
        if not active_lock and (row.locked_until or (now - row.window_start).total_seconds() > window):
            row.hits, row.window_start, row.locked_until = 0, now, None      # khoá/cửa sổ cũ đã hết hạn
        row.hits += 1
        if row.hits >= limit and not active_lock:
            row.locked_until = now + timedelta(seconds=lockout)
        return _remaining(row, now)
    return _run(_do)


def clear(*keys: str) -> None:
    _run(lambda s: s.execute(delete(AuthThrottle).where(AuthThrottle.key.in_(keys))))


def purge_expired(older_than_days: int = 2) -> int:
    """Dọn bản ghi cũ. Gọi định kỳ (cron) hoặc từ manage.py."""
    cutoff = datetime.now() - timedelta(days=older_than_days)
    return _run(lambda s: s.execute(delete(AuthThrottle).where(AuthThrottle.window_start < cutoff)).rowcount)


# ---------------------------------------------------------------- Chống dò mật khẩu (dùng trong auth.py)
LOGIN_PAIR = (5, 900, 900)      # 5 lần sai / cặp (email, IP) / 15 phút  -> khoá 15 phút
LOGIN_IP = (30, 900, 900)       # 30 lần sai / IP                        (quét nhiều tài khoản)
LOGIN_ACCT = (25, 900, 900)     # 25 lần sai / email từ nhiều IP         (tấn công phân tán)
# Khoá theo cặp (email, IP) để kẻ xấu không khoá oan được tài khoản của người khác chỉ bằng cách spam email đó.


def _login_keys(email: str):
    ip = client_ip()
    return (key_for("login_pair", f"{email}|{ip}"), key_for("login_ip", ip), key_for("login_acct", email))


def login_guard(email: str) -> int:
    """Gọi TRƯỚC khi kiểm tra mật khẩu. Trả số giây còn bị khoá (0 = được phép thử)."""
    return max(locked_for(k) for k in _login_keys(email))


def login_failed(email: str) -> int:
    """Gọi khi đăng nhập sai. Trả số giây bị khoá (nếu lần này vừa chạm ngưỡng)."""
    pair, ip, acct = _login_keys(email)
    return max(register(pair, *LOGIN_PAIR), register(ip, *LOGIN_IP), register(acct, *LOGIN_ACCT))


def login_succeeded(email: str) -> None:
    pair, _, _ = _login_keys(email)
    clear(pair)


# ---------------------------------------------------------------- Giới hạn tần suất endpoint
def rate_limit(name: str, *, config_key: Optional[str] = None, default=(60, 60), per: str = "user"):
    """@rate_limit("chat_send", config_key="RATE_CHAT_SEND", default=(30, 60)) = 30 yêu cầu / 60 giây.
    Đặt SAU @api_login_required để có current_user. per="user" hoặc "ip"."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            limit, window = (current_app.config.get(config_key) if config_key else None) or default
            who = current_user.id if per == "user" and current_user.is_authenticated else client_ip()
            key = key_for(f"rl_{name}", who)
            wait = locked_for(key)
            if wait:
                log.warning("RATE-LIMIT %s | who=%s | %s %s", name, who, request.method, request.path)
                if wants_json():
                    resp = json_error(429, retry_after=wait)
                    resp.headers["Retry-After"] = str(wait)
                    return resp
                abort(429)
            register(key, limit, window, window)    # yêu cầu thứ `limit` vẫn qua; yêu cầu kế tiếp bị chặn
            return fn(*args, **kwargs)
        return wrapper
    return decorator
