import os
import requests
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
API_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json"
}

def send_text(to: str, message: str):
    """Send plain text message."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    r = requests.post(API_URL, json=payload, headers=HEADERS)
    print(f"[WA] Sent to {to}: {r.status_code} {r.text}")
    return r.json()


def send_emergency_alert(caregiver_number: str, senior_name: str, 
                          senior_phone: str, symptom: str):
    """Send urgent alert to caregiver."""
    msg = (
        f"🚨 *EMERGENCY ALERT — SeniorCare AI*\n\n"
        f"👤 Senior: {senior_name}\n"
        f"📞 Phone: +{senior_phone}\n"
        f"⚠️ Reported: {symptom}\n\n"
        f"Please contact them immediately or call emergency services."
    )
    return send_text(caregiver_number, msg)


def send_reminder(to: str, medicine: str, time_str: str):
    """Send medicine reminder."""
    msg = (
        f"💊 *Medicine Reminder*\n\n"
        f"Time to take: *{medicine}*\n"
        f"Scheduled: {time_str}\n\n"
        f"Reply 'done' once taken ✅"
    )
    return send_text(to, msg)


def get_media_url(media_id: str) -> str:
    """Get downloadable URL for image/audio from WhatsApp."""
    r = requests.get(
        f"https://graph.facebook.com/v20.0/{media_id}",
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    )
    return r.json().get("url", "")


def download_media(media_url: str) -> bytes:
    """Download media bytes from WhatsApp CDN."""
    r = requests.get(
        media_url,
        headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    )
    return r.content