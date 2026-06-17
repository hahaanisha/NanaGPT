# firebase_handler.py  — SQLite version, no Firebase needed
import sqlite3
import json
from datetime import datetime

DB_PATH = "seniorcare.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            phone TEXT PRIMARY KEY,
            data TEXT
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            medicine TEXT,
            time TEXT,
            frequency TEXT,
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS health_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            response TEXT,
            timestamp TEXT
        );
    """)
    conn.commit()
    conn.close()

def get_user(phone):
    conn = get_conn()
    row = conn.execute("SELECT data FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    return json.loads(row["data"]) if row else {}

def upsert_user(phone, data):
    existing = get_user(phone)
    existing.update(data)
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO users VALUES (?,?)", (phone, json.dumps(existing)))
    conn.commit()
    conn.close()

def add_message_to_history(phone, role, content):
    conn = get_conn()
    conn.execute("INSERT INTO history (phone,role,content,timestamp) VALUES (?,?,?,?)",
                 (phone, role, content, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_recent_history(phone, limit=6):
    conn = get_conn()
    rows = conn.execute(
        "SELECT role, content FROM history WHERE phone=? ORDER BY timestamp DESC LIMIT ?",
        (phone, limit)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

def save_reminder(phone, reminder):
    conn = get_conn()
    conn.execute(
        "INSERT INTO reminders (phone, medicine, time, frequency) VALUES (?,?,?,?)",
        (phone, reminder.get("medicine",""), reminder.get("time",""), reminder.get("frequency","daily"))
    )
    conn.commit()
    conn.close()

def get_active_reminders(phone):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM reminders WHERE phone=? AND active=1", (phone,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def log_health_checkin(phone, response):
    conn = get_conn()
    conn.execute("INSERT INTO health_logs (phone,response,timestamp) VALUES (?,?,?)",
                 (phone, response, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

# Call this once at startup
init_db()