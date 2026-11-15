"""Toàn bộ mô hình dữ liệu của VitaFlow."""
from datetime import date, datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

ROLES = ("manager", "coach", "member")

shift_coaches = db.Table(
    "shift_coaches",
    db.Column("shift_id", db.Integer, db.ForeignKey("shift.id"), primary_key=True),
    db.Column("coach_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
)


class Branch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(200))
    lat = db.Column(db.Float, default=10.80)
    lng = db.Column(db.Float, default=106.74)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="member", index=True)
    phone = db.Column(db.String(30))
    active = db.Column(db.Boolean, default=True, nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Coach
    title = db.Column(db.String(120))          # chức danh
    specialty = db.Column(db.String(160))      # chuyên môn

    # Member
    member_code = db.Column(db.String(20), unique=True)   # HV-102
    coach_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    goal = db.Column(db.String(200))
    streak = db.Column(db.Integer, default=0)
    best_streak = db.Column(db.Integer, default=0)
    last_checkin_day = db.Column(db.Date)
    period_mode = db.Column(db.Boolean, default=False)         # kỳ nghỉ sinh lý
    gym_expires = db.Column(db.Date)
    coach_expires = db.Column(db.Date)
    photo_visibility = db.Column(db.String(10), default="me_coach")  # me_coach | only_me
    avatar_url = db.Column(db.String(300))
    bonus_points = db.Column(db.Integer, default=0)

    branch = db.relationship("Branch")
    coach = db.relationship("User", remote_side=[id], backref="students", foreign_keys=[coach_id])

    @property
    def is_active(self):  # Flask-Login: tài khoản bị tắt thì không đăng nhập được
        return bool(self.active)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def first_name(self):
        return (self.full_name or "").strip().split(" ")[-1]

    @property
    def initials(self):
        parts = (self.full_name or "?").split()
        return (parts[0][0] + parts[-1][0]).upper() if len(parts) > 1 else parts[0][:2].upper()


class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"), nullable=False)
    name = db.Column(db.String(60), nullable=False)       # "Ca 3"
    title = db.Column(db.String(160))                     # "Tăng cơ giảm mỡ chuyên sâu"
    start = db.Column(db.Time, nullable=False)
    end = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, default=15, nullable=False)
    branch = db.relationship("Branch")
    coaches = db.relationship("User", secondary=shift_coaches, backref="shifts")

    @property
    def label(self):
        return f"{self.name}: {self.start:%H:%M} - {self.end:%H:%M}"


class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)  # G3T, C1T, CB3T
    name = db.Column(db.String(100), nullable=False)
    kind = db.Column(db.String(10), nullable=False)               # gym | coach | combo
    days = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, nullable=False)
    perks = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)


class Voucher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    granted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    title = db.Column(db.String(120), nullable=False)
    percent = db.Column(db.Integer, nullable=False)
    message = db.Column(db.String(300))
    expires_on = db.Column(db.Date)
    used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)
    owner = db.relationship("User", foreign_keys=[owner_id])
    granted_by = db.relationship("User", foreign_keys=[granted_by_id])

    @property
    def usable(self):
        return self.used_at is None and (self.expires_on is None or self.expires_on >= date.today())


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("plan.id"), nullable=False)
    branch_id = db.Column(db.Integer, db.ForeignKey("branch.id"))
    shift_id = db.Column(db.Integer, db.ForeignKey("shift.id"))
    coach_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    voucher_id = db.Column(db.Integer, db.ForeignKey("voucher.id"))
    amount = db.Column(db.Integer, nullable=False)
    transfer_code = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(12), default="pending", nullable=False)  # pending|claimed|confirmed|rejected
    created_at = db.Column(db.DateTime, default=datetime.now)
    confirmed_at = db.Column(db.DateTime)
    user = db.relationship("User", foreign_keys=[user_id])
    plan = db.relationship("Plan")
    branch = db.relationship("Branch")
    shift = db.relationship("Shift")
    coach = db.relationship("User", foreign_keys=[coach_id])
    voucher = db.relationship("Voucher")


class FreezeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    days = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(300))
    status = db.Column(db.String(10), default="pending")  # pending|approved|rejected
    created_at = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship("User")


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey("shift.id"), nullable=False)
    day = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(10), default="booked")  # booked|absent
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship("User")
    shift = db.relationship("Shift")


class Checkin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey("shift.id"))
    day = db.Column(db.Date, default=date.today, index=True)
    at = db.Column(db.DateTime, default=datetime.now)
    method = db.Column(db.String(10), default="qr")
    user = db.relationship("User")
    shift = db.relationship("Shift")


class BodyRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    day = db.Column(db.Date, default=date.today, nullable=False)
    weight_kg = db.Column(db.Float)
    height_cm = db.Column(db.Float)
    waist_cm = db.Column(db.Float)
    hip_cm = db.Column(db.Float)
    bust_cm = db.Column(db.Float)
    body_fat = db.Column(db.Float)
    note = db.Column(db.String(200))


class ProgressPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    kind = db.Column(db.String(10), nullable=False)  # before | after
    url = db.Column(db.String(300), nullable=False)
    taken_on = db.Column(db.Date, default=date.today)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    kind = db.Column(db.String(10), default="general")  # checkin|meal|general|invite
    body = db.Column(db.Text)
    image_url = db.Column(db.String(300))
    shift_id = db.Column(db.Integer, db.ForeignKey("shift.id"))
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
    user = db.relationship("User")
    shift = db.relationship("Shift")
    likes = db.relationship("PostLike", backref="post", cascade="all, delete-orphan")
    comments = db.relationship("PostComment", backref="post", cascade="all, delete-orphan",
                               order_by="PostComment.created_at")


class PostLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("post_id", "user_id"),)


class PostComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship("User")


class WaterLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    day = db.Column(db.Date, default=date.today, nullable=False)
    ml = db.Column(db.Integer, default=0, nullable=False)
    __table_args__ = (db.UniqueConstraint("user_id", "day"),)


class MealLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    day = db.Column(db.Date, default=date.today, nullable=False)
    meal_key = db.Column(db.String(10), nullable=False)  # bua_sang|bua_trua|bua_toi
    followed_ai = db.Column(db.Boolean, default=False)
    photo_url = db.Column(db.String(300))
    score = db.Column(db.Integer)                         # coach chấm 1-10
    coach_note = db.Column(db.String(300))
    __table_args__ = (db.UniqueConstraint("user_id", "day", "meal_key"),)


class HealthProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    age = db.Column(db.Integer)
    height_cm = db.Column(db.Float)
    weight_kg = db.Column(db.Float)
    activity_level = db.Column(db.String(20), default="vua")
    fitness_goal = db.Column(db.String(30), default="giam_can")
    notes = db.Column(db.String(1000), default="")
    bmr = db.Column(db.Float)
    tdee = db.Column(db.Float)
    target_calories = db.Column(db.Float)
    protein_g = db.Column(db.Integer)
    carb_g = db.Column(db.Integer)
    fat_g = db.Column(db.Integer)
    user = db.relationship("User", backref=db.backref("health_profile", uselist=False))


class MenuHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    day = db.Column(db.Date, default=date.today, index=True)
    title = db.Column(db.String(150))
    total_calo = db.Column(db.Integer)
    menu_data = db.Column(db.Text)
    source = db.Column(db.String(12), default="ai")  # ai | offline
    workout = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.now)
    user = db.relationship("User")


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)   # chat 1-1
    shift_id = db.Column(db.Integer, db.ForeignKey("shift.id"), index=True)      # nhóm chat theo ca
    body = db.Column(db.String(2000))
    image_url = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
    read_at = db.Column(db.DateTime)
    sender = db.relationship("User", foreign_keys=[sender_id])


class Escalation(db.Model):
    """Coach chuyển tiếp một vấn đề của học viên lên Quản lý."""
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(10), default="open")  # open | resolved
    created_at = db.Column(db.DateTime, default=datetime.now)
    coach = db.relationship("User", foreign_keys=[coach_id])
    member = db.relationship("User", foreign_keys=[member_id])


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    text = db.Column(db.String(300), nullable=False)
    url = db.Column(db.String(200))
    icon = db.Column(db.String(40), default="notifications")
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
