"""vitaflow_mobile/security.py

Object-level RBAC (phân quyền ở tầng dữ liệu) cho VitaFlow.

Quy tắc (theo CONTEXT.md):
  - Manager : thấy/thao tác tất cả. (Tuỳ chọn: bật config MANAGER_BRANCH_SCOPED=True
              để giới hạn Manager theo chi nhánh của họ - mặc định TẮT.)
  - Coach   : chỉ thao tác học viên có member.coach_id == coach.id và ca tập mình được gán.
  - Member  : chỉ xem/thao tác dữ liệu của chính mình.

Cách dùng nhanh:
    @bp.route("/students/<int:uid>/card")
    @coach_required
    @student_access("uid", as_kwarg="m")
    def student_card(uid, m): ...

Mọi truy cập bị từ chối đều được ghi vào logger "vitaflow.security" (logs/security.log).
"""
from __future__ import annotations

import logging
import os
from functools import wraps
from logging.handlers import RotatingFileHandler
from typing import Callable, Iterable, NoReturn, Optional

import sqlalchemy as sa
from flask import abort, current_app, g, jsonify, request
from flask_login import current_user

from extensions import db
from models import User

ROLE_MANAGER, ROLE_COACH, ROLE_MEMBER = "manager", "coach", "member"
audit = logging.getLogger("vitaflow.security")

DEFAULT_SOURCES = ("view_args", "form", "args", "json")


