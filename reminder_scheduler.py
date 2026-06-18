from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from firebase_handler import get_active_reminders, get_conn
from whatsapp import send_reminder, send_text
from datetime import datetime

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def send_all_reminders():
    """Check all active reminders and send due ones."""
    current_time = datetime.now().strftime("%H:%M")
    
    # Get all active reminders directly via SQLite
    conn = get_conn()
    rows = conn.execute("SELECT * FROM reminders WHERE active=1").fetchall()
    conn.close()
    
    for row in rows:
        if row["time"] == current_time:
            send_reminder(
                to=row["phone"],
                medicine=row["medicine"],
                time_str=current_time
            )


def send_daily_checkin():
    """Send morning health check-in to all users at 8 AM IST."""
    conn = get_conn()
    users = conn.execute("SELECT phone FROM users").fetchall()
    conn.close()
    
    msg = (
        "🌅 *Good Morning!*\n\n"
        "How are you feeling today?\n"
        "Reply with: Good 😊 / Not well 😔 / Any symptoms\n\n"
        "_SeniorCare AI Daily Check-in_"
    )
    for user in users:
        send_text(user["phone"], msg)


def start_scheduler():
    scheduler.add_job(send_all_reminders, CronTrigger(minute="*"))
    scheduler.add_job(send_daily_checkin, CronTrigger(hour=8, minute=0))
    scheduler.start()
    print("[Scheduler] Started ✅")