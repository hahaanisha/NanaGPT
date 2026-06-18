import os
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from asi_handler import chat_with_asi, explain_prescription, detect_emergency
from whatsapp import send_text, send_emergency_alert, get_media_url, download_media
from firebase_handler import (get_user, upsert_user, add_message_to_history,
                               get_recent_history, save_reminder, log_health_checkin, init_db)
from reminder_scheduler import start_scheduler

load_dotenv()
init_db()

app = Flask(__name__)
VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN")
CAREGIVER_PHONE = os.getenv("CAREGIVER_PHONE")

# ─── Webhook Verification ──────────────────────────────────────────────────────
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[Webhook] Verified ✅")
        return challenge, 200
    return "Forbidden", 403


# ─── Incoming Messages ─────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.get_json()
    print(f"[Webhook] Received: {json.dumps(data)}")

    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" not in entry:
            return jsonify({"status": "ok"}), 200

        message = entry["messages"][0]
        sender = message["from"]
        msg_type = message["type"]

        if msg_type == "text":
            text = message["text"]["body"].strip()
            handle_text_message(sender, text)

        elif msg_type == "image":
            handle_image_message(sender, message["image"]["id"])

        elif msg_type == "audio":
            handle_audio_message(sender, message["audio"]["id"])

    except (KeyError, IndexError) as e:
        print(f"[Webhook] Parse error: {e}")

    return jsonify({"status": "ok"}), 200


# ─── Menu System ───────────────────────────────────────────────────────────────

MAIN_MENU = """🙏 *Welcome to NanaGPT — SeniorCare AI!*

Please choose an option by replying with the number:

1️⃣ - 💊 Medicine Reminder
2️⃣ - 📋 Explain Prescription
3️⃣ - ❓ Health Question
4️⃣ - 📅 My Reminders
5️⃣ - 🚨 Emergency Alert
6️⃣ - 🌡️ Daily Health Check-in

_Reply 0 anytime to return to this menu_"""

MENU_PROMPTS = {
    "1": "💊 *Medicine Reminder*\n\nTell me the medicine and time.\nExample: _Remind me to take Crocin at 9 PM daily_",
    "2": "📋 *Prescription Explanation*\n\nPlease *send a photo* of your prescription.\nAlso tell me your language (Hindi/Marathi/English).",
    "3": "❓ *Health Question*\n\nGo ahead, type your health question.\nExample: _What is Metformin used for?_",
    "4": None,  # handled separately
    "5": "🚨 *Emergency Alert*\n\nDescribe your emergency symptom right now.\nExample: _I have chest pain_\n\n⚠️ Your caregiver will be alerted immediately.",
    "6": "🌡️ *Daily Check-in*\n\nHow are you feeling today?\nReply with: Good 😊 / Not well 😔 / or describe your symptoms."
}

def send_main_menu(sender: str):
    send_text(sender, MAIN_MENU)
    upsert_user(sender, {"phone": sender, "state": "menu"})


def handle_text_message(sender: str, text: str):
    print(f"[MSG] {sender}: {text}")

    # Ensure user exists
    user = get_user(sender)
    if not user:
        upsert_user(sender, {"phone": sender, "state": "menu"})
        send_main_menu(sender)
        return

    current_state = user.get("state", "menu")
    text_lower = text.lower()

    # Always return to menu on 0 or hi/hello
    if text in ["0"] or text_lower in ["hi", "hello", "hey", "menu", 
                                        "नमस्ते", "हेलो", "नमस्कार"]:
        send_main_menu(sender)
        return

    # ── Handle menu selection ──────────────────────────────────────────────
    if current_state == "menu" or text in ["1","2","3","4","5","6"]:

        if text == "1":
            upsert_user(sender, {"state": "reminder"})
            send_text(sender, MENU_PROMPTS["1"])

        elif text == "2":
            upsert_user(sender, {"state": "prescription"})
            send_text(sender, MENU_PROMPTS["2"])

        elif text == "3":
            upsert_user(sender, {"state": "health_question"})
            send_text(sender, MENU_PROMPTS["3"])

        elif text == "4":
            show_reminders(sender)

        elif text == "5":
            upsert_user(sender, {"state": "emergency"})
            send_text(sender, MENU_PROMPTS["5"])

        elif text == "6":
            upsert_user(sender, {"state": "checkin"})
            send_text(sender, MENU_PROMPTS["6"])

        else:
            # Unknown input while in menu
            send_text(sender, "Please reply with a number 1-6 to choose an option, or type *Hi* to see the menu again.")

        return

    # ── Handle state-based responses ──────────────────────────────────────

    if current_state == "reminder":
        handle_reminder_input(sender, text)

    elif current_state == "health_question":
        handle_health_question(sender, text)

    elif current_state == "emergency":
        handle_emergency_input(sender, text, user)

    elif current_state == "checkin":
        handle_checkin_input(sender, text)

    elif current_state == "prescription":
        # They typed language preference instead of sending image
        upsert_user(sender, {"preferred_language": text})
        send_text(sender, f"Got it! Language set to *{text}*. Now please send your prescription photo 📸")

    else:
        send_main_menu(sender)


