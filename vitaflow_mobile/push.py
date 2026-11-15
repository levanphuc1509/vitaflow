"""Gửi thông báo đẩy tới app Android/iOS.
  - Android: Firebase Cloud Messaging (FCM). Cần FIREBASE_CREDENTIALS=<service-account.json> và `firebase-admin`.
  - iOS: Capacitor trả về token APNs (không phải token FCM) nên gửi thẳng tới APNs bằng khoá .p8 của Apple:
        APNS_KEY_PATH, APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID  (+ APNS_USE_SANDBOX=1 chỉ cho bản Debug chạy từ Xcode; TestFlight/App Store dùng production).
Không cấu hình -> bỏ qua êm, thông báo vẫn hiện trong app."""
import logging
import os
import threading
import time

log = logging.getLogger(__name__)
_fb_app = None
_jwt_cache = {"t": 0, "v": None}


def fcm_enabled():
    return bool(os.getenv("FIREBASE_CREDENTIALS"))


def apns_enabled():
    return all(os.getenv(k) for k in ("APNS_KEY_PATH", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID"))


def enabled():
    return fcm_enabled() or apns_enabled()


# ----------------------------------------------------------------- Android (FCM)
def _send(tokens, title, body, url):
    """Trả về danh sách token FCM không còn hợp lệ."""
    global _fb_app
    import firebase_admin
    from firebase_admin import credentials, messaging
    if _fb_app is None:
        _fb_app = firebase_admin.initialize_app(credentials.Certificate(os.environ["FIREBASE_CREDENTIALS"]))
    msgs = [messaging.Message(token=t, notification=messaging.Notification(title=title, body=body[:180]),
                              data={"url": url or ""}) for t in tokens]
    resp = messaging.send_each(msgs)
    return [tokens[i] for i, r in enumerate(resp.responses)
            if not r.success and isinstance(r.exception, (messaging.UnregisteredError, messaging.SenderIdMismatchError))]


# ----------------------------------------------------------------- iOS (APNs HTTP/2)
def _apns_jwt():
    import jwt
    now = int(time.time())
    if _jwt_cache["v"] and now - _jwt_cache["t"] < 3000:      # Apple cho phép dùng lại token tối đa 60 phút
        return _jwt_cache["v"]
    with open(os.environ["APNS_KEY_PATH"], encoding="utf-8") as f:
        key = f.read()
    tok = jwt.encode({"iss": os.environ["APNS_TEAM_ID"], "iat": now}, key, algorithm="ES256",
                     headers={"kid": os.environ["APNS_KEY_ID"]})
    _jwt_cache.update(t=now, v=tok)
    return tok


def _client_factory():
    import httpx
    return httpx.Client(http2=True, timeout=10)


def _send_apns(tokens, title, body, url):
    """Gửi tới APNs; trả về danh sách token đã hết hạn/không hợp lệ."""
    host = "https://api.sandbox.push.apple.com" if os.getenv("APNS_USE_SANDBOX") == "1" else "https://api.push.apple.com"
    headers = {"authorization": "bearer " + _apns_jwt(), "apns-topic": os.environ["APNS_BUNDLE_ID"],
               "apns-push-type": "alert", "apns-priority": "10"}
    payload = {"aps": {"alert": {"title": title, "body": body[:180]}, "sound": "default"}, "url": url or ""}
    bad = []
    with _client_factory() as c:
        for t in tokens:
            r = c.post(f"{host}/3/device/{t}", json=payload, headers=headers)
            reason = ""
            try:
                reason = r.json().get("reason", "")
            except Exception:  # noqa: BLE001
                pass
            if r.status_code == 410 or reason in ("BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic"):
                bad.append(t)
            elif r.status_code != 200:
                log.warning("APNs %s: %s", r.status_code, reason)
    return bad


# ----------------------------------------------------------------- điều phối
def dispatch(app, items, sender=None, apns_sender=None):
    """items: [(user_id, text, url)]. Android -> FCM, iOS -> APNs. Xoá token chết."""
    use_fcm, use_apns = bool(sender) or fcm_enabled(), bool(apns_sender) or apns_enabled()
    sender, apns_sender = sender or _send, apns_sender or _send_apns
    with app.app_context():
        from extensions import db
        from models import DeviceToken
        for user_id, text, url in items:
            rows = DeviceToken.query.filter_by(user_id=user_id).all()
            groups = (([d.token for d in rows if d.platform != "ios"], sender, use_fcm),
                      ([d.token for d in rows if d.platform == "ios"], apns_sender, use_apns))
            for tokens, fn, ok in groups:
                if not tokens or not ok:
                    continue
                try:
                    bad = fn(tokens, app.config["COMPANY_NAME"], text, url)
                    if bad:
                        DeviceToken.query.filter(DeviceToken.token.in_(bad)).delete(synchronize_session=False)
                        db.session.commit()
                except Exception as exc:  # noqa: BLE001
                    log.warning("Gửi push thất bại: %s", exc)


def dispatch_async(app, items):
    threading.Thread(target=dispatch, args=(app, items), daemon=True).start()
