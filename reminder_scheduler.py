import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from firebase_handler import db
from whatsapp import send_reminder, send_text
from datetime import datetime

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def send_all_reminders():
    """Check all active reminders and send due ones."""
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    
    docs = db.collection("reminders").where("active", "==", True).stream()
    
    for doc in docs:
        reminder = doc.to_dict()
        # Match HH:MM
        if reminder.get("time", "") == current_time:
            send_reminder(
                to=reminder["phone"],
                medicine=reminder.get("medicine", "your medicine"),
                time_str=current_time
            )


def send_daily_checkin():
    """Send morning health check-in to all users at 8 AM IST."""
    users = db.collection("users").stream()
    msg = (
        "🌅 *Good Morning!*\n\n"
        "How are you feeling today?\n"
        "Reply with: Good 😊 / Not well 😔 / Any symptoms\n\n"
        "_SeniorCare AI Daily Check-in_"
    )
    for user in users:
        data = user.to_dict()
        if data.get("phone"):
            send_text(data["phone"], msg)


def start_scheduler():
    # Check reminders every minute
    scheduler.add_job(send_all_reminders, CronTrigger(minute="*"))
    # Daily check-in at 8 AM IST
    scheduler.add_job(send_daily_checkin, CronTrigger(hour=8, minute=0))
    scheduler.start()
    print("[Scheduler] Started ✅")