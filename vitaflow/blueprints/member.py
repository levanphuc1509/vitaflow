"""Cổng Thành viên (Member Portal) - mạng xã hội thu nhỏ, tông Pink & Lavender."""
import calendar
import json
import time as _time
from datetime import date, datetime, timedelta
from urllib.parse import quote

from flask import (Blueprint, abort, current_app, flash, jsonify, redirect, request, session,
                   url_for)
from flask_login import current_user

from extensions import db
from models import (Booking, BodyRecord, Branch, Checkin, FreezeRequest, HealthProfile, MealLog, MenuHistory,
                    Order, Plan, Post, PostComment, PostLike, ProgressPhoto, Shift, User, Voucher, WaterLog)
from services import (MEAL_LABELS, RANK_ORDER, WORKOUTS, body_records, body_summary, contacts_for, current_shift,
                      extend_subscription, generate_menu, groups_for, member_token, notify, nutrition_stats,
                      parse_shift_token, qr_svg, rank_info, ranked_members, register_checkin, shifts_today, similar_food,
                      sub_status, today_menu, transfer_code, water_today)
from utils import float_or, int_or, is_mobile, member_required, render_template, save_image
from throttle import clear, key_for, locked_for, register
from security import owned_record, resolve_member_target, scope_to_user

bp = Blueprint("member", __name__, url_prefix="/app")


# ======================================================================= Bảng tin
@bp.route("/")
@member_required
def feed():
    me = current_user
    posts = Post.query.order_by(Post.created_at.desc()).limit(30).all()
    liked = {l.post_id for l in PostLike.query.filter_by(user_id=me.id).all()}
    ranks = {}
    for p in posts:
        if p.user_id not in ranks:
            ranks[p.user_id] = rank_info(p.user)["name"]
    branch_shifts = shifts_today(me.branch_id)
    return render_template("member/feed.html", posts=posts, liked=liked, ranks=ranks, shifts=branch_shifts,
                           water=water_today(me.id), goal=current_app.config["WATER_GOAL_ML"],
                           my_rank=rank_info(me), status=sub_status(me), cur=current_shift(me.branch_id))


@bp.post("/post")
@member_required
def post_create():
    body = request.form.get("body", "").strip()[:1500]
    kind = request.form.get("kind", "general")
    kind = kind if kind in ("checkin", "meal", "general") else "general"
    img = save_image(request.files.get("image"))
    if not body and not img:
        flash("Hãy viết gì đó hoặc chọn một tấm ảnh nhé.", "warning")
    else:
        db.session.add(Post(user_id=current_user.id, kind=kind, body=body, image_url=img))
        db.session.commit()
        flash("Đã đăng lên bảng tin!", "success")
    return redirect(url_for("member.feed"))


@bp.post("/post/<int:pid>/like")
@member_required
def post_like(pid):
    p = db.session.get(Post, pid) or abort(404)
    like = PostLike.query.filter_by(post_id=pid, user_id=current_user.id).first()
    if like:
        db.session.delete(like)
        state = False
    else:
        db.session.add(PostLike(post_id=pid, user_id=current_user.id))
        state = True
        if p.user_id != current_user.id:
            notify(p.user_id, f"{current_user.full_name} đã thả tim bài viết của bạn", "/app/", "favorite")
    db.session.commit()
    return jsonify(ok=True, liked=state, count=PostLike.query.filter_by(post_id=pid).count())


@bp.post("/post/<int:pid>/comment")
@member_required
def post_comment(pid):
    p = db.session.get(Post, pid) or abort(404)
    body = request.form.get("body", "").strip()[:500]
    if body:
        db.session.add(PostComment(post_id=pid, user_id=current_user.id, body=body))
        if p.user_id != current_user.id:
            notify(p.user_id, f"{current_user.full_name} đã bình luận bài viết của bạn", "/app/", "chat_bubble")
        db.session.commit()
    return redirect(url_for("member.feed") + f"#post-{pid}")


@bp.post("/post/<int:pid>/delete")
@member_required
def post_delete(pid):
    p = db.session.get(Post, pid) or abort(404)
    if p.user_id != current_user.id:
        abort(403)
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for("member.feed"))


