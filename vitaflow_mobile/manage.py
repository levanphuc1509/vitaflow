"""Lệnh quản trị khi chạy thật (không dùng dữ liệu demo):
    python manage.py create-manager --email quanly@congty.vn --name "Nguyễn Văn A"
    python manage.py reset-password --email quanly@congty.vn
    python manage.py create-branch --name "Cơ sở 1" --address "..." """
import argparse
import getpass
import sys

from app import create_app
from extensions import db
from models import Branch, User


def main():
    p = argparse.ArgumentParser(description="VITAFLOW - quản trị")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("create-manager"); m.add_argument("--email", required=True); m.add_argument("--name", required=True); m.add_argument("--password")
    r = sub.add_parser("reset-password"); r.add_argument("--email", required=True); r.add_argument("--password")
    b = sub.add_parser("create-branch"); b.add_argument("--name", required=True); b.add_argument("--address", default="")
    b.add_argument("--lat", type=float, default=10.8); b.add_argument("--lng", type=float, default=106.7)
    args = p.parse_args()
    app = create_app()
    with app.app_context():
        if args.cmd == "create-branch":
            db.session.add(Branch(name=args.name, address=args.address, lat=args.lat, lng=args.lng)); db.session.commit()
            print("Đã tạo cơ sở:", args.name); return
        pw = args.password or getpass.getpass("Mật khẩu (tối thiểu 8 ký tự): ")
        if len(pw) < 8:
            sys.exit("Mật khẩu quá ngắn.")
        email = args.email.strip().lower()
        u = User.query.filter_by(email=email).first()
        if args.cmd == "create-manager":
            if u:
                sys.exit("Email đã tồn tại.")
            br = Branch.query.first()
            u = User(full_name=args.name, email=email, role="manager", title="Quản lý chuỗi", branch_id=br.id if br else None)
        elif not u:
            sys.exit("Không tìm thấy tài khoản.")
        u.set_password(pw); db.session.add(u); db.session.commit()
        print("Xong:", email)


if __name__ == "__main__":
    main()
