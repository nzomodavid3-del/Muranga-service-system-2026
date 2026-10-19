# Muranga County Public Service Request System

A Python Flask web application for citizens to submit county service issues and track progress. Administrators can review requests, update statuses, add notes, and view basic analytics.

## Features

- Citizen registration and login
- Secure password hashing
- Submit requests with category, location, description, and optional image
- Citizen dashboard to track requests
- Administrator dashboard and status filters
- Status workflow: Pending → In Progress → Resolved
- Basic counts for total, pending, in-progress, and resolved requests
- SQLite database
- CSRF protection on forms
- Responsive layout and optional image upload

## Requirements

- Python 3.10 or newer
- Git (for version control)
- Visual Studio Code (recommended)

## Run on Windows

Open this folder in VS Code. Open **Terminal → New Terminal**, then run:

```powershell
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python app.py
```

If `py` is unavailable, try `python` instead. Open the local URL shown in the terminal, usually `http://127.0.0.1:5000`.

## Create an administrator

Stop the server with `Ctrl+C`, then run:

```powershell
flask --app app create-admin
```

Enter the administrator's full name, email, and a strong password when prompted. Start the server again with `python app.py`, then sign in using that administrator account.

Citizen accounts created through the Register page do not receive administrator privileges.

## Database and uploads

- SQLite database: `muranga.db` (created automatically; intentionally excluded from Git)
- Uploaded images: `static/uploads/` (uploads are intentionally excluded from Git)
- Allowed image formats: PNG, JPG, JPEG, GIF, WEBP
- Maximum upload size: 5 MB

## Before publishing or deploying

1. Set a strong random `SECRET_KEY` environment variable; the development fallback is not for production.
2. Use HTTPS and a production WSGI server for deployment.
3. Configure backups and a privacy/retention policy for citizen data.
4. Add rate limiting, email verification, password reset and audit logging before real public use.
5. Do not commit credentials, private citizen data, the SQLite database, or uploaded user photos.
6. Review and test the application for your institution's security and accessibility requirements.

## Project structure

```text
muranga-service-system/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── muranga.db              # generated locally; not committed
├── static/
│   ├── style.css
│   └── uploads/            # user uploads; not committed
└── templates/
    ├── base.html
    ├── index.html
    ├── register.html
    ├── login.html
    ├── dashboard.html
    ├── new_request.html
    ├── request_detail.html
    ├── admin_dashboard.html
    └── error.html
```

## Suggested test checklist

- Register a citizen account and sign in.
- Submit a test request and verify it appears in the citizen dashboard.
- Sign in with the administrator account and change the request status.
- Return to the citizen account and confirm the status is updated.
- Test invalid login, empty fields, unsupported image formats and access restrictions.
