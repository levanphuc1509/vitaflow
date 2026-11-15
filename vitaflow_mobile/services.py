"""Lớp nghiệp vụ: hạng, streak, điểm danh, gia hạn, chat, thực đơn AI."""
import json
import random
import re
from datetime import date, datetime, timedelta

from flask import current_app
from sqlalchemy import and_, func, or_

from extensions import db
from models import (DeviceToken, Report, UserBlock, Booking, BodyRecord, Checkin, Escalation, FreezeRequest, HealthProfile, MealLog,
                    Message, MenuHistory, Notification, Order, Post, PostComment, PostLike, ProgressPhoto,
                    Shift, User, Voucher, WaterLog, shift_coaches)

RANK_ORDER = ["Diamond", "Gold", "Silver", "Bronze"]
MEAL_LABELS = {"bua_sang": "Bữa sáng", "bua_trua": "Bữa trưa", "bua_toi": "Bữa tối"}


# ------------------------------------------------------------------ thông báo
def notify(user_id, text, url=None, icon="notifications"):
    """Tạo thông báo trong app và xếp hàng gửi push (gửi sau khi request kết thúc)."""
    db.session.add(Notification(user_id=user_id, text=text, url=url, icon=icon))
    from flask import g, has_request_context
    if has_request_context():
        g.setdefault("pending_push", []).append((user_id, text, url))


# ------------------------------------------------------------------ body
def body_records(user_id):
    return BodyRecord.query.filter_by(user_id=user_id).order_by(BodyRecord.day, BodyRecord.id).all()


def body_summary(user_id):
    recs = body_records(user_id)
    if not recs:
        return {"first": None, "last": None, "d_weight": 0, "d_waist": 0, "count": 0}
    first, last = recs[0], recs[-1]
    d = lambda a, b: round((b or 0) - (a or 0), 1) if a is not None and b is not None else 0
    return {"first": first, "last": last, "count": len(recs),
            "d_weight": d(first.weight_kg, last.weight_kg), "d_waist": d(first.waist_cm, last.waist_cm)}


# ------------------------------------------------------------------ hạng
def rank_info(user):
    """Điểm = chuyên cần 30 ngày + streak + thưởng + kết quả giảm cân. Trả dict hạng."""
    since = date.today() - timedelta(days=30)
    sessions = Checkin.query.filter(Checkin.user_id == user.id, Checkin.day >= since).count()
    lost = max(0, -body_summary(user.id)["d_weight"])
    score = int(sessions * 10 + (user.streak or 0) * 8 + (user.bonus_points or 0) + min(lost, 10) * 15)
    name = "Bronze"
    for rname, threshold in current_app.config["RANK_THRESHOLDS"]:
        if score >= threshold:
            name = rname
            break
    return {"name": name, "score": score, "sessions": sessions}


def ranked_members(members):
    data = [{"user": m, **rank_info(m)} for m in members]
    data.sort(key=lambda r: (RANK_ORDER.index(r["name"]), -r["score"]))
    return data


# ------------------------------------------------------------------ gói tập
def sub_status(user):
    """Trạng thái gói Gym & Coach: số ngày còn lại + mức cảnh báo."""
    today = date.today()

    def one(expires):
        if not expires:
            return {"days": 0, "state": "none", "expires": None}
        days = (expires - today).days
        state = "expired" if days < 0 else "expiring" if days <= 7 else "active"
        return {"days": days, "state": state, "expires": expires}

    gym, coach = one(user.gym_expires), one(user.coach_expires)
    worst = "expired" if gym["state"] in ("expired", "none") else gym["state"]
    return {"gym": gym, "coach": coach, "state": worst}


def extend_subscription(user, plan):
    """Cộng dồn ngày: gói còn hạn thì cộng tiếp vào ngày hết hạn."""
    today = date.today()
    if plan.kind in ("gym", "combo"):
        user.gym_expires = max(user.gym_expires or today, today) + timedelta(days=plan.days)
    if plan.kind in ("coach", "combo"):
        user.coach_expires = max(user.coach_expires or today, today) + timedelta(days=plan.days)


# ------------------------------------------------------------------ ca tập / điểm danh
def current_shift(branch_id=None, now=None):
    now = now or datetime.now()
    q = Shift.query
    if branch_id:
        q = q.filter_by(branch_id=branch_id)
    for s in q.order_by(Shift.start).all():
        if s.start <= now.time() < s.end:
            return s
    return None


