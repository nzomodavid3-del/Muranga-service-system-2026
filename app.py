import os
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, url_for
from flask_login import (
    LoginManager, UserMixin, current_user, login_required, login_user, logout_user
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "muranga.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)

csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "info"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'citizen',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS service_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            image_filename TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            admin_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    db.commit()


with app.app_context():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.full_name = row["full_name"]
        self.email = row["email"]
        self.role = row["role"]


@login_manager.user_loader
def load_user(user_id):
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User(row) if row else None


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.context_processor
def inject_year():
    return {"current_year": datetime.now().year}


@app.route("/")
def index():
    db = get_db()
    totals = {
        "total": db.execute("SELECT COUNT(*) FROM service_requests").fetchone()[0],
        "pending": db.execute("SELECT COUNT(*) FROM service_requests WHERE status='Pending'").fetchone()[0],
        "in_progress": db.execute("SELECT COUNT(*) FROM service_requests WHERE status='In Progress'").fetchone()[0],
        "resolved": db.execute("SELECT COUNT(*) FROM service_requests WHERE status='Resolved'").fetchone()[0],
    }
    latest = db.execute("""
        SELECT sr.*, u.full_name AS citizen_name
        FROM service_requests sr JOIN users u ON u.id = sr.user_id
        ORDER BY sr.created_at DESC LIMIT 5
    """).fetchall()
    return render_template("index.html", totals=totals, latest=latest)


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not full_name or not email or not password:
            flash("Please complete all required fields.", "danger")
        elif len(password) < 8:
            flash("Use a password with at least 8 characters.", "danger")
        elif password != confirm:
            flash("The passwords do not match.", "danger")
        else:
            db = get_db()
            try:
                cur = db.execute(
                    "INSERT INTO users (full_name, email, password_hash, role, created_at) VALUES (?, ?, ?, 'citizen', ?)",
                    (full_name, email, generate_password_hash(password), datetime.now().isoformat(timespec="seconds"))
                )
                db.commit()
                row = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
                login_user(User(row))
                flash("Your account has been created. Welcome!", "success")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "danger")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        row = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row and check_password_hash(row["password_hash"], password):
            login_user(User(row))
            flash("You are now signed in.", "success")
            return redirect(url_for("admin_dashboard" if row["role"] == "admin" else "dashboard"))
        flash("Email or password is incorrect.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have signed out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    rows = get_db().execute("""
        SELECT * FROM service_requests WHERE user_id = ?
        ORDER BY created_at DESC
    """, (current_user.id,)).fetchall()
    return render_template("dashboard.html", requests_list=rows)


@app.route("/requests/new", methods=["GET", "POST"])
@login_required
def new_request():
    categories = ["Water", "Roads", "Street lighting", "Garbage collection", "Drainage", "Other"]
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        image = request.files.get("image")
        if not title or category not in categories or not location or not description:
            flash("Please complete all required fields and select a valid category.", "danger")
            return render_template("new_request.html", categories=categories)
        filename = None
        if image and image.filename:
            if not allowed_file(image.filename):
                flash("Image must be PNG, JPG, JPEG, GIF, or WEBP.", "danger")
                return render_template("new_request.html", categories=categories)
            filename = f"{uuid.uuid4().hex}_{secure_filename(image.filename)}"
            image.save(UPLOAD_DIR / filename)
        now = datetime.now().isoformat(timespec="seconds")
        db = get_db()
        db.execute("""
            INSERT INTO service_requests
            (user_id, title, category, location, description, image_filename, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending', ?, ?)
        """, (current_user.id, title, category, location, description, filename, now, now))
        db.commit()
        flash("Your service request has been submitted.", "success")
        return redirect(url_for("dashboard"))
    return render_template("new_request.html", categories=categories)


@app.route("/requests/<int:request_id>")
@login_required
def request_detail(request_id):
    row = get_db().execute("""
        SELECT sr.*, u.full_name AS citizen_name, u.email AS citizen_email
        FROM service_requests sr JOIN users u ON u.id = sr.user_id
        WHERE sr.id = ?
    """, (request_id,)).fetchone()
    if not row:
        abort(404)
    if current_user.role != "admin" and row["user_id"] != current_user.id:
        abort(403)
    return render_template("request_detail.html", service_request=row)


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    totals = {
        "total": db.execute("SELECT COUNT(*) FROM service_requests").fetchone()[0],
        "pending": db.execute("SELECT COUNT(*) FROM service_requests WHERE status='Pending'").fetchone()[0],
        "in_progress": db.execute("SELECT COUNT(*) FROM service_requests WHERE status='In Progress'").fetchone()[0],
        "resolved": db.execute("SELECT COUNT(*) FROM service_requests WHERE status='Resolved'").fetchone()[0],
    }
    status_filter = request.args.get("status", "")
    query = """
        SELECT sr.*, u.full_name AS citizen_name
        FROM service_requests sr JOIN users u ON u.id = sr.user_id
    """
    params = []
    if status_filter in {"Pending", "In Progress", "Resolved"}:
        query += " WHERE sr.status = ?"
        params.append(status_filter)
    query += " ORDER BY sr.created_at DESC"
    rows = db.execute(query, params).fetchall()
    return render_template("admin_dashboard.html", totals=totals, requests_list=rows, status_filter=status_filter)


@app.route("/admin/requests/<int:request_id>/update", methods=["POST"])
@admin_required
def update_request(request_id):
    status = request.form.get("status", "")
    note = request.form.get("admin_note", "").strip()
    if status not in {"Pending", "In Progress", "Resolved"}:
        flash("Invalid status selected.", "danger")
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    exists = db.execute("SELECT id FROM service_requests WHERE id = ?", (request_id,)).fetchone()
    if not exists:
        abort(404)
    db.execute(
        "UPDATE service_requests SET status = ?, admin_note = ?, updated_at = ? WHERE id = ?",
        (status, note, datetime.now().isoformat(timespec="seconds"), request_id)
    )
    db.commit()
    flash(f"Request #{request_id} updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.cli.command("create-admin")
def create_admin():
    """Create an administrator account."""
    full_name = click.prompt("Administrator full name")
    email = click.prompt("Administrator email").strip().lower()
    password = click.prompt("Administrator password", hide_input=True, confirmation_prompt=True)
    if len(password) < 8:
        raise click.ClickException("Password must be at least 8 characters.")
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (full_name, email, password_hash, role, created_at) VALUES (?, ?, ?, 'admin', ?)",
            (full_name.strip(), email, generate_password_hash(password), datetime.now().isoformat(timespec="seconds"))
        )
        db.commit()
        click.echo(f"Administrator account created for {email}.")
    except sqlite3.IntegrityError:
        raise click.ClickException("That email already exists. Use another email or promote the account manually.")


@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="The page or request could not be found."), 404


if __name__ == "__main__":
    app.run(debug=True)
