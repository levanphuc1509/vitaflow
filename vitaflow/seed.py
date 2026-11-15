"""Dữ liệu demo cho VITAFLOW. Chạy `python seed.py --reset` để tạo lại từ đầu."""
import json
import random
import sys
from datetime import date, datetime, time, timedelta

from extensions import db
from models import (Booking, BodyRecord, Branch, Checkin, Escalation, FreezeRequest, HealthProfile, MealLog,
                    Message, MenuHistory, Notification, Order, Plan, Post, PostComment, PostLike, Shift, User,
                    Voucher, WaterLog)

DEMO_ACCOUNTS = [
    ("Quản lý", "manager@vitaflow.vn", "manager123"),
    ("Coach", "mai.anh@vitaflow.vn", "coach123"),
    ("Thành viên", "mai.phuong@gmail.com", "member123"),
]

BRANCHES = [("Thảo Điền Premier", "Quận 2, TP. Hồ Chí Minh", 10.8031, 106.7403),
            ("Landmark Plus", "Bình Thạnh, TP. Hồ Chí Minh", 10.7950, 106.7218),
            ("Phú Mỹ Hưng", "Quận 7, TP. Hồ Chí Minh", 10.7290, 106.7190)]

SHIFTS = [("Ca 1", "Khởi động sáng · Pilates", time(5), time(6)),
          ("Ca 2", "Yoga & giãn cơ", time(6), time(7)),
          ("Ca 3", "Tăng cơ giảm mỡ chuyên sâu (Glutes & Core)", time(17), time(18)),
          ("Ca 4", "Cardio nhẹ & Siết eo S-Line", time(18), time(19))]

PLANS = [("G1T", "Gym 1 tháng", "gym", 30, 700_000, "Tập tự do tại mọi cơ sở"),
         ("G3T", "Gym 3 tháng", "gym", 90, 1_800_000, "Tiết kiệm 14% · khoá tủ riêng"),
         ("G6T", "Gym 6 tháng", "gym", 180, 3_200_000, "Tiết kiệm 24% · 1 buổi InBody/tháng"),
         ("C1T", "Coach 1:1 – 1 tháng", "coach", 30, 2_400_000, "Coach riêng + thực đơn AI"),
         ("C3T", "Coach 1:1 – 3 tháng", "coach", 90, 6_300_000, "Lộ trình độ body 12 tuần"),
         ("CB3T", "Combo Gym + Coach 3 tháng", "combo", 90, 7_200_000, "Gói phổ biến nhất"),
         ("CB6T", "Combo Gym + Coach 6 tháng", "combo", 180, 12_500_000, "Hạng Diamond ưu tiên")]

COACHES = [("Mai Anh", "mai.anh@vitaflow.vn", "Trưởng bộ phận Dinh dưỡng", "Siết eo & S-Line"),
           ("Yến Vy", "yen.vy@vitaflow.vn", "Huấn luyện viên Pilates", "Pilates Reformer"),
           ("Thùy Dương", "thuy.duong@vitaflow.vn", "Huấn luyện viên Yoga", "Yoga phục hồi")]

MEMBERS = [("Trần Mai Phương", "mai.phuong@gmail.com", 54.2, 160), ("Hoàng Lan Chi", "lan.chi@gmail.com", 57.4, 163),
           ("Nguyễn Minh Thư", "minh.thu@gmail.com", 52.0, 158), ("Lê Ngọc Diệp", "ngoc.diep@gmail.com", 61.5, 165),
           ("Phạm Thanh Trúc", "thanh.truc@gmail.com", 58.0, 162), ("Vũ Quỳnh Nga", "quynh.nga@gmail.com", 63.2, 166),
           ("Nguyễn Thị Thảo", "thi.thao@gmail.com", 55.0, 159), ("Hoàng Thùy Linh", "thuy.linh@gmail.com", 50.8, 157),
           ("Đỗ Khánh Vy", "khanh.vy@gmail.com", 59.9, 164), ("Bùi Diễm My", "diem.my@gmail.com", 56.3, 161),
           ("Trương Bảo Ngọc", "bao.ngoc@gmail.com", 60.4, 167), ("Lý Yến Nhi", "yen.nhi@gmail.com", 53.6, 158)]


def reset_db():
    db.drop_all()
    db.create_all()


