"""Cổng Quản lý (Manager Portal) - tông Emerald & Champagne Gold."""
import json
from datetime import date, datetime, time, timedelta

from flask_login import current_user
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, request, session, url_for
from sqlalchemy import func

from extensions import db
from models import (Report, Post, PostComment, Booking, Branch, Checkin, Escalation, FreezeRequest, MealLog, Message, Order, Shift, User,
                    Voucher)
from services import (RANK_ORDER, body_summary, checked_in_ids, contacts_for, current_shift, delete_user,
                      expiring_members, extend_subscription, grant_voucher, groups_for, notify, rank_info,
                      ranked_members, shift_state, sub_status, students_of, today_menu)
from utils import render_template, float_or, int_or, manager_required
from security import student_access, shift_access, owned_record, escalation_access

bp = Blueprint("manager", __name__, url_prefix="/manager")


def _branch_id():
    """Bộ lọc cơ sở lưu trong session (0 = tất cả)."""
    if "branch" in request.args:
        session["branch"] = request.args.get("branch", type=int) or 0
    return session.get("branch") or None


def _members(branch_id=None, q=""):
    qs = User.query.filter_by(role="member", active=True)
    if branch_id:
        qs = qs.filter_by(branch_id=branch_id)
    if q:
        like = f"%{q}%"
        qs = qs.filter(User.full_name.ilike(like) | User.member_code.ilike(like) | User.email.ilike(like))
    return qs.order_by(User.full_name).all()


# ------------------------------------------------------------ Tổng quan
@bp.route("/")
@manager_required
def dashboard():
    bid = _branch_id()
    branch = db.session.get(Branch, bid) if bid else Branch.query.first()
    shift = current_shift(bid)
    today = date.today()
    members = _members(bid)
    present = []
    if shift:
        ids = checked_in_ids(shift.id)
        present = [m for m in members if m.id in ids]
    coaches_q = User.query.filter_by(role="coach", active=True)
    if bid:
        coaches_q = coaches_q.filter_by(branch_id=bid)
    coaches = coaches_q.order_by(User.full_name).all()
    on_duty = list(shift.coaches) if shift else []
    shifts = Shift.query.filter_by(branch_id=bid).order_by(Shift.start).all() if bid else \
        Shift.query.filter_by(branch_id=branch.id).order_by(Shift.start).all()
    shift_rows = [{"shift": s, "state": shift_state(s), "count": len(checked_in_ids(s.id))} for s in shifts]
    kpi = {
        "members": len(members), "coaches": len(coaches),
        "expiring": len(expiring_members(members)),
        "escalations": Escalation.query.filter_by(status="open").count(),
        "orders": Order.query.filter(Order.status.in_(["claimed", "pending"])).count(),
        "reports": Report.query.filter_by(status="open").count(),
        "checkins_today": Checkin.query.filter_by(day=today).count(),
    }
    return render_template("manager/dashboard.html", branch=branch, shift=shift, present=present, coaches=coaches,
                           on_duty=on_duty, shift_rows=shift_rows, kpi=kpi, sel_branch=bid)