@bp.post("/water")
@member_required
def water():
    delta = max(-1000, min(1000, int_or(request.form.get("ml"), 0)))
    w = WaterLog.query.filter_by(user_id=current_user.id, day=date.today()).first()
    if not w:
        w = WaterLog(user_id=current_user.id, day=date.today(), ml=0)
        db.session.add(w)
    w.ml = max(0, min(6000, w.ml + delta))
    db.session.commit()
    return jsonify(ok=True, ml=w.ml, goal=current_app.config["WATER_GOAL_ML"])


@bp.post("/period-mode")
@member_required
def period_mode():
    current_user.period_mode = not current_user.period_mode
    db.session.commit()
    return jsonify(ok=True, on=current_user.period_mode, streak=current_user.streak)


@bp.post("/invite")
@member_required
def invite():
    shift = db.session.get(Shift, request.form.get("shift_id", type=int) or 0) or abort(404)
    msg = request.form.get("message", "").strip()[:200] or "Ai tập cùng mình không nè? 💪"
    db.session.add(Post(user_id=current_user.id, kind="invite", shift_id=shift.id,
                        body=f"{msg}\n📍 {shift.name} · {shift.start:%H:%M}-{shift.end:%H:%M} · {shift.branch.name}"))
    db.session.commit()
    flash("Đã đăng lời rủ bạn tập cùng lên bảng tin!", "success")
    return redirect(url_for("member.feed"))


# ======================================================================= Hồ sơ & Nhật ký Body
def _photos_unlocked():
    return session.get("photos_until", 0) > _time.time()


@bp.route("/profile")
@member_required
def profile():
    target = resolve_member_target(request.args.get("uid", type=int))
    me = current_user
    recs = body_records(me.id)
    chart = {"labels": [f"{r.day:%d/%m}" for r in recs], "weight": [r.weight_kg for r in recs],
             "waist": [r.waist_cm for r in recs]}
    photos = {k: ProgressPhoto.query.filter_by(user_id=me.id, kind=k).order_by(ProgressPhoto.id.desc()).first()
              for k in ("before", "after")}
    return render_template("member/profile.html", recs=list(reversed(recs)), chart=chart, summary=body_summary(me.id),
                           rank=rank_info(me), photos=photos, unlocked=_photos_unlocked(), status=sub_status(me),
                           total_checkins=Checkin.query.filter_by(user_id=me.id).count())


@bp.post("/profile/record")
@member_required
def profile_record():
    f = request.form
    w, waist = float_or(f.get("weight_kg")), float_or(f.get("waist_cm"))
    if w is None or not 25 <= w <= 300 or (waist is not None and not 40 <= waist <= 200):
        flash("Vui lòng nhập cân nặng (25-300kg) và vòng eo hợp lệ.", "error")
        return redirect(url_for("member.profile"))
    db.session.add(BodyRecord(user_id=current_user.id, day=date.today(), weight_kg=w, waist_cm=waist,
                              hip_cm=float_or(f.get("hip_cm")), bust_cm=float_or(f.get("bust_cm")),
                              height_cm=float_or(f.get("height_cm")), body_fat=float_or(f.get("body_fat")),
                              note=f.get("note", "").strip()[:200]))
    db.session.commit()
    flash("Đã cập nhật số đo mới. Cố lên nhé! 💗", "success")
    return redirect(url_for("member.profile"))


@bp.post("/profile/goal")
@member_required
def profile_goal():
    current_user.goal = request.form.get("goal", "").strip()[:200]
    db.session.commit()
    flash("Đã cập nhật mục tiêu.", "success")
    return redirect(url_for("member.profile"))


@bp.post("/profile/photo")
@member_required
def profile_photo():
    kind = request.form.get("kind")
    url = save_image(request.files.get("image"))
    if kind not in ("before", "after") or not url:
        flash("Ảnh không hợp lệ (chỉ nhận PNG/JPG/WEBP).", "error")
    else:
        db.session.add(ProgressPhoto(user_id=current_user.id, kind=kind, url=url))
        db.session.commit()
        flash("Đã lưu ảnh vào kho riêng tư.", "success")
    return redirect(url_for("member.profile"))