def seed_demo():
    if User.query.first():
        return
    rnd = random.Random(2024)
    today = date.today()

    branches = [Branch(name=n, address=a, lat=la, lng=lo) for n, a, la, lo in BRANCHES]
    db.session.add_all(branches)
    db.session.flush()
    for p in PLANS:
        db.session.add(Plan(code=p[0], name=p[1], kind=p[2], days=p[3], price=p[4], perks=p[5]))

    shifts = []
    for b in branches:
        for name, title, s, e in SHIFTS:
            sh = Shift(branch_id=b.id, name=name, title=title, start=s, end=e, capacity=15)
            db.session.add(sh)
            shifts.append(sh)
    db.session.flush()

    mgr = User(full_name="Nguyễn Lan Hương", email="manager@vitaflow.vn", role="manager",
               phone="0900000001", title="Quản lý chuỗi", branch_id=branches[0].id)
    mgr.set_password("manager123")
    db.session.add(mgr)

    coaches = []
    for name, email, title, spec in COACHES:
        c = User(full_name=name, email=email, role="coach", title=title, specialty=spec,
                 phone="09" + str(rnd.randint(10000000, 99999999)), branch_id=branches[0].id)
        c.set_password("coach123")
        db.session.add(c)
        coaches.append(c)
    db.session.flush()

    b0 = [s for s in shifts if s.branch_id == branches[0].id]
    b0[0].coaches.append(coaches[0]); b0[1].coaches.append(coaches[1]); b0[3].coaches.append(coaches[2])
    b0[2].coaches.extend(coaches)

    members = []
    for i, (name, email, weight, height) in enumerate(MEMBERS):
        coach = coaches[i % 3]
        m = User(full_name=name, email=email, role="member", member_code=f"HV-{102 + i}",
                 phone="09" + str(rnd.randint(10000000, 99999999)), branch_id=branches[0].id, coach_id=coach.id,
                 goal=rnd.choice(["Siết eo S-Line", "Giảm mỡ bụng", "Săn chắc đùi", "Tăng cơ mông"]))
        m.set_password("member123")
        m.gym_expires = today + timedelta(days=[78, 45, 21, -3, 2, 60, 3, 120, 33, 15, 90, 9][i])
        m.coach_expires = today + timedelta(days=[78, 45, 21, -3, 2, 60, 3, 0, 33, 15, 90, 9][i]) if i != 7 else None
        m.streak = [12, 9, 6, 0, 3, 14, 4, 21, 7, 5, 11, 2][i]
        m.best_streak = m.streak + rnd.randint(0, 6)
        m.bonus_points = rnd.choice([0, 20, 60, 120, 200])
        m.photo_visibility = "me_coach"
        db.session.add(m)
        members.append(m)
    db.session.flush()

    # Số đo 8 tuần
    for i, m in enumerate(members):
        w0, h = MEMBERS[i][2] + rnd.uniform(2, 4.5), MEMBERS[i][3]
        waist0 = rnd.uniform(70, 80)
        for wk in range(8):
            f = wk / 7
            db.session.add(BodyRecord(user_id=m.id, day=today - timedelta(days=7 * (7 - wk)),
                                      weight_kg=round(w0 - (w0 - MEMBERS[i][2]) * f, 1), height_cm=h,
                                      waist_cm=round(waist0 - 9 * f, 1), hip_cm=round(95 - 2 * f + rnd.uniform(-.5, .5), 1),
                                      bust_cm=round(86 + rnd.uniform(-.5, .5), 1),
                                      body_fat=round(27.5 - 5.5 * f, 1)))
        db.session.add(HealthProfile(user_id=m.id, age=rnd.randint(25, 42), height_cm=h, weight_kg=MEMBERS[i][2],
                                     activity_level="vua", fitness_goal="giam_can"))

    # Check-in 30 ngày
    ca3 = b0[2]
    for i, m in enumerate(members):
        for d in range(1, 31):
            if rnd.random() < 0.55:
                day = today - timedelta(days=d)
                db.session.add(Checkin(user_id=m.id, shift_id=ca3.id if rnd.random() < .6 else b0[3].id, day=day,
                                       at=datetime.combine(day, time(17, rnd.randint(0, 20)))))
    for i, m in enumerate(members[:9]):
        if i == 3:
            continue
        m.last_checkin_day = today
        db.session.add(Checkin(user_id=m.id, shift_id=ca3.id, day=today,
                               at=datetime.combine(today, time(16, 45 + i % 14)), method="qr"))
        db.session.add(Booking(user_id=m.id, shift_id=ca3.id, day=today))
    for m in members[9:]:
        db.session.add(Booking(user_id=m.id, shift_id=b0[3].id, day=today + timedelta(days=1)))

    # Bảng tin
    captions = [("checkin", "Check-in Ca 3 ✨ Hôm nay tập mông & core, mồ hôi rơi đã đời!"),
                ("meal", "Mâm cơm tối nay theo AI: cá kho, canh bí, rau luộc 🥦"),
                ("general", "Tuần 8 rồi, vòng eo giảm 10cm. Cảm ơn Coach Mai Anh ❤️"),
                ("invite", "Ai tập Ca 3 chiều nay cùng mình không? Rủ bạn tập cùng nè 💪")]
    for i in range(8):
        k, t = captions[i % 4]
        p = Post(user_id=members[i].id, kind=k, body=t, shift_id=ca3.id if k in ("checkin", "invite") else None,
                 created_at=datetime.now() - timedelta(hours=2 * i + 1))
        db.session.add(p)
        db.session.flush()
        for lm in rnd.sample(members, rnd.randint(1, 5)):
            db.session.add(PostLike(post_id=p.id, user_id=lm.id))
        if i % 2 == 0:
            db.session.add(PostComment(post_id=p.id, user_id=members[(i + 1) % 12].id, body="Quá đỉnh luôn chị ơi! 🔥"))

    # Chat
    db.session.add_all([
        Message(sender_id=members[0].id, recipient_id=coaches[0].id, body="Coach ơi, tối nay em đi sinh nhật ở nhà hàng Nhật, em có thể ăn sashimi cá hồi với salad không ạ?", created_at=datetime.now() - timedelta(minutes=9)),
        Message(sender_id=coaches[0].id, recipient_id=members[0].id, body="Được nhé em, ưu tiên 150g cá hồi + salad, hạn chế sốt mayonnaise.", created_at=datetime.now() - timedelta(minutes=6), read_at=datetime.now()),
        Message(sender_id=members[0].id, recipient_id=coaches[0].id, body="Dạ em cảm ơn Coach ạ ❤️", created_at=datetime.now() - timedelta(minutes=3)),
        Message(sender_id=mgr.id, recipient_id=members[0].id, body="Chào chị Phương, VitaFlow gửi chị voucher Diamond tháng này nhé!", created_at=datetime.now() - timedelta(days=1), read_at=datetime.now()),
        Message(sender_id=members[1].id, shift_id=ca3.id, body="Chiều nay mình tập Ca 3 nha cả nhà 💕", created_at=datetime.now() - timedelta(hours=2)),
    ])
    db.session.add(Escalation(coach_id=coaches[0].id, member_id=members[3].id, status="open",
                              reason="Học viên báo đau gối sau buổi deadlift, đề nghị Quản lý tư vấn đổi gói phục hồi."))

    # Voucher, đơn, bảo lưu, bữa ăn, nước
    db.session.add_all([
        Voucher(owner_id=members[0].id, granted_by_id=mgr.id, title="Quà Diamond tháng 10", percent=10,
                message="Cảm ơn chị đã đồng hành!", expires_on=today + timedelta(days=45)),
        Voucher(owner_id=members[5].id, granted_by_id=coaches[2].id, title="Thưởng chuyên cần", percent=5,
                expires_on=today + timedelta(days=30))])
    plan = Plan.query.filter_by(code="G3T").first()
    db.session.add(Order(user_id=members[4].id, plan_id=plan.id, branch_id=branches[0].id, shift_id=ca3.id,
                         coach_id=coaches[1].id, amount=plan.price, transfer_code="VF HV106 G3T", status="claimed"))
    db.session.add(FreezeRequest(user_id=members[6].id, days=14, reason="Đi công tác Hà Nội 2 tuần"))
    menu = {"bua_sang": [{"ten_mon": "Xôi xéo (1 gói ~150g)", "dinh_luong_g": 150, "calo": 322}],
            "bua_trua": [{"ten_mon": "Cơm gạo lứt (1 chén ~150g)", "dinh_luong_g": 150, "calo": 182}],
            "bua_toi": [{"ten_mon": "Cơm trắng (1 chén ~150g)", "dinh_luong_g": 150, "calo": 188}]}
    db.session.add(MenuHistory(user_id=members[0].id, title="Thực đơn hôm nay", total_calo=1500,
                               menu_data=json.dumps(menu, ensure_ascii=False), source="offline",
                               workout="Glutes & Core 35' + giãn cơ 10'"))
    db.session.add(MealLog(user_id=members[0].id, meal_key="bua_sang", followed_ai=True, score=9, coach_note="Tốt lắm!"))
    db.session.add(WaterLog(user_id=members[0].id, ml=1250))
    db.session.add(Notification(user_id=members[0].id, text="Bạn nhận được voucher giảm 10% từ Quản lý", url="/app/rewards", icon="redeem"))
    db.session.add(Notification(user_id=mgr.id, text="Coach Mai Anh chuyển tiếp 1 vấn đề cần xử lý", url="/manager/nutrition", icon="flag"))
    db.session.commit()


if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():
        if "--reset" in sys.argv:
            reset_db()
        seed_demo()
        print("Đã nạp dữ liệu demo.")