# ------------------------------------------------------------ Nhân sự & Cơ sở
@bp.route("/staff")
@manager_required
def staff():
    bid, q = _branch_id(), request.args.get("q", "").strip()
    cq = User.query.filter_by(role="coach")
    if bid:
        cq = cq.filter_by(branch_id=bid)
    if q:
        cq = cq.filter(User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    coaches = cq.order_by(User.full_name).all()
    all_members = User.query.filter_by(role="member", active=True).order_by(User.full_name).all()
    return render_template("manager/staff.html", coaches=coaches, all_members=all_members, q=q, sel_branch=bid)


def _fill_coach(u, f, creating=False):
    u.full_name = f.get("full_name", "").strip()
    u.phone = f.get("phone", "").strip()
    u.title = f.get("title", "").strip()
    u.specialty = f.get("specialty", "").strip()
    u.branch_id = int_or(f.get("branch_id"))
    if f.get("password"):
        u.set_password(f["password"])


@bp.post("/staff/add")
@manager_required
def staff_add():
    f = request.form
    email = f.get("email", "").strip().lower()
    if not f.get("full_name", "").strip() or "@" not in email or len(f.get("password", "")) < 6:
        flash("Cần họ tên, email hợp lệ và mật khẩu từ 6 ký tự.", "error")
    elif User.query.filter_by(email=email).first():
        flash("Email đã tồn tại trong hệ thống.", "error")
    else:
        u = User(email=email, role="coach", full_name="")
        _fill_coach(u, f, True)
        db.session.add(u)
        db.session.commit()
        flash(f"Đã thêm Coach {u.full_name}.", "success")
    return redirect(url_for("manager.staff"))


@bp.post("/staff/<int:uid>/edit")
@manager_required
def staff_edit(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.role != "coach":
        abort(403)
    email = request.form.get("email", "").strip().lower()
    if email and email != u.email:
        if User.query.filter(User.email == email, User.id != u.id).first():
            flash("Email đã tồn tại.", "error")
            return redirect(url_for("manager.staff"))
        u.email = email
    _fill_coach(u, request.form)
    db.session.commit()
    flash("Đã cập nhật thông tin Coach.", "success")
    return redirect(url_for("manager.staff"))


@bp.post("/staff/<int:uid>/toggle")
@manager_required
def staff_toggle(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.role != "coach":
        abort(403)
    u.active = not u.active
    db.session.commit()
    flash(f"Coach {u.full_name} đã được {'bật' if u.active else 'tắt'}.", "success")
    return redirect(url_for("manager.staff"))


@bp.post("/staff/<int:uid>/delete")
@manager_required
def staff_delete(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.role != "coach":
        abort(403)
    name = u.full_name
    delete_user(u)
    flash(f"Đã xoá Coach {name}. Học viên của Coach này đang chờ được gán lại.", "success")
    return redirect(url_for("manager.staff"))


@bp.post("/staff/<int:uid>/assign")
@manager_required
def staff_assign(uid):
    coach = db.session.get(User, uid) or abort(404)
    if coach.role != "coach":
        abort(403)
    chosen = {int(x) for x in request.form.getlist("member_ids") if x.isdigit()}
    for m in User.query.filter_by(role="member").all():
        if m.id in chosen:
            m.coach_id = coach.id
        elif m.coach_id == coach.id:
            m.coach_id = None
    db.session.commit()
    flash(f"Đã cập nhật danh sách học viên của Coach {coach.full_name}.", "success")
    return redirect(url_for("manager.staff"))


# ------------------------------------------------------------ Tiến độ & Hồ sơ Body
@bp.route("/members")
@manager_required
def members():
    bid, q = _branch_id(), request.args.get("q", "").strip()
    rank_f, coach_f = request.args.get("rank", ""), request.args.get("coach", type=int)
    ms = _members(bid, q)
    if coach_f:
        ms = [m for m in ms if m.coach_id == coach_f]
    ranked = ranked_members(ms)
    if rank_f in RANK_ORDER:
        ranked = [r for r in ranked if r["name"] == rank_f]
    groups = {r: [x for x in ranked if x["name"] == r] for r in RANK_ORDER}
    coaches = User.query.filter_by(role="coach", active=True).all()
    return render_template("manager/members.html", groups=groups, coaches=coaches, q=q, rank_f=rank_f,
                           coach_f=coach_f, sel_branch=bid, total=len(ranked))


@bp.route("/members/<int:uid>/card")
@manager_required
@student_access("uid", as_kwarg="m")
def member_card(uid, m):
    return render_template("partials/member_card.html", m=m, **member_card_ctx(m, viewer="manager"))


def member_card_ctx(m, viewer):
    from models import ProgressPhoto
    s = body_summary(m.id)
    show = m.photo_visibility != "only_me" or viewer == "self"
    photos = {}
    if show:
        for kind in ("before", "after"):
            photos[kind] = (ProgressPhoto.query.filter_by(user_id=m.id, kind=kind)
                            .order_by(ProgressPhoto.id.desc()).first())
    return {"summary": s, "rank": rank_info(m), "status": sub_status(m), "photos": photos, "photos_hidden": not show}


# ------------------------------------------------------------ Ca tập & Giám sát điểm danh
@bp.route("/shifts")
@manager_required
def shifts():
    bid = _branch_id() or Branch.query.first().id
    session["branch"] = bid
    shift_list = Shift.query.filter_by(branch_id=bid).order_by(Shift.start).all()
    sel = db.session.get(Shift, request.args.get("shift", type=int) or 0) or current_shift(bid) or \
        (shift_list[0] if shift_list else None)
    monitor = []
    if sel:
        ck = checked_in_ids(sel.id)
        booked = {b.user_id: b for b in Booking.query.filter_by(shift_id=sel.id, day=date.today()).all()}
        for c in sel.coaches:
            rows = []
            for st in students_of(c):
                rows.append({"user": st, "checkin": ck.get(st.id), "booking": booked.get(st.id), "status": sub_status(st)})
            monitor.append({"coach": c, "rows": rows, "present": sum(1 for r in rows if r["checkin"])})
    coaches = User.query.filter_by(role="coach", active=True).all()
    return render_template("manager/shifts.html", shift_list=shift_list, sel=sel, monitor=monitor, coaches=coaches,
                           states={s.id: shift_state(s) for s in shift_list}, sel_branch=bid)


def _parse_time(v, default):
    try:
        h, m = v.split(":")
        return time(int(h), int(m))
    except (ValueError, AttributeError):
        return default


@bp.post("/shifts/save")
@manager_required
def shift_save():
    f = request.form
    sid = int_or(f.get("id"))
    s = db.session.get(Shift, sid) if sid else Shift(branch_id=int_or(f.get("branch_id")) or session.get("branch"))
    s.name = f.get("name", "").strip() or "Ca mới"
    s.title = f.get("title", "").strip()
    s.start, s.end = _parse_time(f.get("start"), time(17)), _parse_time(f.get("end"), time(18))
    s.capacity = max(1, int_or(f.get("capacity"), 15))
    if s.end <= s.start:
        flash("Giờ kết thúc phải sau giờ bắt đầu.", "error")
        return redirect(url_for("manager.shifts"))
    ids = {int(x) for x in f.getlist("coach_ids") if x.isdigit()}
    s.coaches = User.query.filter(User.id.in_(ids), User.role == "coach").all() if ids else []
    db.session.add(s)
    db.session.commit()
    flash("Đã lưu ca tập.", "success")
    return redirect(url_for("manager.shifts", shift=s.id))


@bp.post("/shifts/<int:sid>/delete")
@manager_required
@shift_access("sid", as_kwarg="s")
def shift_delete(sid, s):
    s = db.session.get(Shift, sid) or abort(404)
    if Booking.query.filter_by(shift_id=s.id).filter(Booking.day >= date.today()).count():
        flash("Ca này còn lịch đặt chỗ sắp tới, không thể xoá.", "error")
    else:
        Message.query.filter_by(shift_id=s.id).delete()
        Checkin.query.filter_by(shift_id=s.id).update({"shift_id": None})
        Booking.query.filter_by(shift_id=s.id).delete()
        s.coaches = []
        db.session.delete(s)
        db.session.commit()
        flash("Đã xoá ca tập.", "success")
    return redirect(url_for("manager.shifts"))


# ------------------------------------------------------------ AI Diet & Messenger
@bp.route("/nutrition")
@manager_required
def nutrition():
    from models import Shift as S
    peer = db.session.get(User, request.args.get("peer", type=int) or 0)
    group = db.session.get(S, request.args.get("shift", type=int) or 0)
    side = None
    if peer and peer.role == "member":
        menu_row = today_menu(peer.id)
        side = {"menu": menu_row, "menu_data": json.loads(menu_row.menu_data) if menu_row else None,
                "meals": {m.meal_key: m for m in MealLog.query.filter_by(user_id=peer.id, day=date.today()).all()},
                "status": sub_status(peer), "rank": rank_info(peer), "body": body_summary(peer.id)}
    esc = Escalation.query.order_by(Escalation.status.desc(), Escalation.id.desc()).limit(10).all()
    return render_template("manager/nutrition.html", contacts=contacts_for(current_user), groups=groups_for(current_user),
                           peer=peer, group=group, side=side, escalations=esc)



@bp.post("/escalations/<int:eid>/resolve")
@manager_required
@escalation_access("eid", as_kwarg="esc")
def escalation_resolve(eid, esc):
    e = db.session.get(Escalation, eid) or abort(404)
    e.status = "resolved"
    notify(e.coach_id, f"Quản lý đã xử lý vấn đề của {e.member.full_name}", "/coach/nutrition", "task_alt")
    db.session.commit()
    flash("Đã đánh dấu xử lý xong.", "success")
    return redirect(request.referrer or url_for("manager.nutrition"))


# ------------------------------------------------------------ Phân hạng, gia hạn, quà tặng
@bp.route("/rewards")
@manager_required
def rewards():
    tab = request.args.get("tab", "orders")
    bid = _branch_id()
    ms = _members(bid)
    ranked = ranked_members(ms)
    counts = {r: sum(1 for x in ranked if x["name"] == r) for r in RANK_ORDER}
    orders = Order.query.order_by(Order.status.desc(), Order.id.desc()).limit(40).all()
    freezes = FreezeRequest.query.order_by(FreezeRequest.status.desc(), FreezeRequest.id.desc()).limit(30).all()
    return render_template("manager/rewards.html", tab=tab, counts=counts, orders=orders, freezes=freezes,
                           expiring=expiring_members(ms), members=ms, ranked=ranked, sel_branch=bid)


@bp.post("/rewards/order/<int:oid>/<action>")
@manager_required
@owned_record(Order, "oid", owner_field="user_id", as_kwarg="o")
def order_action(oid, action, o):
    o = db.session.get(Order, oid) or abort(404)
    if o.status in ("confirmed", "rejected") or action not in ("confirm", "reject"):
        flash("Đơn này đã được xử lý.", "warning")
    elif action == "confirm":
        extend_subscription(o.user, o.plan)
        if o.plan.kind in ("coach", "combo") and o.coach_id:
            o.user.coach_id = o.coach_id
        if o.branch_id:
            o.user.branch_id = o.branch_id
        if o.voucher:
            o.voucher.used_at = datetime.now()
        o.status, o.confirmed_at = "confirmed", datetime.now()
        notify(o.user_id, f"Đã xác nhận thanh toán {o.plan.name}. Ngày tập đã được cộng dồn!", "/app/membership", "verified")
        db.session.commit()
        flash(f"Đã xác nhận đơn {o.transfer_code}.", "success")
    else:
        o.status = "rejected"
        notify(o.user_id, f"Đơn {o.transfer_code} chưa được xác nhận. Vui lòng liên hệ Quản lý.", "/app/membership", "error")
        db.session.commit()
        flash("Đã từ chối đơn.", "success")
    return redirect(url_for("manager.rewards", tab="orders"))


@bp.post("/rewards/freeze/<int:fid>/<action>")
@manager_required
@owned_record(FreezeRequest, "fid", owner_field="user_id", as_kwarg="fr")
def freeze_action(fid, action, fr):
    r = db.session.get(FreezeRequest, fid) or abort(404)
    if r.status != "pending" or action not in ("approve", "reject"):
        flash("Yêu cầu này đã được xử lý.", "warning")
    elif action == "approve":
        for field in ("gym_expires", "coach_expires"):
            cur = getattr(r.user, field)
            if cur:
                setattr(r.user, field, cur + timedelta(days=r.days))
        r.status = "approved"
        notify(r.user_id, f"Yêu cầu bảo lưu {r.days} ngày đã được duyệt.", "/app/membership", "pause_circle")
        db.session.commit()
        flash("Đã duyệt bảo lưu và cộng bù ngày tập.", "success")
    else:
        r.status = "rejected"
        notify(r.user_id, "Yêu cầu bảo lưu chưa được duyệt.", "/app/membership", "error")
        db.session.commit()
        flash("Đã từ chối yêu cầu.", "success")
    return redirect(url_for("manager.rewards", tab="freeze"))


@bp.post("/rewards/gift")
@manager_required
@student_access("member_id", sources=("form",), as_kwarg="m")
def gift(m):
    f = request.form
    percent = int_or(f.get("percent"), 0)
    if not m or m.role != "member" or not 1 <= percent <= 50:
        flash("Chọn hội viên và mức giảm từ 1% đến 50%.", "error")
    else:
        grant_voucher(m, current_user, f.get("title", "").strip() or f"Quà từ {current_app.config['COMPANY_NAME']}", percent,
                      f.get("message", ""), int_or(f.get("days"), 30))
        db.session.commit()
        flash(f"Đã gửi voucher -{percent}% cho {m.full_name}.", "success")
    return redirect(request.referrer or url_for("manager.rewards", tab="gift"))


# ------------------------------------------------------------ Kiểm duyệt nội dung (báo cáo vi phạm)
@bp.route("/reports")
@manager_required
def reports():
    status = request.args.get("status", "open")
    rows = []
    for r in Report.query.filter_by(status=status).order_by(Report.id.desc()).limit(60):
        rows.append({"r": r, "post": db.session.get(Post, r.post_id) if r.post_id else None,
                     "comment": db.session.get(PostComment, r.comment_id) if r.comment_id else None,
                     "target": db.session.get(User, r.target_user_id) if r.target_user_id else None,
                     "reporter": db.session.get(User, r.reporter_id)})
    return render_template("manager/reports.html", rows=rows, status=status,
                           open_count=Report.query.filter_by(status="open").count())


@bp.post("/reports/<int:rid>/<action>")
@manager_required
def report_action(rid, action):
    r = db.session.get(Report, rid) or abort(404)
    if action not in ("remove", "dismiss", "suspend") or r.status != "open":
        flash("Báo cáo này đã được xử lý.", "warning")
        return redirect(url_for("manager.reports"))
    if action == "dismiss":
        r.status = "dismissed"
    else:
        post = db.session.get(Post, r.post_id) if r.post_id else None
        comment = db.session.get(PostComment, r.comment_id) if r.comment_id else None
        if post:
            Report.query.filter(Report.post_id == post.id).update({"status": "removed"})
            db.session.delete(post)
        if comment:
            Report.query.filter(Report.comment_id == comment.id).update({"status": "removed"})
            db.session.delete(comment)
        r.status = "removed"
        target = db.session.get(User, r.target_user_id) if r.target_user_id else None
        if target:
            notify(target.id, "Nội dung của bạn đã bị gỡ do vi phạm Điều khoản sử dụng.", None, "gavel")
            if action == "suspend" and target.role == "member":
                target.active = False
    db.session.commit()
    flash({"remove": "Đã gỡ nội dung vi phạm.", "dismiss": "Đã bỏ qua báo cáo.", "suspend": "Đã gỡ nội dung và khoá tài khoản."}[action], "success")
    return redirect(url_for("manager.reports"))
