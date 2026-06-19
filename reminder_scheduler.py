from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import pytz

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def send_all_reminders():
    # Import here to avoid circular imports
    from firebase_handler import get_all_active_reminders
    from whatsapp import send_reminder

    IST = pytz.timezone("Asia/Kolkata")
    current_time = datetime.now(IST).strftime("%H:%M")
    print(f"[Scheduler] Checking reminders at {current_time} IST")

    reminders = get_all_active_reminders()
    print(f"[Scheduler] Found {len(reminders)} active reminders")

    for r in reminders:
        print(f"[Scheduler] Checking: {r['medicine']} at {r['time']} for {r['phone']}")
        if r["time"] == current_time:
            print(f"[Scheduler] Sending reminder to {r['phone']}")
            send_reminder(
                to=r["phone"],
                medicine=r["medicine"],
                time_str=current_time
            )


def start_scheduler():
    scheduler.add_job(
        send_all_reminders,
        CronTrigger(minute="*"),
        id="reminder_job",
        replace_existing=True
    )
    scheduler.start()
    print("[Scheduler] Started ✅")