import os
import json
import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                phone TEXT PRIMARY KEY,
                data JSONB
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id SERIAL PRIMARY KEY,
                phone TEXT,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                phone TEXT,
                medicine TEXT,
                time TEXT,
                frequency TEXT,
                active BOOLEAN DEFAULT TRUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS health_logs (
                id SERIAL PRIMARY KEY,
                phone TEXT,
                type TEXT,
                value TEXT,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.commit()
    print("[DB] Tables ready ✅")


def get_user(phone):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data FROM users WHERE phone=%s", (phone,)
        ).fetchone()
    return row["data"] if row else {}


def upsert_user(phone, data):
    existing = get_user(phone)
    existing.update(data)
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO users (phone, data)
            VALUES (%s, %s)
            ON CONFLICT (phone) DO UPDATE SET data = EXCLUDED.data
        """, (phone, json.dumps(existing)))
        conn.commit()


def add_message_to_history(phone, role, content):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO history (phone, role, content) VALUES (%s, %s, %s)",
            (phone, role, content)
        )
        conn.commit()


def get_recent_history(phone, limit=6):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT role, content FROM history
            WHERE phone=%s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (phone, limit)).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def save_reminder(phone, medicine, time_str, frequency="daily"):
    with get_conn() as conn:
        existing = conn.execute("""
            SELECT id FROM reminders
            WHERE phone=%s AND LOWER(medicine)=LOWER(%s) AND time=%s AND active=TRUE
        """, (phone, medicine, time_str)).fetchone()
        if existing:
            return False
        conn.execute("""
            INSERT INTO reminders (phone, medicine, time, frequency)
            VALUES (%s, %s, %s, %s)
        """, (phone, medicine, time_str, frequency))
        conn.commit()
    return True


def get_active_reminders(phone):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE phone=%s AND active=TRUE", (phone,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_active_reminders():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE active=TRUE"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_reminder(phone, medicine):
    with get_conn() as conn:
        conn.execute("""
            UPDATE reminders SET active=FALSE
            WHERE phone=%s AND LOWER(medicine)=LOWER(%s)
        """, (phone, medicine))
        conn.commit()


def save_health_log(phone, log_type, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO health_logs (phone, type, value) VALUES (%s, %s, %s)",
            (phone, log_type, value)
        )
        conn.commit()


def get_health_logs(phone, limit=10):
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM health_logs WHERE phone=%s
            ORDER BY timestamp DESC LIMIT %s
        """, (phone, limit)).fetchall()
    return [dict(r) for r in rows]