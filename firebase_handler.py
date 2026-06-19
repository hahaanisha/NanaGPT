import os
import json
import psycopg
from psycopg.rows import dict_row
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_conn():
    conn = psycopg.connect(DATABASE_URL)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            phone TEXT PRIMARY KEY,
            data JSONB
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id SERIAL PRIMARY KEY,
            phone TEXT,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            phone TEXT,
            medicine TEXT,
            time TEXT,
            frequency TEXT,
            active BOOLEAN DEFAULT TRUE
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS health_logs (
            id SERIAL PRIMARY KEY,
            phone TEXT,
            type TEXT,
            value TEXT,
            timestamp TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("[DB] Tables ready ✅")


def get_user(phone):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg.extras.RealDictCursor)
    cur.execute("SELECT data FROM users WHERE phone=%s", (phone,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row["data"] if row else {}


def upsert_user(phone, data):
    existing = get_user(phone)
    existing.update(data)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (phone, data)
        VALUES (%s, %s)
        ON CONFLICT (phone) DO UPDATE SET data = EXCLUDED.data
    """, (phone, json.dumps(existing)))
    conn.commit()
    cur.close()
    conn.close()


def add_message_to_history(phone, role, content):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO history (phone, role, content) VALUES (%s, %s, %s)",
        (phone, role, content)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_recent_history(phone, limit=6):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg.extras.RealDictCursor)
    cur.execute("""
        SELECT role, content FROM history
        WHERE phone=%s
        ORDER BY timestamp DESC
        LIMIT %s
    """, (phone, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def save_reminder(phone, medicine, time_str, frequency="daily"):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg.extras.RealDictCursor)
    cur.execute("""
        SELECT id FROM reminders
        WHERE phone=%s AND LOWER(medicine)=LOWER(%s) AND time=%s AND active=TRUE
    """, (phone, medicine, time_str))
    existing = cur.fetchone()
    if existing:
        cur.close()
        conn.close()
        return False  # duplicate
    cur.execute("""
        INSERT INTO reminders (phone, medicine, time, frequency)
        VALUES (%s, %s, %s, %s)
    """, (phone, medicine, time_str, frequency))
    conn.commit()
    cur.close()
    conn.close()
    return True


def get_active_reminders(phone):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM reminders WHERE phone=%s AND active=TRUE", (phone,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_all_active_reminders():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg.extras.RealDictCursor)
    cur.execute("SELECT * FROM reminders WHERE active=TRUE")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def delete_reminder(phone, medicine):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE reminders SET active=FALSE
        WHERE phone=%s AND LOWER(medicine)=LOWER(%s)
    """, (phone, medicine))
    conn.commit()
    cur.close()
    conn.close()


def save_health_log(phone, log_type, value):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO health_logs (phone, type, value) VALUES (%s, %s, %s)",
        (phone, log_type, value)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_health_logs(phone, limit=10):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg.extras.RealDictCursor)
    cur.execute("""
        SELECT * FROM health_logs WHERE phone=%s
        ORDER BY timestamp DESC LIMIT %s
    """, (phone, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]