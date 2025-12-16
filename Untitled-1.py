"""
A deliberately complex Python application intended to exercise GitHub CodeQL.

This app mixes:
- Flask web API
- SQLite persistence
- Authentication & authorization
- File uploads & parsing
- Subprocess execution
- Deserialization
- Logging
- Background jobs

NOTE: This code is intentionally *not secure* in places. Do NOT deploy.
"""

import os
import sqlite3
import json
import pickle
import hashlib
import logging
import threading
import time
import subprocess
from functools import wraps
from datetime import datetime

from flask import (
    Flask,
    request,
    jsonify,
    g,
    send_from_directory
)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_ROOT, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "app.db")
LOG_PATH = os.path.join(DATA_DIR, "app.log")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Flask app
# -----------------------------------------------------------------------------

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

# -----------------------------------------------------------------------------
# Database helpers
# -----------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            is_admin INTEGER
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT,
            action TEXT,
            metadata TEXT,
            created_at TEXT
        )
        """
    )

    db.commit()
    db.close()

# -----------------------------------------------------------------------------
# Security helpers (intentionally naive)
# -----------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate(username, password):
    db = get_db()
    row = db.execute(
        f"SELECT * FROM users WHERE username = '{username}'"
    ).fetchone()

    if not row:
        return None

    if row["password_hash"] == hash_password(password):
        return dict(row)

    return None


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-Auth")
        if not token:
            return jsonify({"error": "missing auth"}), 401

        try:
            user = json.loads(token)
        except Exception:
            return jsonify({"error": "invalid token"}), 401

        g.user = user
        return fn(*args, **kwargs)

    return wrapper

# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "missing fields"}), 400

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 0)",
            (username, hash_password(password)),
        )
        db.commit()
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"status": "registered"})


@app.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    user = authenticate(data.get("username"), data.get("password"))

    if not user:
        return jsonify({"error": "invalid credentials"}), 403

    # insecure token on purpose
    token = json.dumps({
        "username": user["username"],
        "is_admin": user["is_admin"],
    })

    return jsonify({"token": token})


@app.route("/upload", methods=["POST"])
@require_auth
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400

    f = request.files["file"]
    path = os.path.join(UPLOAD_DIR, f.filename)
    f.save(path)

    log_action(g.user["username"], "upload", {"file": f.filename})

    return jsonify({"status": "uploaded", "path": path})


@app.route("/files/<path:filename>")
@require_auth
def get_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/admin/exec", methods=["POST"])
@require_auth
def admin_exec():
    if not g.user.get("is_admin"):
        return jsonify({"error": "admin only"}), 403

    cmd = request.json.get("cmd")
    if not cmd:
        return jsonify({"error": "missing cmd"}), 400

    # dangerous on purpose
    output = subprocess.getoutput(cmd)

    log_action(g.user["username"], "exec", {"cmd": cmd})

    return jsonify({"output": output})


@app.route("/deserialize", methods=["POST"])
@require_auth
def deserialize():
    raw = request.data

    try:
        obj = pickle.loads(raw)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({"type": str(type(obj)), "value": str(obj)})

# -----------------------------------------------------------------------------
# Audit logging
# -----------------------------------------------------------------------------

def log_action(actor, action, metadata):
    db = get_db()
    db.execute(
        "INSERT INTO audit_log (actor, action, metadata, created_at) VALUES (?, ?, ?, ?)",
        (
            actor,
            action,
            json.dumps(metadata),
            datetime.utcnow().isoformat(),
        ),
    )
    db.commit()

# -----------------------------------------------------------------------------
# Background worker
# -----------------------------------------------------------------------------

class CleanupWorker(threading.Thread):
    daemon = True

    def run(self):
        while True:
            try:
                self.cleanup_uploads()
            except Exception as e:
                logger.exception("cleanup failed: %s", e)
            time.sleep(60)

    def cleanup_uploads(self):
        now = time.time()
        for name in os.listdir(UPLOAD_DIR):
            path = os.path.join(UPLOAD_DIR, name)
            if os.path.isfile(path):
                age = now - os.path.getmtime(path)
                if age > 3600:
                    os.remove(path)
                    logger.info("removed old file %s", path)

# -----------------------------------------------------------------------------
# App entrypoint
# -----------------------------------------------------------------------------

def main():
    init_db()
    worker = CleanupWorker()
    worker.start()

    logger.info("starting app")
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