@bp.post("/profile/visibility")
@member_required
def profile_visibility():
    v = request.form.get("visibility")
    current_user.photo_visibility = v if v in ("me_coach", "only_me") else "me_coach"
    db.session.commit()
    return jsonify(ok=True, visibility=current_user.photo_visibility)


@bp.post("/profile/unlock")
@member_required
def profile_unlock():
    if request.form.get("lock"):
        session.pop("photos_until", None)
        return jsonify(ok=True)
    if current_user.check_password(request.form.get("password", "")):
        session["photos_until"] = _time.time() + 600
        return jsonify(ok=True)
    return jsonify(ok=False, error="Mật khẩu chưa đúng."), 403


# ======================================================================= Lịch ca & đặt chỗ
@bp.route("/schedule")
@member_required
def schedule():
    me = current_user
    today = date.today()
    try:
        y, m = [int(x) for x in request.args.get("m", today.strftime("%Y-%m")).split("-")]
        first = date(y, m, 1)
    except ValueError:
        first = today.replace(day=1)
    try:
        sel = date.fromisoformat(request.args.get("d", today.isoformat()))
    except ValueError:
        sel = today
    weeks = calendar.Calendar(0).monthdatescalendar(first.year, first.month)
    start, end = weeks[0][0], weeks[-1][-1]
    bookings = Booking.query.filter(Booking.user_id == me.id, Booking.day.between(start, end)).all()
    checks = {c.day for c in Checkin.query.filter(Checkin.user_id == me.id, Checkin.day.between(start, end)).all()}
    booked_days = {b.day for b in bookings if b.status == "booked"}
    shift_rows = []
    for s in shifts_today(me.branch_id):
        taken = Booking.query.filter_by(shift_id=s.id, day=sel, status="booked").count()
        mine = next((b for b in bookings if b.shift_id == s.id and b.day == sel), None) or \
            Booking.query.filter_by(user_id=me.id, shift_id=s.id, day=sel).first()
        shift_rows.append({"shift": s, "taken": taken, "mine": mine})
    upcoming = (Booking.query.filter(Booking.user_id == me.id, Booking.day >= today)
                .order_by(Booking.day).limit(10).all())
    prev_m, next_m = (first - timedelta(days=1)).replace(day=1), (first + timedelta(days=32)).replace(day=1)
    return render_template("member/schedule.html", weeks=weeks, first=first, sel=sel, checks=checks,
                           booked_days=booked_days, shift_rows=shift_rows, upcoming=upcoming,
                           prev_m=prev_m.strftime("%Y-%m"), next_m=next_m.strftime("%Y-%m"),
                           status=sub_status(me), all_shifts=shifts_today(me.branch_id))


def _back(sel):
    return redirect(url_for("member.schedule", d=sel.isoformat(), m=sel.strftime("%Y-%m")))


@bp.post("/schedule/book")
@member_required
def book():
    shift = db.session.get(Shift, request.form.get("shift_id", type=int) or 0) or abort(404)
    try:
        day = date.fromisoformat(request.form.get("day", ""))
    except ValueError:
        abort(400)
    exp = current_user.gym_expires
    if day < date.today():
        flash("Không thể đặt chỗ cho ngày đã qua.", "error")
    elif not exp or day > exp:
        flash("Gói tập của bạn không còn hiệu lực vào ngày này. Hãy gia hạn nhé!", "warning")
    elif Booking.query.filter_by(user_id=current_user.id, shift_id=shift.id, day=day).first():
        flash("Bạn đã đặt ca này rồi.", "warning")
    elif Booking.query.filter_by(shift_id=shift.id, day=day, status="booked").count() >= shift.capacity:
        flash("Ca này đã đủ chỗ. Hãy chọn ca khác.", "warning")
    else:
        db.session.add(Booking(user_id=current_user.id, shift_id=shift.id, day=day))
        db.session.commit()
        flash(f"Đã đặt chỗ {shift.name} ngày {day:%d/%m}.", "success")
    return _back(day)


def _own_booking(bid):
    b = db.session.get(Booking, bid) or abort(404)
    if b.user_id != current_user.id:
        abort(403)
    return b


