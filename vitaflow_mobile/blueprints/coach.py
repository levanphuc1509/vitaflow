"""Cổng Coach (Huấn luyện viên) - tông Coral Orange. Chỉ thấy học viên được phân công."""
import json
from datetime import date, datetime

from flask import Blueprint, abort, flash, jsonify, redirect, request, url_for
from flask_login import current_user

from blueprints.manager import member_card_ctx
from extensions import db
from models import Checkin, MealLog, Shift, User, Voucher
from services import (checked_in_ids, contacts_for, current_shift, expiring_members, grant_voucher, groups_for,
                      notify, parse_member_token, rank_info, ranked_members, register_checkin, shift_state,
                      shift_token, students_of, sub_status, today_menu, qr_svg, body_summary, unread_count)
from utils import render_template, coach_required, int_or
from security import ensure_member_access, shift_access, student_access

bp = Blueprint("coach", __name__, url_prefix="/coach")


def _my_shifts():
    return sorted(current_user.shifts, key=lambda s: (s.branch_id, s.start))


def _student_or_404(uid):
    m = db.session.get(User, uid) or abort(404)
    if m.role != "member" or m.coach_id != current_user.id:
        abort(403)
    return m


@bp.route("/")
@coach_required
def dashboard():
    students = students_of(current_user)
    shifts = _my_shifts()
    live = next((s for s in shifts if shift_state(s) == "live"), None)
    upcoming = next((s for s in shifts if shift_state(s) == "upcoming"), None)
    focus = live or upcoming or (shifts[-1] if shifts else None)
    ck = checked_in_ids(focus.id) if focus else {}
    today_ck = {c.user_id for c in Checkin.query.filter_by(day=date.today()).all()}
    rows = [{"user": s, "rank": rank_info(s), "status": sub_status(s), "in": s.id in ck, "today": s.id in today_ck}
            for s in students]
    kpi = {"students": len(students), "present": sum(1 for r in rows if r["today"]),
           "expiring": len(expiring_members(students)), "unread": unread_count(current_user)}
    return render_template("coach/dashboard.html", rows=rows, focus=focus, focus_state=shift_state(focus) if focus else None,
                           shifts=shifts, kpi=kpi, states={s.id: shift_state(s) for s in shifts})


@bp.route("/progress")
@coach_required
def progress():
    ranked = ranked_members(students_of(current_user))
    for r in ranked:
        r["body"] = body_summary(r["user"].id)
        r["status"] = sub_status(r["user"])
    return render_template("coach/progress.html", ranked=ranked)


@bp.route("/students/<int:uid>/card")
@coach_required
def student_card(uid):
    m = _student_or_404(uid)
    return render_template("partials/member_card.html", m=m, **member_card_ctx(m, viewer="coach"))


# ---------------------------------------------------------- Ca tập & Quét QR
@bp.route("/checkin")
@coach_required
def checkin():
    shifts = _my_shifts()
    sel = next((s for s in shifts if s.id == request.args.get("shift", type=int)), None) or \
        next((s for s in shifts if shift_state(s) == "live"), None) or (shifts[0] if shifts else None)
    done, alerts, stats = [], [], {"in": 0, "expected": 0}
    if sel:
        ck = checked_in_ids(sel.id)
        done = sorted(ck.values(), key=lambda c: c.at, reverse=True)
        mine = students_of(current_user)
        alerts = expiring_members(mine)
        stats = {"in": len(done), "expected": sel.capacity, "mine_in": sum(1 for m in mine if m.id in ck)}
    return render_template("coach/checkin.html", shifts=shifts, sel=sel, done=done, alerts=alerts, stats=stats,
                           states={s.id: shift_state(s) for s in shifts})


def _shift_url(shift):
    return url_for("member.shift_checkin", token=shift_token(shift), _external=True)


@bp.get("/checkin/qr/<int:sid>")
@coach_required
@shift_access("sid", as_kwarg="s")
def shift_qr(sid, s):
    url = _shift_url(s)
    return jsonify(ok=True, svg=qr_svg(url, scale=8), url=url, ttl=150)