def shifts_today(branch_id=None):
    q = Shift.query
    if branch_id:
        q = q.filter_by(branch_id=branch_id)
    return q.order_by(Shift.start).all()


def shift_state(shift, now=None):
    now = now or datetime.now()
    if shift.start <= now.time() < shift.end:
        return "live"
    return "done" if now.time() >= shift.end else "upcoming"


def register_checkin(user, shift_id=None, method="qr"):
    """Điểm danh + cập nhật streak. Trả (ok, message, checkin)."""
    today = date.today()
    st = sub_status(user)
    if st["gym"]["state"] in ("expired", "none"):
        return False, f"Gói tập của {user.full_name} đã hết hạn. Vui lòng gia hạn.", None
    existing = Checkin.query.filter_by(user_id=user.id, day=today, shift_id=shift_id).first()
    if existing:
        return True, f"{user.full_name} đã điểm danh lúc {existing.at:%H:%M}.", existing
    ck = Checkin(user_id=user.id, shift_id=shift_id, day=today, method=method)
    db.session.add(ck)
    last = user.last_checkin_day
    if last == today:
        pass
    elif last == today - timedelta(days=1) or (user.period_mode and last and (today - last).days <= 14):
        user.streak = (user.streak or 0) + 1
    else:
        user.streak = 1
    user.last_checkin_day = today
    user.best_streak = max(user.best_streak or 0, user.streak or 0)
    db.session.commit()
    return True, f"Điểm danh thành công: {user.full_name}.", ck


def checked_in_ids(shift_id, day=None):
    day = day or date.today()
    return {c.user_id: c for c in Checkin.query.filter_by(shift_id=shift_id, day=day).all()}


def students_of(coach):
    return User.query.filter_by(role="member", coach_id=coach.id, active=True).order_by(User.full_name).all()


def expiring_members(members, within=7):
    out = []
    for m in members:
        st = sub_status(m)
        if st["state"] in ("expired", "expiring", "none") or st["coach"]["state"] in ("expired", "expiring"):
            out.append((m, st))
    return out


# ------------------------------------------------------------------ chat
def can_chat(me, peer):
    if not peer or me.id == peer.id or not peer.active:
        return False
    if me.role == "manager":
        return peer.role in ("coach", "member")
    if me.role == "coach":
        return peer.role == "manager" or (peer.role == "member" and peer.coach_id == me.id)
    return peer.role == "manager" or (peer.role == "coach" and me.coach_id == peer.id)


def can_group(me, shift):
    if me.role == "manager":
        return True
    if me.role == "coach":
        return me in shift.coaches
    return (Booking.query.filter_by(user_id=me.id, shift_id=shift.id).first() is not None
            or Checkin.query.filter_by(user_id=me.id, shift_id=shift.id).first() is not None)


def thread_filter(me, peer_id=None, shift_id=None):
    if shift_id:
        return Message.shift_id == shift_id
    return or_(and_(Message.sender_id == me.id, Message.recipient_id == peer_id),
               and_(Message.sender_id == peer_id, Message.recipient_id == me.id))


def unread_count(me, from_id=None):
    q = Message.query.filter(Message.recipient_id == me.id, Message.read_at.is_(None))
    if from_id:
        q = q.filter(Message.sender_id == from_id)
    return q.count()


def contacts_for(me):
    """Danh sách người có thể chat + tin cuối + số tin chưa đọc."""
    if me.role == "manager":
        users = User.query.filter(User.role.in_(["coach", "member"]), User.active.is_(True)).all()
    elif me.role == "coach":
        users = students_of(me) + User.query.filter_by(role="manager").all()
    else:
        users = User.query.filter_by(role="manager").all() + ([me.coach] if me.coach and me.coach.active else [])
    out = []
    for u in users:
        last = (Message.query.filter(thread_filter(me, u.id)).order_by(Message.id.desc()).first())
        out.append({"user": u, "last": last, "unread": unread_count(me, u.id)})
    out.sort(key=lambda c: (c["last"].created_at if c["last"] else datetime.min), reverse=True)
    return out


