"""API JSON dùng chung: chat Messenger, chuyển tiếp lên quản lý, thông báo."""
from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from extensions import db
from models import Escalation, Message, Notification, Shift, User
from services import (can_chat, can_group, notify, serialize_message, thread_filter)
from utils import coach_required, save_image

bp = Blueprint("api", __name__, url_prefix="/api")


def _resolve(args):
    """Xác định thread: 1-1 (peer) hoặc nhóm ca (shift). Trả (peer_id, shift_id)."""
    peer_id, shift_id = args.get("peer", type=int), args.get("shift", type=int)
    if shift_id:
        shift = db.session.get(Shift, shift_id) or abort(404)
        if not can_group(current_user, shift):
            abort(403)
        return None, shift_id
    peer = db.session.get(User, peer_id or 0)
    if not can_chat(current_user, peer):
        abort(403)
    return peer.id, None


@bp.get("/chat/messages")
@login_required
def chat_messages():
    peer_id, shift_id = _resolve(request.args)
    after = request.args.get("after", 0, type=int)
    q = Message.query.filter(thread_filter(current_user, peer_id, shift_id), Message.id > after)
    msgs = q.order_by(Message.id).limit(200).all()
    if peer_id:
        for m in msgs:
            if m.recipient_id == current_user.id and not m.read_at:
                m.read_at = datetime.now()
        db.session.commit()
    return jsonify(ok=True, messages=[serialize_message(m, current_user) for m in msgs])


@bp.post("/chat/send")
@login_required
def chat_send():
    peer_id, shift_id = _resolve(request.form)
    body = (request.form.get("body") or "").strip()[:2000]
    image = save_image(request.files.get("image"))
    if not body and not image:
        return jsonify(ok=False, error="Tin nhắn trống."), 400
    m = Message(sender_id=current_user.id, recipient_id=peer_id, shift_id=shift_id, body=body, image_url=image)
    db.session.add(m)
    if peer_id:
        notify(peer_id, f"{current_user.full_name}: {body[:60] or '[Hình ảnh]'}", icon="chat")
    db.session.commit()
    return jsonify(ok=True, message=serialize_message(m, current_user))


@bp.post("/chat/escalate")
@coach_required
def chat_escalate():
    """Coach chuyển tiếp vấn đề của học viên lên Quản lý."""
    member = db.session.get(User, request.form.get("member_id", type=int) or 0)
    reason = (request.form.get("reason") or "").strip()[:500]
    if not member or member.coach_id != current_user.id:
        abort(403)
    if not reason:
        return jsonify(ok=False, error="Vui lòng nhập nội dung cần chuyển tiếp."), 400
    db.session.add(Escalation(coach_id=current_user.id, member_id=member.id, reason=reason))
    for mgr in User.query.filter_by(role="manager", active=True).all():
        notify(mgr.id, f"Coach {current_user.full_name} chuyển tiếp vấn đề của {member.full_name}",
               "/manager/nutrition", "flag")
    db.session.commit()
    return jsonify(ok=True, message="Đã chuyển tiếp lên Quản lý.")


@bp.post("/notifications/read")
@login_required
def notifications_read():
    Notification.query.filter_by(user_id=current_user.id, read=False).update({"read": True})
    db.session.commit()
    return jsonify(ok=True)