@bp.post("/schedule/<int:bid>/absent")
@member_required
@owned_record(Booking, "bid", owner_field="user_id", as_kwarg="b")
def absent(bid, b):
    b.status, b.note = "absent", request.form.get("note", "").strip()[:200] or "Báo vắng"
    if b.shift.coaches and current_user.coach_id:
        notify(current_user.coach_id, f"{current_user.full_name} báo vắng {b.shift.name} ngày {b.day:%d/%m}", None, "event_busy")
    db.session.commit()
    flash("Đã báo vắng. Streak vẫn được giữ nếu bạn đang trong kỳ nghỉ sinh lý.", "success")
    return _back(b.day)


@bp.post("/schedule/<int:bid>/swap")
@member_required
@owned_record(Booking, "bid", owner_field="user_id", as_kwarg="b")
def swap(bid, b):
    new = db.session.get(Shift, request.form.get("shift_id", type=int) or 0) or abort(404)
    if Booking.query.filter_by(user_id=current_user.id, shift_id=new.id, day=b.day).first():
        flash("Bạn đã có lịch ở ca đó rồi.", "warning")
    elif Booking.query.filter_by(shift_id=new.id, day=b.day, status="booked").count() >= new.capacity:
        flash("Ca muốn đổi đã đủ chỗ.", "warning")
    else:
        b.shift_id, b.status = new.id, "booked"
        db.session.commit()
        flash(f"Đã đổi sang {new.name}.", "success")
    return _back(b.day)


@bp.post("/schedule/<int:bid>/cancel")
@member_required
@owned_record(Booking, "bid", owner_field="user_id", as_kwarg="b")
def cancel(bid, b):
    day = b.day
    db.session.delete(b)
    db.session.commit()
    flash("Đã huỷ đặt chỗ.", "success")
    return _back(day)


# ======================================================================= AI Coach & nhật ký bữa ăn
def _menu_ctx(me):
    menu_row = today_menu(me.id)
    menu = json.loads(menu_row.menu_data) if menu_row else None
    logs = {l.meal_key: l for l in MealLog.query.filter_by(user_id=me.id, day=date.today()).all()}
    return {"menu_row": menu_row, "menu": menu, "logs": logs}


@bp.route("/nutrition")
@member_required
def nutrition():
    me = current_user
    prof = me.health_profile
    if not prof:
        last = body_summary(me.id)["last"]
        prof = HealthProfile(age=30, height_cm=(last.height_cm if last and last.height_cm else 160),
                             weight_kg=(last.weight_kg if last else 55), activity_level="vua", fitness_goal="giam_can")
    stats = None
    if prof.bmr:
        stats = {"bmr": prof.bmr, "tdee": prof.tdee, "calo_muc_tieu": prof.target_calories,
                 "macro": {"protein_g": prof.protein_g, "carb_g": prof.carb_g, "fat_g": prof.fat_g}}
    return render_template("member/nutrition.html", prof=prof, stats=stats, water=water_today(me.id),
                           goal=current_app.config["WATER_GOAL_ML"], **_menu_ctx(me))


@bp.post("/nutrition/generate")
@member_required
def nutrition_generate():
    f, me = request.form, current_user
    age, weight, height = int_or(f.get("age")), float_or(f.get("weight")), float_or(f.get("height"))
    activity, goal = f.get("activity", "vua"), f.get("goal", "giam_can")
    if not (age and 18 <= age <= 100 and weight and 25 <= weight <= 300 and height and 100 <= height <= 250) \
            or activity not in ("nhe", "vua", "nhieu") or goal not in ("giam_can", "tang_co", "can_bang"):
        return jsonify(ok=False, error="Vui lòng kiểm tra lại tuổi (≥18), cân nặng và chiều cao."), 400
    notes = f.get("notes", "").strip()[:1000]
    try:
        stats = nutrition_stats(age, weight, height, activity, goal)
        seed = f"{me.id}-{date.today()}-{_time.time() if f.get('fresh') else ''}"
        menu, meta = generate_menu(stats, notes, seed=seed, fresh=bool(f.get("fresh")))
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("Lỗi tạo thực đơn")
        return jsonify(ok=False, error=getattr(exc, "user_message", "Không tạo được thực đơn lúc này, thử lại nhé.")), 502
    prof = me.health_profile or HealthProfile(user_id=me.id)
    prof.age, prof.weight_kg, prof.height_cm, prof.activity_level, prof.fitness_goal, prof.notes = \
        age, weight, height, activity, goal, notes
    prof.bmr, prof.tdee, prof.target_calories = stats["bmr"], stats["tdee"], stats["calo_muc_tieu"]
    prof.protein_g, prof.carb_g, prof.fat_g = (stats["macro"][k] for k in ("protein_g", "carb_g", "fat_g"))
    db.session.add(prof)
    MenuHistory.query.filter_by(user_id=me.id, day=date.today()).delete()
    db.session.add(MenuHistory(user_id=me.id, title=f"Thực đơn ngày {date.today():%d/%m/%Y}",
                               total_calo=round(stats["calo_muc_tieu"]), menu_data=json.dumps(menu, ensure_ascii=False),
                               source="offline" if meta.get("model") == "offline" else "ai", workout=WORKOUTS[goal]))
    db.session.commit()
    return jsonify(ok=True, stats=stats, html=render_template("partials/menu_card.html", **_menu_ctx(me), stats=stats,
                                                              editable=True))


