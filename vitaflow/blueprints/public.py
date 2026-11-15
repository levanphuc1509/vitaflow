from flask import Blueprint, redirect, request, session

from utils import render_template, safe_next

from models import Branch, Plan, User
from services import body_summary

bp = Blueprint("public", __name__)


@bp.route("/")
def landing():
    plans = Plan.query.filter_by(active=True).order_by(Plan.price).all()
    branches = Branch.query.all()
    stories = []
    for m in User.query.filter_by(role="member", active=True).limit(3).all():
        s = body_summary(m.id)
        stories.append({"user": m, "d_weight": s["d_weight"], "d_waist": s["d_waist"]})
    return render_template("public/landing.html", plans=plans, branches=branches, stories=stories)


@bp.route("/view/<mode>")
def set_view(mode):
    """Chuyển đổi thủ công giữa giao diện PC và điện thoại."""
    if mode in ("mobile", "desktop"):
        session["view"] = mode
    return redirect(safe_next(request.args.get("next"), "/"))
