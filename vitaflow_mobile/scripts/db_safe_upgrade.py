"""vitaflow_mobile/scripts/db_safe_upgrade.py

Sao lưu database rồi mới chạy `flask db upgrade`. Dùng thay cho lệnh upgrade trần.

Chạy (PowerShell, từ thư mục vitaflow_mobile):
    python scripts/db_safe_upgrade.py

Cần: tồn tại hàm create_app() trong app.py (đổi import bên dưới nếu tên khác).
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flask_migrate import upgrade          # noqa: E402
from sqlalchemy.engine import make_url      # noqa: E402

from app import create_app                  # noqa: E402  <- chỉnh nếu app factory ở file khác


def backup_sqlite(db_path: Path) -> Path:
    backup_dir = ROOT / "backups"
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"{db_path.stem}_{datetime.now():%Y%m%d_%H%M%S}{db_path.suffix}"
    # Dùng SQLite backup API: an toàn kể cả khi DB đang được mở.
    src, dst = sqlite3.connect(db_path), sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return dest


def main() -> int:
    app = create_app()
    with app.app_context():
        url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
        backup = None
        if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
            db_path = Path(url.database)
            if not db_path.is_absolute():
                db_path = Path(app.instance_path) / db_path if (Path(app.instance_path) / db_path).exists() \
                    else ROOT / db_path
            backup = backup_sqlite(db_path)
            print(f"[OK] Đã sao lưu: {backup}")
        else:
            print("[CẢNH BÁO] Không phải SQLite - hãy tự sao lưu (vd pg_dump) trước khi tiếp tục.")
            if input("Đã sao lưu? Gõ 'yes' để tiếp tục: ").strip().lower() != "yes":
                return 1
        try:
            upgrade()
        except Exception as exc:  # noqa: BLE001
            print(f"[LỖI] Upgrade thất bại: {exc}")
            if backup:
                print(f"Khôi phục bằng cách chép đè file: {backup}")
            return 2
        print("[OK] Database đã lên phiên bản mới nhất.")
    return 0


if __name__ == "__main__":
    sys.exit(main())