@bp.post("/nutrition/swap")
@member_required
def nutrition_swap():
    row = today_menu(current_user.id)
    meal, idx = request.form.get("meal"), int_or(request.form.get("index"), -1)
    if not row or meal not in MEAL_LABELS:
        return jsonify(ok=False, error="Chưa có thực đơn hôm nay."), 400
    menu = json.loads(row.menu_data)
    if not 0 <= idx < len(menu.get(meal, [])):
        return jsonify(ok=False, error="Món không tồn tại."), 400
    cur = menu[meal][idx]
    new = similar_food(cur["ten_mon"], cur["calo"])
    if not new:
        return jsonify(ok=False, error="Chưa có món tương đương."), 400
    menu[meal][idx] = new
    row.menu_data = json.dumps(menu, ensure_ascii=False)
    db.session.commit()
    return jsonify(ok=True, html=render_template("partials/menu_card.html", **_menu_ctx(current_user), stats=None,
                                                 editable=True))


@bp.post("/nutrition/followed")
@member_required
def nutrition_followed():
    meal = request.form.get("meal")
    if meal not in MEAL_LABELS:
        abort(400)
    log = MealLog.query.filter_by(user_id=current_user.id, day=date.today(), meal_key=meal).first()
    if not log:
        log = MealLog(user_id=current_user.id, day=date.today(), meal_key=meal)
        db.session.add(log)
    gained = 0
    if not log.followed_ai:
        log.followed_ai = True
        current_user.bonus_points = (current_user.bonus_points or 0) + 5
        gained = 5
    db.session.commit()
    return jsonify(ok=True, gained=gained)


@bp.post("/nutrition/photo")
@member_required
def nutrition_photo():
    from models import Message
    meal = request.form.get("meal", "bua_trua")
    url = save_image(request.files.get("image"))
    if meal not in MEAL_LABELS or not url:
        flash("Vui lòng chọn ảnh hợp lệ.", "error")
        return redirect(url_for("member.nutrition"))
    log = MealLog.query.filter_by(user_id=current_user.id, day=date.today(), meal_key=meal).first()
    if not log:
        log = MealLog(user_id=current_user.id, day=date.today(), meal_key=meal)
        db.session.add(log)
    log.photo_url = url
    if current_user.coach_id:
        db.session.add(Message(sender_id=current_user.id, recipient_id=current_user.coach_id, image_url=url,
                               body=f"Em gửi Coach mâm cơm {MEAL_LABELS[meal].lower()} hôm nay ạ 🍚"))
        notify(current_user.coach_id, f"{current_user.full_name} gửi ảnh {MEAL_LABELS[meal].lower()} để chấm điểm",
               f"/coach/nutrition?peer={current_user.id}", "photo_camera")
    if request.form.get("share"):
        db.session.add(Post(user_id=current_user.id, kind="meal", image_url=url,
                            body=f"{MEAL_LABELS[meal]} hôm nay theo thực đơn AI 🥗"))
    db.session.commit()
    flash("Đã gửi ảnh cho Coach!" if current_user.coach_id else "Đã lưu ảnh bữa ăn.", "success")
    return redirect(url_for("member.nutrition"))