@bp.post("/checkin/scan")
@coach_required
def scan():
    s = db.session.get(Shift, request.form.get("shift_id", type=int) or 0) or abort(404)
    if current_user not in s.coaches:
        abort(403)
    m = parse_member_token(request.form.get("code"))
    if not m or m.role != "member":
        return jsonify(ok=False, message="Mã không hợp lệ hoặc không tìm thấy hội viên."), 404
    ok, msg, ck = register_checkin(m, s.id, method="scan")
    st = sub_status(m)
    return jsonify(ok=ok, message=msg, name=m.full_name, code=m.member_code,
                   time=ck.at.strftime("%H:%M:%S") if ck else "", state=st["gym"]["state"],
                   days=st["gym"]["days"])


@bp.post("/checkin/unlock")
@coach_required
def kiosk_unlock():
    """Thoát Chế độ chỉ hiện QR: yêu cầu nhập lại mật khẩu của Coach."""
    return jsonify(ok=current_user.check_password(request.form.get("password", "")))


# ---------------------------------------------------------- Dinh dưỡng AI & Chat
@bp.route("/nutrition")
@coach_required
def nutrition():
    peer = db.session.get(User, request.args.get("peer", type=int) or 0)
    group = db.session.get(Shift, request.args.get("shift", type=int) or 0)
    side = None
    if peer and peer.role == "member":
        _student_or_404(peer.id)
        if group and not can_group(current_user, group):
            abort(403)
        menu_row = today_menu(peer.id)
        side = {"menu": menu_row, "menu_data": json.loads(menu_row.menu_data) if menu_row else None,
                "meals": {m.meal_key: m for m in MealLog.query.filter_by(user_id=peer.id, day=date.today()).all()},
                "status": sub_status(peer), "rank": rank_info(peer), "body": body_summary(peer.id)}
    return render_template("coach/nutrition.html", contacts=contacts_for(current_user), groups=groups_for(current_user),
                           peer=peer, group=group, side=side)


@bp.post("/meal/<int:uid>/<meal_key>/score")
@coach_required
def meal_score(uid, meal_key):
    m = _student_or_404(uid)
    if meal_key not in ("bua_sang", "bua_trua", "bua_toi"):
        abort(404)
    score = int_or(request.form.get("score"), 0)
    if not 1 <= score <= 10:
        flash("Điểm mâm cơm từ 1 đến 10.", "error")
    else:
        log = MealLog.query.filter_by(user_id=m.id, day=date.today(), meal_key=meal_key).first()
        if not log:
            log = MealLog(user_id=m.id, day=date.today(), meal_key=meal_key)
            db.session.add(log)
        log.score, log.coach_note = score, request.form.get("note", "").strip()[:300]
        notify(m.id, f"Coach {current_user.first_name} chấm mâm cơm của bạn: {score}/10", "/app/nutrition", "restaurant")
        db.session.commit()
        flash(f"Đã chấm {score}/10 cho {m.full_name}.", "success")
    return redirect(url_for("coach.nutrition", peer=m.id))


# ---------------------------------------------------------- Phân hạng & Gifting
@bp.route("/rewards")
@coach_required
def rewards():
    ranked = ranked_members(students_of(current_user))
    for r in ranked:
        r["suggest"] = r["name"] in ("Diamond", "Gold") or (r["user"].streak or 0) >= 10
        r["status"] = sub_status(r["user"])
    sent = (Voucher.query.filter_by(granted_by_id=current_user.id).order_by(Voucher.id.desc()).limit(10).all())
    return render_template("coach/rewards.html", ranked=ranked, sent=sent)


@bp.post("/rewards/gift")
@coach_required
def gift():
    f = request.form
    m = _student_or_404(int_or(f.get("member_id"), 0))
    percent = int_or(f.get("percent"), 0)
    if not 1 <= percent <= 20:
        flash("Coach có thể tặng voucher từ 1% đến 20%.", "error")
    else:
        grant_voucher(m, current_user, f.get("title", "").strip() or "Thưởng chuyên cần", percent,
                      f.get("message", ""), int_or(f.get("days"), 30))
        db.session.commit()
        flash(f"Đã gửi voucher -{percent}% cho {m.full_name}.", "success")
    return redirect(url_for("coach.rewards"))
