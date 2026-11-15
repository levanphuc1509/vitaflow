import os
from datetime import timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent


class Config:
    COMPANY_NAME = os.getenv("COMPANY_NAME", "VitaFlow")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-doi-secret-key-truoc-khi-deploy")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'vitaflow.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 6 * 1024 * 1024
    UPLOAD_FOLDER = str(BASE_DIR / "static" / "uploads")
    ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)
    # VietQR (chuyển khoản)
    BANK_ID = os.getenv("BANK_ID", "MB")
    BANK_ACCOUNT = os.getenv("BANK_ACCOUNT", "0000000000")
    BANK_ACCOUNT_NAME = os.getenv("BANK_ACCOUNT_NAME", "CONG TY VITAFLOW")
    # Điểm chuyên cần -> hạng
    RANK_THRESHOLDS = (("Diamond", 400), ("Gold", 250), ("Silver", 120), ("Bronze", 0))
    WATER_GOAL_ML = 2000