# ======================================================================= QR cá nhân & điểm danh qua QR ca
@bp.route("/qr")
@member_required
def qr():
    me = current_user
    today_ck = Checkin.query.filter_by(user_id=me.id, day=date.today()).order_by(Checkin.at.desc()).first()
    return render_template("member/qr.html", svg=qr_svg(member_token(me), scale=7), status=sub_status(me),
                           today_ck=today_ck)


@bp.route("/checkin/shift/<token>")
@member_required
def shift_checkin(token):
    shift = parse_shift_token(token)
    if not shift:
        flash("Mã QR của ca đã hết hạn. Hãy quét lại mã đang hiển thị ở quầy.", "warning")
        return redirect(url_for("member.qr"))
    ok, msg, _ = register_checkin(current_user, shift.id, method="qr")
    flash(msg, "success" if ok else "error")
    return redirect(url_for("member.feed" if ok else "member.membership"))


# ======================================================================= Tin nhắn
@bp.route("/messages")
@member_required
def messages():
    contacts = contacts_for(current_user)
    groups = groups_for(current_user)
    peer = db.session.get(User, request.args.get("peer", type=int) or 0)
    group = db.session.get(Shift, request.args.get("shift", type=int) or 0)
    if not peer and not group and contacts and not is_mobile():
        peer = next((c["user"] for c in contacts if c["user"].id == current_user.coach_id), contacts[0]["user"])
    return render_template("member/messages.html", contacts=contacts, groups=groups, peer=peer, group=group)


# ======================================================================= Xếp hạng & ví quà
@bp.route("/rewards")
@member_required
def rewards():
    me = current_user
    mine = rank_info(me)
    board = ranked_members(User.query.filter_by(role="member", active=True, branch_id=me.branch_id).all())
    board.sort(key=lambda r: -r["score"])
    position = next((i + 1 for i, r in enumerate(board) if r["user"].id == me.id), None)
    thresholds = dict(current_app.config["RANK_THRESHOLDS"])
    idx = RANK_ORDER.index(mine["name"])
    nxt = RANK_ORDER[idx - 1] if idx > 0 else None
    vouchers = Voucher.query.filter_by(owner_id=me.id).order_by(Voucher.id.desc()).all()
    return render_template("member/rewards.html", mine=mine, board=board[:10], position=position, nxt=nxt,
                           need=(thresholds[nxt] - mine["score"]) if nxt else 0,
                           nxt_total=thresholds[nxt] if nxt else mine["score"], vouchers=vouchers)


# ======================================================================= Gói tập
@bp.route("/membership")
@member_required
def membership():
    me = current_user
    orders = Order.query.filter_by(user_id=me.id).order_by(Order.id.desc()).limit(10).all()
    freezes = FreezeRequest.query.filter_by(user_id=me.id).order_by(FreezeRequest.id.desc()).limit(5).all()
    plans = Plan.query.filter_by(active=True).order_by(Plan.price).all()
    return render_template("member/membership.html", status=sub_status(me), orders=orders, freezes=freezes, plans=plans,
                           pending_freeze=any(f.status == "pending" for f in freezes))


@bp.post("/membership/freeze")
@member_required
def freeze():
    days, reason = int_or(request.form.get("days"), 0), request.form.get("reason", "").strip()[:300]
    if not sub_status(current_user)["gym"]["days"] > 0:
        flash("Bạn cần có gói tập còn hiệu lực để xin bảo lưu.", "warning")
    elif not 7 <= days <= 60:
        flash("Thời gian bảo lưu từ 7 đến 60 ngày.", "error")
    elif FreezeRequest.query.filter_by(user_id=current_user.id, status="pending").first():
        flash("Bạn đang có một yêu cầu bảo lưu chờ duyệt.", "warning")
    else:
        db.session.add(FreezeRequest(user_id=current_user.id, days=days, reason=reason))
        for mgr in User.query.filter_by(role="manager", active=True).all():
            notify(mgr.id, f"{current_user.full_name} xin bảo lưu thẻ {days} ngày", "/manager/rewards?tab=freeze", "pause_circle")
        db.session.commit()
        flash("Đã gửi yêu cầu bảo lưu tới Quản lý.", "success")
    return redirect(url_for("member.membership"))