# ─── State Handlers ────────────────────────────────────────────────────────────

def handle_reminder_input(sender: str, text: str):
    history = get_recent_history(sender)
    result = chat_with_asi(
        f"User wants to set a medicine reminder: '{text}'. "
        f"Extract medicine name, time (HH:MM 24hr), frequency. "
        f"Output a <REMINDER> JSON tag and confirm in simple language.",
        history
    )
    add_message_to_history(sender, "user", text)
    add_message_to_history(sender, "assistant", result["reply"])

    if result["reminder"]:
        save_reminder(sender, result["reminder"])

    send_text(sender, result["reply"])
    send_text(sender, "\n_Reply 0 to go back to menu_")
    upsert_user(sender, {"state": "reminder"})  # stay in reminder state for more


def handle_health_question(sender: str, text: str):
    history = get_recent_history(sender)
    result = chat_with_asi(text, history)
    add_message_to_history(sender, "user", text)
    add_message_to_history(sender, "assistant", result["reply"])

    if result["is_emergency"]:
        trigger_emergency(sender, text, get_user(sender))
        return

    send_text(sender, result["reply"])
    send_text(sender, "_Ask another question or reply 0 for menu_")


def handle_emergency_input(sender: str, text: str, user: dict):
    trigger_emergency(sender, text, user)


def trigger_emergency(sender: str, symptom: str, user: dict):
    name = user.get("name", "Senior User")
    if CAREGIVER_PHONE:
        send_emergency_alert(CAREGIVER_PHONE, name, sender, symptom)
    send_text(sender,
        "🚨 *EMERGENCY ALERT SENT*\n\n"
        "Your caregiver has been notified immediately.\n"
        "Please call *112* if this is life-threatening.\n\n"
        "Stay calm. Help is on the way. 🙏"
    )
    upsert_user(sender, {"state": "menu"})


def handle_checkin_input(sender: str, text: str):
    log_health_checkin(sender, text)
    result = chat_with_asi(
        f"User daily health check-in response: '{text}'. "
        f"Respond warmly and give simple advice if needed.",
        []
    )
    send_text(sender, result["reply"])
    send_text(sender, "_Reply 0 to go back to menu_")
    upsert_user(sender, {"state": "menu"})


def show_reminders(sender: str):
    from firebase_handler import get_active_reminders
    reminders = get_active_reminders(sender)
    if reminders:
        msg = "📅 *Your Active Reminders:*\n\n"
        for r in reminders:
            msg += f"💊 {r.get('medicine')} at {r.get('time')} ({r.get('frequency', 'daily')})\n"
        msg += "\n_Reply 0 to go back to menu_"
    else:
        msg = "No reminders set yet.\n\nReply *1* to set a medicine reminder."
    send_text(sender, msg)
    upsert_user(sender, {"state": "menu"})


def handle_image_message(sender: str, media_id: str):
    user = get_user(sender)
    # Check if user is in prescription state
    if user.get("state") != "prescription":
        send_text(sender, "📋 I see you sent an image! To explain a prescription, reply *2* from the menu first.")
        return

    send_text(sender, "📋 Processing your prescription... please wait ⏳")
    lang = user.get("preferred_language", "Hindi")
    media_url = get_media_url(media_id)
    explanation = explain_prescription(media_url, language=lang)
    send_text(sender, f"📋 *Prescription ({lang}):*\n\n{explanation}")
    send_text(sender, "_Reply 0 to go back to menu_")
    upsert_user(sender, {"state": "menu"})


def handle_audio_message(sender: str, media_id: str):
    send_text(sender, "🎤 Processing voice message... ⏳")
    media_url = get_media_url(media_id)
    audio_bytes = download_media(media_url)

    try:
        import io
        from openai import OpenAI
        asi_client = OpenAI(
            api_key=os.getenv("ASI_API_KEY"),
            base_url=os.getenv("ASI_BASE_URL")
        )
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "voice.ogg"
        transcript = asi_client.audio.transcriptions.create(
            model="whisper-1", file=audio_file, language="hi"
        )
        send_text(sender, f"🎤 I heard: _{transcript.text}_\n")
        handle_text_message(sender, transcript.text)
    except Exception as e:
        print(f"[Audio] Error: {e}")
        send_text(sender, "Sorry, couldn't process voice. Please type your message. 🙏")


# ─── Health Check ──────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "SeniorCare AI running ✅"}), 200


if __name__ == "__main__":
    start_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=True)