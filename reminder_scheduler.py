from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from firebase_handler import get_conn
from whatsapp import send_reminder
from datetime import datetime

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

def send_all_reminders():
    current_time = datetime.now().strftime("%H:%M")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM reminders WHERE active=1 AND time=?", (current_time,)
    ).fetchall()
    conn.close()
    for row in rows:
        send_reminder(
            to=row["phone"],
            medicine=row["medicine"],
            time_str=current_time
        )

def start_scheduler():
    scheduler.add_job(send_all_reminders, CronTrigger(minute="*"))
    scheduler.start()
    print("[Scheduler] Started ✅")