# ======================================================================= Cửa hàng nạp gói
@bp.route("/shop")
@member_required
def shop():
    me = current_user
    plans = Plan.query.filter_by(active=True).order_by(Plan.kind, Plan.price).all()
    branches = Branch.query.all()
    data = {
        "branches": {b.id: {"shifts": [{"id": s.id, "label": s.label, "title": s.title or ""} for s in
                                       Shift.query.filter_by(branch_id=b.id).order_by(Shift.start)],
                            "coaches": [{"id": c.id, "name": c.full_name, "spec": c.specialty or ""} for c in
                                        User.query.filter_by(role="coach", active=True, branch_id=b.id)]}
                     for b in branches},
        "plans": {p.id: {"kind": p.kind, "price": p.price, "name": p.name} for p in plans},
        "vouchers": [{"id": v.id, "title": v.title, "percent": v.percent}
                     for v in Voucher.query.filter_by(owner_id=me.id) if v.usable],
    }
    return render_template("member/shop.html", plans=plans, branches=branches, data=data, status=sub_status(me),
                           pre_plan=request.args.get("plan", type=int))


@bp.post("/shop/checkout")
@member_required
def checkout():
    f, me = request.form, current_user
    plan = db.session.get(Plan, int_or(f.get("plan_id"), 0))
    if not plan or not plan.active:
        flash("Vui lòng chọn gói dịch vụ.", "error")
        return redirect(url_for("member.shop"))
    branch_id, shift_id, coach_id = int_or(f.get("branch_id")), int_or(f.get("shift_id")), int_or(f.get("coach_id"))
    shift = db.session.get(Shift, shift_id) if shift_id else None
    coach = db.session.get(User, coach_id) if coach_id else None
    if not db.session.get(Branch, branch_id or 0) or (shift and shift.branch_id != branch_id):
        flash("Vui lòng chọn cơ sở và ca tập hợp lệ.", "error")
        return redirect(url_for("member.shop"))
    if plan.kind in ("coach", "combo") and (not coach or coach.role != "coach" or not coach.active):
        flash("Gói có Coach cần chọn Coach phụ trách.", "error")
        return redirect(url_for("member.shop"))
    voucher = db.session.get(Voucher, int_or(f.get("voucher_id"), 0)) if f.get("voucher_id") else None
    if voucher and (voucher.owner_id != me.id or not voucher.usable):
        flash("Voucher không còn hiệu lực.", "error")
        return redirect(url_for("member.shop"))
    amount = round(plan.price * (1 - (voucher.percent if voucher else 0) / 100) / 1000) * 1000
    Order.query.filter_by(user_id=me.id, status="pending").delete()
    o = Order(user_id=me.id, plan_id=plan.id, branch_id=branch_id, shift_id=shift.id if shift else None,
              coach_id=coach.id if coach else None, voucher_id=voucher.id if voucher else None, amount=amount,
              transfer_code=transfer_code(me, plan))
    db.session.add(o)
    db.session.commit()
    return redirect(url_for("member.order", oid=o.id))


@bp.route("/shop/order/<int:oid>")
@member_required
@owned_record(Order, "oid", owner_field="user_id", as_kwarg="o")
def order(oid, o):
    c = current_app.config
    qr_url = (f"https://img.vietqr.io/image/{c['BANK_ID']}-{c['BANK_ACCOUNT']}-compact2.png"
              f"?amount={o.amount}&addInfo={quote(o.transfer_code)}&accountName={quote(c['BANK_ACCOUNT_NAME'])}")
    return render_template("member/order.html", o=o, qr_url=qr_url, cfg=c)


@bp.post("/shop/order/<int:oid>/claim")
@member_required
@owned_record(Order, "oid", owner_field="user_id", as_kwarg="o")
def order_claim(oid, o):
    if o.status == "pending":
        o.status = "claimed"
        for mgr in User.query.filter_by(role="manager", active=True).all():
            notify(mgr.id, f"{current_user.full_name} báo đã chuyển khoản {o.transfer_code}", "/manager/rewards?tab=orders", "payments")
        db.session.commit()
        flash("Đã ghi nhận! Quản lý sẽ xác nhận và cộng ngày tập cho bạn sớm nhất.", "success")
    return redirect(url_for("member.membership"))
