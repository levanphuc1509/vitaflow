# VitaFlow

**A gym management platform for members, coaches, and managers.**

VitaFlow is a Flask-based project with role-specific web experiences, a mobile-friendly interface, and a Capacitor Android/iOS app shell. The interface and demo data are primarily in Vietnamese.

## What it includes

- Separate dashboards and permissions for managers, coaches, and members.
- Class schedules, bookings, check-ins, and QR-based attendance.
- Membership, progress, messaging, and reward workflows.
- Nutrition planning with an offline fallback and optional Gemini integration.
- A desktop web app and a mobile app project.

## Project layout

| Folder | Purpose |
|---|---|
| [`vitaflow/`](./vitaflow/) | Desktop-oriented Flask web app |
| [`vitaflow_mobile/`](./vitaflow_mobile/) | Mobile-oriented Flask app and server launcher |
| [`vitaflow_mobile/mobile-app/`](./vitaflow_mobile/mobile-app/) | Capacitor project for Android and iOS |

## Run locally

The following commands are for Windows PowerShell. Start with the mobile project:

```powershell
cd vitaflow_mobile
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000). For environment variables and deployment requirements, see the [mobile project guide](./vitaflow_mobile/README.md) and [deployment guide](./vitaflow_mobile/docs/DEPLOY.md).

To test on a phone connected to the same Wi-Fi, run `.\CHAY_SERVER.ps1` from `vitaflow_mobile`. The script detects the computer's LAN address and updates the local Capacitor server URL.

## Mobile builds

See the [Capacitor build guide](./vitaflow_mobile/mobile-app/README.md) for Android and iOS setup. iOS builds require macOS and Xcode.

## Tests

From `vitaflow_mobile`, run:

```powershell
python smoke_test.py
python smoke_test_mobile.py
python smoke_test_store.py
```

## Demo data and privacy

Development mode creates demo accounts and sample data. They are for local testing only; do not use demo credentials in production. Never commit `.env` files, production credentials, member data, or database backups.

This project is under development and is not a substitute for professional medical or nutrition advice.

## More documentation

- [Desktop web guide](./vitaflow/README.md)
- [Mobile/backend guide](./vitaflow_mobile/README.md)
- [Android/iOS store checklist](./vitaflow_mobile/docs/STORE_LISTING.md)
- [Desktop/mobile UI mapping](./vitaflow_mobile/docs/UI_MOBILE_MAPPING.md)

## License

No license has been selected yet. Until a license is added, do not assume the code is available for reuse or redistribution.