# ---------------------------------------------------------------- Khởi tạo
def init_security(app) -> None:
    """Gọi 1 lần trong create_app(): `from security import init_security; init_security(app)`."""
    app.config.setdefault("MANAGER_BRANCH_SCOPED", False)
    if audit.handlers:
        return
    audit.setLevel(logging.INFO)
    log_dir = os.path.join(app.root_path, "logs")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(os.path.join(log_dir, "security.log"), maxBytes=2_000_000,
                                  backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    audit.addHandler(handler)


# ---------------------------------------------------------------- Tiện ích nội bộ
def _role() -> Optional[str]:
    return getattr(current_user, "role", None)


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.is_json or \
        request.accept_mimetypes.best == "application/json"


def _deny(status: int, reason: str) -> NoReturn:
    """Ghi log bảo mật rồi trả 403/404 (JSON cho API, trang lỗi cho HTML)."""
    audit.warning("DENY %s | user=%s role=%s | %s %s | ip=%s | %s", status,
                  getattr(current_user, "id", None), _role(), request.method, request.path,
                  request.remote_addr, reason)
    if _wants_json():
        resp = jsonify(ok=False, message="Không có quyền truy cập." if status == 403 else "Không tìm thấy.")
        resp.status_code = status
        abort(resp)
    abort(status)


def _manager_scope_ok(user, branch_id) -> bool:
    """Manager mặc định thấy tất cả. Nếu MANAGER_BRANCH_SCOPED=True thì chỉ trong chi nhánh mình."""
    if not current_app.config.get("MANAGER_BRANCH_SCOPED", False):
        return True
    if branch_id is None or getattr(user, "branch_id", None) is None:
        return True
    return branch_id == user.branch_id


def _extract_id(param: str, sources: Iterable[str]) -> Optional[int]:
    for src in sources:
        if src == "view_args":
            v = (request.view_args or {}).get(param)
        elif src == "form":
            v = request.form.get(param)
        elif src == "args":
            v = request.args.get(param)
        elif src == "json":
            v = (request.get_json(silent=True) or {}).get(param)
        else:
            continue
        if v is not None and str(v).isdigit():
            return int(v)


# ---------------------------------------------------------------- Chính sách truy cập
def can_access_member(current_user, target: User) -> bool:
    """Coach chỉ học viên của mình; Member chỉ chính mình; Manager tất cả."""
    role = _role()
    if role == ROLE_MANAGER:
        return True
    if role == ROLE_COACH:
        return target.role == ROLE_MEMBER and getattr(target, "coach_id", None) == current_user.id
    if role == ROLE_MEMBER:
        return target.id == current_user.id
    return False


def can_access_shift(current_user, shift) -> bool:
    """Coach/Manager: chỉ ca mình được gán (hoặc tất cả nếu Manager)."""
    role = _role()
    if role == ROLE_MANAGER:
        return True
    if role == ROLE_COACH:
        return current_user in shift.coaches
    return False


def owner_policy(owner_field: str, coach_field: Optional[str] = None) -> Callable:
    """Trả về hàm kiểm tra quyền sở hữu bản ghi theo owner_field (user_id, v.v.)."""

    def policy(current_user, obj) -> bool:
        role = _role()
        if role == ROLE_MANAGER:
            return True
        owner_id = getattr(obj, owner_field, None)
        if role == ROLE_MEMBER:
            return owner_id == current_user.id
        if role == ROLE_COACH and coach_field:
            coach_id = getattr(obj, coach_field, None)
            return coach_id == current_user.id
        return False

    return policy


def can_access_message(current_user, msg) -> bool:
    """Tin nhắn: người gửi hoặc người nhận (1-1), hoặc thành viên nhóm ca."""
    role = _role()
    if role == ROLE_MANAGER:
        return True
    if msg.sender_id == current_user.id or msg.recipient_id == current_user.id:
        return True
    if role == ROLE_COACH and msg.shift_id:
        return current_user in (msg.shift.coaches if msg.shift else [])
    return False


def can_access_escalation(current_user, esc) -> bool:
    """Escalation: Coach của học viên, hoặc Manager."""
    role = _role()
    if role == ROLE_MANAGER:
        return True
    if role == ROLE_COACH:
        return esc.coach_id == current_user.id
    return False
    return None


# ---------------------------------------------------------------- Decorator object_access
def object_access(model, param: str = "id", policy=None, roles: Optional[Iterable[str]] = None,
                  sources: Iterable[str] = DEFAULT_SOURCES, as_kwarg: Optional[str] = None,
                  optional: bool = False):
    """Kiểm tra quyền truy cập đối tượng model trước khi vào view.

    - `param`: tên tham số trong URL / form / args chứa ID.
    - `policy(current_user, obj) -> bool`: hàm kiểm tra quyền.
    - `as_kwarg`: nếu set, đối tượng được truyền vào view qua kwargs này.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if roles and _role() not in roles:
                _deny(403, f"role {_role()} not in {roles}")
            oid = _extract_id(param, sources)
            if oid is None:
                if optional:
                    if as_kwarg:
                        kwargs[as_kwarg] = None
                    return fn(*args, **kwargs)
                abort(404)
            obj = db.session.get(model, oid)
            if obj is None:
                abort(404)
            if policy and not policy(current_user, obj):
                _deny(403, f"{model.__name__}#{oid} không thuộc quyền truy cập")
            g.rbac_object = obj
            if as_kwarg:
                kwargs[as_kwarg] = obj
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# ---------------------------------------------------------------- Shortcut dễ dùng
def student_access(param: str = "uid", **kw):
    """Đối tượng là một User-học viên (Coach chỉ học viên của mình; Member chỉ chính mình)."""
    return object_access(User, param, policy=can_access_member, **kw)


def shift_access(param: str = "sid", **kw):
    from models import Shift
    return object_access(Shift, param, policy=can_access_shift, **kw)


def owned_record(model, param: str = "id", *, owner_field: str = "user_id",
                 coach_field: Optional[str] = None, **kw):
    """Bản ghi thuộc về học viên: Order, MealLog, Booking, FreezeRequest, Escalation..."""
    return object_access(model, param, policy=owner_policy(owner_field, coach_field), **kw)


def message_access(param: str = "id", **kw):
    from models import Message
    return object_access(Message, param, policy=can_access_message, **kw)


def escalation_access(param: str = "eid", **kw):
    from models import Escalation
    return object_access(Escalation, param, policy=can_access_escalation, **kw)


# ---------------------------------------------------------------- Dùng trong thân hàm
def ensure_member_access(member) -> None:
    """Kiểm tra thủ công (vd tham số tuỳ chọn ?peer=). 403 + audit log nếu không đủ quyền."""
    if not can_access_member(current_user, member):
        _deny(403, f"User#{getattr(member, 'id', None)} không thuộc quyền truy cập")


def resolve_member_target(uid: Optional[int] = None):
    """Cho trang như /app/profile?uid=X: không có uid -> chính mình; có uid -> phải đủ quyền."""
    if uid is None or uid == current_user.id:
        return current_user
    target = db.session.get(User, uid) or abort(404)
    ensure_member_access(target)
    return target


# ---------------------------------------------------------------- Lọc danh sách (query scoping)
def scope_to_user(query, owner_column):
    """Giới hạn query theo quyền. Ví dụ:
        orders = scope_to_user(Order.query, Order.user_id).all()
    Manager: tất cả | Coach: học viên của mình | Member: chỉ của mình.
    """
    role = _role()
    if role == ROLE_MANAGER:
        if current_app.config.get("MANAGER_BRANCH_SCOPED", False) and current_user.branch_id is not None:
            ids = db.session.query(User.id).filter(User.branch_id == current_user.branch_id)
            return query.filter(owner_column.in_(ids))
        return query
    if role == ROLE_COACH:
        ids = db.session.query(User.id).filter(User.role == ROLE_MEMBER, User.coach_id == current_user.id)
        return query.filter(owner_column.in_(ids))
    if role == ROLE_MEMBER:
        return query.filter(owner_column == current_user.id)
    return query.filter(sa.false())