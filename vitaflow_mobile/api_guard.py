"""vitaflow_mobile/api_guard.py

Lớp bảo vệ riêng cho API JSON (Mobile App Capacitor):
  - api_login_required(roles=None): trả JSON 401/403 thay vì redirect sang trang đăng nhập
    (redirect HTML làm app mobile hiểu nhầm là thành công), chặn tài khoản đã bị khoá.
  - json_http_error: error-handler để mọi lỗi abort() trong blueprint /api đều là JSON.
  - is_capacitor_app(): chỉ để phân tích/UX. KHÔNG dùng làm cơ chế xác thực (User-Agent giả mạo được).
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Iterable, Optional

from flask import jsonify, request
from flask_login import current_user
from werkzeug.exceptions import HTTPException

audit = logging.getLogger("vitaflow.security")

_MESSAGES = {
    400: "Yêu cầu không hợp lệ.",
    401: "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
    403: "Bạn không có quyền thực hiện thao tác này.",
    404: "Không tìm thấy dữ liệu.",
    405: "Phương thức không được hỗ trợ.",
    413: "Tệp tải lên quá lớn.",
    429: "Bạn thao tác quá nhanh. Vui lòng thử lại sau.",
}


def wants_json() -> bool:
    return request.path.startswith("/api/") or request.is_json or \
        request.accept_mimetypes.best == "application/json"


def json_error(status: int, message: Optional[str] = None, **extra):
    msg = message or _MESSAGES.get(status, "Đã xảy ra lỗi.")
    resp = jsonify(ok=False, error=msg, message=msg, **extra)   # `error` giữ tương thích client cũ
    resp.status_code = status
    return resp


def json_http_error(exc: HTTPException):
    """Đăng ký: bp.register_error_handler(HTTPException, json_http_error)."""
    if exc.response is not None:          # abort(Response) từ security._deny: giữ nguyên
        return exc.response
    return json_error(exc.code or 500)


def api_login_required(roles: Optional[Iterable[str]] = None):
    roles = tuple(roles) if roles else None

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return json_error(401)
            if getattr(current_user, "active", True) is False:
                audit.warning("DENY 403 | user=%s | tài khoản bị khoá gọi %s %s",
                              current_user.id, request.method, request.path)
                return json_error(403, "Tài khoản đã bị khoá.")
            if roles and current_user.role not in roles:
                audit.warning("DENY 403 | user=%s role=%s | %s %s | cần vai trò %s", current_user.id,
                              current_user.role, request.method, request.path, roles)
                return json_error(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def is_capacitor_app() -> bool:
    return "VitaFlowApp/" in (request.headers.get("User-Agent") or "")
