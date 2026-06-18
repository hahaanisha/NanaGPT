import os
import requests
from dotenv import load_dotenv

load_dotenv()

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
API_URL = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"

def get_headers():
    # Refresh token from env each time (in case updated)
    return {
        "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
        "Content-Type": "application/json"
    }

def send_text(to: str, message: str):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    r = requests.post(API_URL, json=payload, headers=get_headers())
    print(f"[WA] {to}: {r.status_code}")
    return r.json()

def send_reminder(to: str, medicine: str, time_str: str):
    msg = (
        f"💊 *Medicine Reminder*\n\n"
        f"Time to take: *{medicine}*\n"
        f"Scheduled: {time_str}\n\n"
        f"Reply *done* once taken ✅"
    )
    return send_text(to, msg)

def get_media_url(media_id: str) -> str:
    r = requests.get(
        f"https://graph.facebook.com/v20.0/{media_id}",
        headers={"Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}"}
    )
    return r.json().get("url", "")

def download_media(media_url: str) -> bytes:
    r = requests.get(
        media_url,
        headers={"Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}"}
    )
    return r.content