def groups_for(me):
    if me.role == "manager":
        return Shift.query.order_by(Shift.branch_id, Shift.start).all()
    if me.role == "coach":
        return list(me.shifts)
    ids = {b.shift_id for b in Booking.query.filter_by(user_id=me.id).all()}
    ids |= {c.shift_id for c in Checkin.query.filter_by(user_id=me.id).all() if c.shift_id}
    return Shift.query.filter(Shift.id.in_(ids)).all() if ids else []


def serialize_message(m, me):
    return {"id": m.id, "mine": m.sender_id == me.id, "sender": m.sender.full_name,
            "initials": m.sender.initials, "body": m.body or "", "image": m.image_url,
            "time": m.created_at.strftime("%H:%M · %d/%m")}


# ------------------------------------------------------------------ dữ liệu xoá user
def delete_user(u):
    uid = u.id
    for s in User.query.filter_by(coach_id=uid).all():
        s.coach_id = None
    Voucher.query.filter_by(granted_by_id=uid).update({"granted_by_id": None})
    Order.query.filter_by(coach_id=uid).update({"coach_id": None})
    db.session.execute(shift_coaches.delete().where(shift_coaches.c.coach_id == uid))
    Message.query.filter(or_(Message.sender_id == uid, Message.recipient_id == uid)).delete(synchronize_session=False)
    Escalation.query.filter(or_(Escalation.coach_id == uid, Escalation.member_id == uid)).delete(synchronize_session=False)
    post_ids = [p.id for p in Post.query.filter_by(user_id=uid)]
    comment_ids = [c.id for c in PostComment.query.filter_by(user_id=uid)]
    Report.query.filter(or_(Report.reporter_id == uid, Report.target_user_id == uid, Report.post_id.in_(post_ids or [0]),
                            Report.comment_id.in_(comment_ids or [0]))).delete(synchronize_session=False)
    UserBlock.query.filter(or_(UserBlock.user_id == uid, UserBlock.blocked_id == uid)).delete(synchronize_session=False)
    DeviceToken.query.filter_by(user_id=uid).delete(synchronize_session=False)
    for p in Post.query.filter_by(user_id=uid).all():
        db.session.delete(p)
    for model in (PostLike, PostComment, Notification, Voucher, Order, Booking, Checkin, BodyRecord,
                  ProgressPhoto, WaterLog, MealLog, HealthProfile, MenuHistory, FreezeRequest):
        col = model.owner_id if model is Voucher else model.user_id
        model.query.filter(col == uid).delete(synchronize_session=False)
    db.session.delete(u)
    db.session.commit()


def next_member_code():
    codes = [int(m.group(1)) for (c,) in db.session.query(User.member_code).filter(User.member_code.isnot(None))
             if (m := re.search(r"(\d+)$", c))]
    return f"HV-{(max(codes) + 1) if codes else 101}"


def transfer_code(user, plan):
    return f"VF {user.member_code.replace('-', '')} {plan.code}"


# ------------------------------------------------------------------ dinh dưỡng
GOAL_TO_CAL = {"giam_can": "giam_can", "tang_co": "tang_can", "can_bang": "giu_can"}
ACTIVITY = {"nhe": 1.375, "vua": 1.55, "nhieu": 1.725}
WORKOUTS = {
    "giam_can": "Cardio nhẹ 25' + Pilates Reformer 30' + giãn cơ 10'",
    "tang_co": "Glutes & Core 35' + tạ nhẹ toàn thân 25' + giãn cơ 10'",
    "can_bang": "Yoga/Pilates 40' + đi bộ nhanh 15'",
}


def nutrition_stats(age, weight, height, activity, goal):
    from ai_engine import calculator
    return calculator.tinh_tat_ca(tuoi=age, gioi_tinh="nu", can_nang=weight, chieu_cao=height,
                                  he_so_van_dong=ACTIVITY.get(activity, 1.55),
                                  muc_tieu=GOAL_TO_CAL.get(goal, "giu_can"), ti_le=goal)


def _grams(name):
    m = re.search(r"~?(\d+)\s*g", name)
    return int(m.group(1)) if m else 100


