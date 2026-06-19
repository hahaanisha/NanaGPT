from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import pytz

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

# In-memory tracking of sent reminders awaiting confirmation
# Format: { "phone_medicine_HH:MM": { "count": 1, "sent_at": datetime } }
pending_confirmations = {}


def send_all_reminders():
    from firebase_handler import get_all_active_reminders
    from whatsapp import send_reminder, send_text

    IST = pytz.timezone("Asia/Kolkata")
    now = datetime.now(IST)
    current_time = now.strftime("%H:%M")
    print(f"[Scheduler] Checking reminders at {current_time} IST")

    try:
        reminders = get_all_active_reminders()
        print(f"[Scheduler] {len(reminders)} active reminder(s)")

        for r in reminders:
            phone = r["phone"]
            medicine = r["medicine"]
            scheduled_time = r["time"]
            key = f"{phone}_{medicine}_{scheduled_time}"

            # ── Send initial reminder at scheduled time ────────────────────
            if scheduled_time == current_time:
                print(f"[Scheduler] Sending initial reminder to {phone}")
                send_reminder(to=phone, medicine=medicine, time_str=current_time)
                pending_confirmations[key] = {
                    "count": 1,
                    "sent_at": now,
                    "phone": phone,
                    "medicine": medicine
                }

            # ── Send follow-up if not confirmed ───────────────────────────
            elif key in pending_confirmations:
                pending = pending_confirmations[key]
                count = pending["count"]
                sent_at = pending["sent_at"]
                minutes_passed = (now - sent_at).seconds // 60

                # Follow-up messages at 10 min and 20 min (max 3 total)
                if count == 1 and minutes_passed >= 10:
                    print(f"[Scheduler] Follow-up 1 to {phone}")
                    send_text(phone,
                        f"💊 *Reminder — {medicine}*\n\n"
                        f"It seems you haven't taken your medicine yet.\n"
                        f"Please take *{medicine}* now if you haven't. 🙏\n\n"
                        f"Reply *done* once taken ✅"
                    )
                    pending_confirmations[key]["count"] = 2
                    pending_confirmations[key]["sent_at"] = now

                elif count == 2 and minutes_passed >= 10:
                    print(f"[Scheduler] Follow-up 2 to {phone}")
                    send_text(phone,
                        f"⚠️ *Final Reminder — {medicine}*\n\n"
                        f"This is your last reminder to take *{medicine}*.\n"
                        f"Skipping medicines regularly can affect your health.\n\n"
                        f"Please take it now and reply *done* ✅\n\n"
                        f"_If you have already taken it, please reply done._"
                    )
                    pending_confirmations[key]["count"] = 3
                    pending_confirmations[key]["sent_at"] = now

                elif count >= 3:
                    # Max reminders sent — stop and clean up
                    print(f"[Scheduler] Max reminders reached for {phone}, cleaning up")
                    del pending_confirmations[key]

    except Exception as e:
        print(f"[Scheduler] Error: {e}")


def confirm_medicine_taken(phone: str, medicine: str = None):
    """
    Call this when user replies 'done'.
    Clears all pending confirmations for this user,
    or just for a specific medicine if provided.
    """
    keys_to_remove = []
    for key in pending_confirmations:
        if key.startswith(phone):
            if medicine is None or medicine.lower() in key.lower():
                keys_to_remove.append(key)
    for key in keys_to_remove:
        del pending_confirmations[key]
    print(f"[Scheduler] Cleared confirmations for {phone}: {keys_to_remove}")


def start_scheduler():
    scheduler.add_job(
        send_all_reminders,
        CronTrigger(minute="*"),
        id="reminder_job",
        replace_existing=True
    )
    scheduler.start()
    print("[Scheduler] Started ✅")