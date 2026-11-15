"""API JSON dùng chung: chat Messenger, chuyển tiếp lên quản lý, thông báo.

Bảo mật (Object-level Authorization):
  - Mọi endpoint dùng @api_login_required: chưa đăng nhập -> JSON 401 (không redirect), tài khoản bị khoá -> 403.
  - Chat: thread luôn được dựng từ current_user + can_chat()/can_group() + thread_filter();
    người dùng không bao giờ chỉ định được "người gửi" hay đọc thread của người khác.
  - Escalate: @student_access -> Coach chỉ chuyển tiếp học viên của chính mình.
  - Notification / Device: luôn ràng buộc user_id = current_user.id.
  - Giới hạn tần suất cho các endpoint ghi (chống spam/brute-force).
  - Mọi lỗi abort() trong blueprint này trả JSON để app mobile xử lý thống nhất.
"""
import re
from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user
from werkzeug.exceptions import HTTPException

from api_guard import api_login_required, json_error, json_http_error
from extensions import db
from models import DeviceToken, Escalation, Message, Notification, Shift, User, UserBlock
from security import student_access
from services import (can_chat, can_group, notify, serialize_message, thread_filter)
from throttle import rate_limit
from utils import save_image

bp = Blueprint("api", __name__, url_prefix="/api")
bp.register_error_handler(HTTPException, json_http_error)

_TOKEN_RE = re.compile(r"^[A-Za-z0-9:_\-\.]{20,400}$")      # FCM / APNs
_PLATFORMS = {"android", "ios", "web"}


def _resolve(args):
    """Xác định thread: 1-1 (peer) hoặc nhóm ca (shift). Trả (peer_id, shift_id).
    Không tồn tại và không đủ quyền đều trả 403 (không để dò ID có tồn tại hay không)."""
    peer_id, shift_id = args.get("peer", type=int), args.get("shift", type=int)
    if shift_id:
        shift = db.session.get(Shift, shift_id)
        if shift is None or not can_group(current_user, shift):
            abort(403)
        return None, shift_id
    peer = db.session.get(User, peer_id or 0)
    if peer is None or peer.id == current_user.id or not can_chat(current_user, peer):
        abort(403)
    return peer.id, None


# ---------------------------------------------------------------- Chat
@bp.get("/chat/messages")
@api_login_required()
def chat_messages():
    peer_id, shift_id = _resolve(request.args)
    after = request.args.get("after", 0, type=int)
    q = Message.query.filter(thread_filter(current_user, peer_id, shift_id), Message.id > after)
    if shift_id:  # chat nhóm: ẩn tin của người mình đã chặn
        blocked = [b.blocked_id for b in UserBlock.query.filter_by(user_id=current_user.id)]
        if blocked:
            q = q.filter(~Message.sender_id.in_(blocked))
    msgs = q.order_by(Message.id).limit(200).all()
    if peer_id:
        for m in msgs:
            if m.recipient_id == current_user.id and not m.read_at:
                m.read_at = datetime.now()
        db.session.commit()
    return jsonify(ok=True, messages=[serialize_message(m, current_user) for m in msgs])


@bp.post("/chat/send")
@api_login_required()
@rate_limit("chat_send", config_key="RATE_CHAT_SEND", default=(30, 60))
def chat_send():
    peer_id, shift_id = _resolve(request.form)
    body = (request.form.get("body") or "").strip()[:2000]
    image = save_image(request.files.get("image"))
    if not body and not image:
        return json_error(400, "Tin nhắn trống.")
    # sender_id luôn là người đang đăng nhập - không nhận từ client
    m = Message(sender_id=current_user.id, recipient_id=peer_id, shift_id=shift_id, body=body, image_url=image)
    db.session.add(m)
    if peer_id:
        notify(peer_id, f"{current_user.full_name}: {body[:60] or '[Hình ảnh]'}", icon="chat")
    db.session.commit()
    return jsonify(ok=True, message=serialize_message(m, current_user))


@bp.post("/chat/escalate")
@api_login_required(roles=("coach",))
@rate_limit("escalate", config_key="RATE_ESCALATE", default=(10, 3600))
@student_access("member_id", sources=("form",), as_kwarg="member")
def chat_escalate(member):
    """Coach chuyển tiếp vấn đề của học viên lên Quản lý.
    @student_access đảm bảo member.role == 'member' và member.coach_id == current_user.id."""
    reason = (request.form.get("reason") or "").strip()[:500]
    if not reason:
        return json_error(400, "Vui lòng nhập nội dung cần chuyển tiếp.")
    db.session.add(Escalation(coach_id=current_user.id, member_id=member.id, reason=reason))
    for mgr in User.query.filter_by(role="manager", active=True).all():
        notify(mgr.id, f"Coach {current_user.full_name} chuyển tiếp vấn đề của {member.full_name}",
               "/manager/nutrition", "flag")
    db.session.commit()
    return jsonify(ok=True, message="Đã chuyển tiếp lên Quản lý.")


# ---------------------------------------------------------------- Thông báo
@bp.post("/notifications/read")
@api_login_required()
def notifications_read():
    Notification.query.filter_by(user_id=current_user.id, read=False).update({"read": True})
    db.session.commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- Thiết bị (push)
@bp.post("/device/register")
@api_login_required()
@rate_limit("device_register", config_key="RATE_DEVICE", default=(10, 60))
def device_register():
    """App native gửi token FCM/APNs sau khi người dùng cho phép nhận thông báo.
    Token luôn gắn với current_user: đổi tài khoản trên cùng thiết bị thì token chuyển sang người mới."""
    token = (request.form.get("token") or "").strip()
    platform = (request.form.get("platform") or "").strip().lower()
    if not _TOKEN_RE.match(token):
        return json_error(400, "Token không hợp lệ.")
    if platform not in _PLATFORMS:
        return json_error(400, "Nền tảng không hợp lệ.")
    d = DeviceToken.query.filter_by(token=token).first()
    if d:
        d.user_id, d.last_seen = current_user.id, datetime.now()
    else:
        d = DeviceToken(user_id=current_user.id, token=token)
        db.session.add(d)
    d.platform = platform
    db.session.commit()
    return jsonify(ok=True)


@bp.post("/device/unregister")
@api_login_required()
def device_unregister():
    token = (request.form.get("token") or "").strip()
    DeviceToken.query.filter_by(token=token, user_id=current_user.id).delete()   # chỉ xoá token của chính mình
    db.session.commit()
    return jsonify(ok=True)