def offline_menu(stats, seed):
    """Thực đơn dự phòng (không cần API): chọn món theo nhóm thực phẩm, co giãn khẩu phần."""
    from ai_engine import rag
    foods = rag.get_food_catalog()
    by_cat = {}
    for f in foods:
        by_cat.setdefault(f["TheLoai"], []).append(f)
    rnd = random.Random(seed)
    plan = {"bua_sang": (0.28, ["Món nước", "Trái cây"]),
            "bua_trua": (0.40, ["Tinh bột", "Mặn", "Rau củ"]),
            "bua_toi": (0.32, ["Tinh bột", "Hải sản", "Rau củ"])}
    target = stats["calo_muc_tieu"]
    menu = {}
    for key, (share, cats) in plan.items():
        picks = [rnd.choice(by_cat[c]) for c in cats if by_cat.get(c)]
        base = sum(float(p["Calo"]) for p in picks) or 1
        k = max(0.6, min(1.5, target * share / base))
        menu[key] = [{"ten_mon": p["TenMon"], "dinh_luong_g": round(_grams(p["TenMon"]) * k),
                      "calo": round(float(p["Calo"]) * k)} for p in picks]
    return menu


def generate_menu(stats, notes, seed, fresh=False):
    """Gọi Gemini nếu có key; lỗi/không có key thì dùng thực đơn offline. Trả (menu, meta)."""
    import os
    if (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip():
        try:
            from ai_engine import llm, rag
            ctx, allowed = rag.get_prompt_catalog()
            return llm.generate_menu(stats, ctx, notes, allowed_food_names=allowed, fresh=fresh, return_meta=True)
        except Exception as exc:  # noqa: BLE001
            current_app.logger.warning("Gemini lỗi, dùng thực đơn offline: %s", exc)
    return offline_menu(stats, seed), {"cached": False, "model": "offline", "seconds": 0.0}


def similar_food(name, calo):
    """Món tương đương: cùng nhóm, calo gần nhất, khác tên."""
    from ai_engine import rag
    foods = rag.get_food_catalog()
    cur = next((f for f in foods if f["TenMon"] == name), None)
    pool = [f for f in foods if f["TenMon"] != name and (not cur or f["TheLoai"] == cur["TheLoai"])]
    if not pool:
        return None
    pool.sort(key=lambda f: abs(float(f["Calo"]) - float(calo)))
    f = random.choice(pool[:3])
    return {"ten_mon": f["TenMon"], "dinh_luong_g": _grams(f["TenMon"]), "calo": round(float(f["Calo"]))}


def today_menu(user_id):
    return MenuHistory.query.filter_by(user_id=user_id, day=date.today()).order_by(MenuHistory.id.desc()).first()


def water_today(user_id):
    w = WaterLog.query.filter_by(user_id=user_id, day=date.today()).first()
    return w.ml if w else 0


# ------------------------------------------------------------------ QR & token
def _ser(salt):
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def member_token(user):
    return "VFM." + _ser("member-qr").dumps({"u": user.id})


def parse_member_token(raw):
    """Nhận mã QR cá nhân hoặc mã hội viên gõ tay (HV-102). Trả User hoặc None."""
    raw = (raw or "").strip()
    _, separator, payload = raw.partition(".")
    if separator:
        from itsdangerous import BadSignature
        try:
            return db.session.get(User, _ser("member-qr").loads(payload)["u"])
        except (BadSignature, KeyError):
            return None
    code = raw.upper().replace(" ", "")
    if re.fullmatch(r"HV\d+", code):
        code = "HV-" + code[2:]
    return User.query.filter_by(member_code=code, role="member").first()


def shift_token(shift):
    return _ser("shift-qr").dumps({"s": shift.id, "d": date.today().isoformat()})


def parse_shift_token(token, max_age=180):
    from itsdangerous import BadSignature
    try:
        data = _ser("shift-qr").loads(token, max_age=max_age)
    except BadSignature:
        return None
    if data.get("d") != date.today().isoformat():
        return None
    return db.session.get(Shift, data["s"])


def qr_svg(data, scale=6, dark="#111827"):
    import segno
    return segno.make(data, error="m").svg_inline(scale=scale, dark=dark, light=None, border=1)


def grant_voucher(owner, by, title, percent, message="", days=30):
    v = Voucher(owner_id=owner.id, granted_by_id=by.id, title=title, percent=percent, message=message[:300],
                expires_on=date.today() + timedelta(days=days))
    db.session.add(v)
    notify(owner.id, f"{by.full_name} gửi bạn quà: {title} (-{percent}%)", "/app/rewards", "redeem")
    return v
