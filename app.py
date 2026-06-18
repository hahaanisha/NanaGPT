import os
import json
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from asi_handler import chat_with_asi, explain_prescription
from whatsapp import send_text, get_media_url, download_media
from firebase_handler import (
    get_user, upsert_user, init_db,
    add_message_to_history, get_recent_history,
    save_reminder, get_active_reminders, delete_reminder,
    save_health_log, get_health_logs
)
from reminder_scheduler import start_scheduler

load_dotenv()
init_db()

app = Flask(__name__)
VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN")

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
    print(f"[Webhook] {json.dumps(data)}")
    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" not in entry:
            return jsonify({"status": "ok"}), 200
        message = entry["messages"][0]
        sender = message["from"]
        msg_type = message["type"]

        if msg_type == "text":
            handle_text_message(sender, message["text"]["body"].strip())
        elif msg_type == "image":
            handle_image_message(sender, message["image"]["id"])
        elif msg_type == "audio":
            handle_audio_message(sender, message["audio"]["id"])

    except (KeyError, IndexError) as e:
        print(f"[Error] {e}")
    return jsonify({"status": "ok"}), 200

# ─── Menus ─────────────────────────────────────────────────────────────────────

def send_main_menu(sender: str):
    msg = (
        "🏥 *NanaGPT — Main Menu*\n\n"
        "1️⃣ - 💊 Set Medicine Reminder\n"
        "2️⃣ - 📅 View My Reminders\n"
        "3️⃣ - 📋 Read Prescription\n"
        "4️⃣ - ❓ Ask Health Question\n"
        "5️⃣ - 📊 Log Health Reading\n"
        "6️⃣ - 📈 View Health History\n"
        "7️⃣ - 🌐 Change Language\n\n"
        "_Reply with a number to choose_"
    )
    send_text(sender, msg)
    upsert_user(sender, {"state": "menu"})

# ─── Onboarding ────────────────────────────────────────────────────────────────

ONBOARDING_STEPS = ["name", "age", "conditions", "medicines", "prescription_image"]

def start_onboarding(sender: str):
    upsert_user(sender, {"phone": sender, "state": "onboard_name", "language": "English"})
    send_text(sender,
        "🙏 *Welcome to NanaGPT!*\n\n"
        "I am your personal health assistant.\n"
        "Let me set up your profile first.\n\n"
        "👤 What is your *name*?"
    )

def handle_onboarding(sender: str, text: str, user: dict):
    state = user.get("state", "")

    if state == "onboard_name":
        upsert_user(sender, {"name": text, "state": "onboard_age"})
        send_text(sender, f"Nice to meet you, *{text}*! 😊\n\n🔢 What is your *age*?")

    elif state == "onboard_age":
        upsert_user(sender, {"age": text, "state": "onboard_conditions"})
        send_text(sender,
            "🏥 Do you have any known health conditions?\n\n"
            "Example: _Diabetes, High BP, Thyroid_\n\n"
            "Or type *None* if not applicable."
        )

    elif state == "onboard_conditions":
        upsert_user(sender, {"conditions": text, "state": "onboard_medicines"})
        send_text(sender,
            "💊 What medicines are you currently taking?\n\n"
            "Example: _Metformin 500mg, Amlodipine 5mg_\n\n"
            "Or type *None* if not applicable."
        )

    elif state == "onboard_medicines":
        upsert_user(sender, {"medicines": text, "state": "onboard_prescription"})
        send_text(sender,
            "📋 Please send a *photo of your prescription* so I can store it.\n\n"
            "Or type *Skip* to continue without it."
        )

    elif state == "onboard_prescription":
        if text.lower() == "skip":
            finish_onboarding(sender)
        else:
            send_text(sender, "Please send the prescription as a *photo/image*, or type *Skip*.")

def handle_onboarding_image(sender: str, media_id: str):
    user = get_user(sender)
    if user.get("state") == "onboard_prescription":
        media_url = get_media_url(media_id)
        upsert_user(sender, {"prescription_url": media_url})
        finish_onboarding(sender)

def finish_onboarding(sender: str):
    user = get_user(sender)
    upsert_user(sender, {"state": "menu", "onboarded": True})
    send_text(sender,
        f"✅ *Profile saved!*\n\n"
        f"👤 Name: {user.get('name')}\n"
        f"🔢 Age: {user.get('age')}\n"
        f"🏥 Conditions: {user.get('conditions', 'None')}\n"
        f"💊 Medicines: {user.get('medicines', 'None')}\n\n"
        f"You're all set! Here's what I can do for you:"
    )
    send_main_menu(sender)

# ─── Main Message Router ───────────────────────────────────────────────────────

def handle_text_message(sender: str, text: str):
    print(f"[MSG] {sender}: {text}")
    user = get_user(sender)

    # New user — start onboarding
    if not user or not user.get("onboarded"):
        if not user:
            start_onboarding(sender)
        else:
            handle_onboarding(sender, text, user)
        return

    state = user.get("state", "menu")
    text_lower = text.lower()

    # Global: return to menu
    if text in ["0"] or text_lower in ["hi", "hello", "menu", "back",
                                        "नमस्ते", "हेलो", "नमस्कार"]:
        send_main_menu(sender)
        return

    # Global: medicine taken confirmation
    if text_lower in ["done", "taken", "हो गया", "घेतली", "ले लिया"]:
        send_text(sender, "✅ Great! Medicine logged. Stay healthy! 💪\n\n_Reply 0 for menu_")
        return

    # Menu selection
    if state == "menu" or text in ["1","2","3","4","5","6","7"]:
        handle_menu_selection(sender, text, user)
        return

    # State-based routing
    state_handlers = {
        "reminder":       handle_reminder_input,
        "health_question": handle_health_question,
        "health_log":     handle_health_log_input,
        "language":       handle_language_input,
        "delete_reminder": handle_delete_reminder,
    }
    handler = state_handlers.get(state)
    if handler:
        handler(sender, text, user)
    else:
        send_main_menu(sender)

def handle_menu_selection(sender: str, text: str, user: dict):
    if text == "1":
        upsert_user(sender, {"state": "reminder"})
        send_text(sender,
            "💊 *Set Medicine Reminder*\n\n"
            "Tell me the medicine name and time.\n\n"
            "Example: _Take Crocin at 9 PM daily_\n\n"
            "_Reply 0 to go back_"
        )
    elif text == "2":
        show_reminders(sender)

    elif text == "3":
        upsert_user(sender, {"state": "prescription"})
        lang = user.get("language", "English")
        send_text(sender,
            f"📋 *Read Prescription*\n\n"
            f"Please send a *photo* of your prescription.\n"
            f"I will explain it in *{lang}*.\n\n"
            f"_(Language can be changed via option 7)_\n\n"
            f"_Reply 0 to go back_"
        )
    elif text == "4":
        upsert_user(sender, {"state": "health_question"})
        send_text(sender,
            "❓ *Ask a Health Question*\n\n"
            "Type your question below.\n\n"
            "Example: _What is Metformin used for?_\n"
            "Example: _Can I take Crocin with Metformin?_\n\n"
            "_Reply 0 to go back_"
        )
    elif text == "5":
        upsert_user(sender, {"state": "health_log"})
        send_text(sender,
            "📊 *Log Health Reading*\n\n"
            "Tell me your reading. Examples:\n\n"
            "• _My BP is 130/85_\n"
            "• _Blood sugar is 140_\n"
            "• _Weight is 68 kg_\n\n"
            "_Reply 0 to go back_"
        )
    elif text == "6":
        show_health_history(sender)

    elif text == "7":
        upsert_user(sender, {"state": "language"})
        send_text(sender,
            "🌐 *Change Language*\n\n"
            "Which language do you prefer?\n\n"
            "1 - English\n"
            "2 - Hindi (हिंदी)\n"
            "3 - Marathi (मराठी)\n"
            "4 - Gujarati (ગુજરાતી)\n"
            "5 - Tamil (தமிழ்)\n\n"
            "_Reply with number_"
        )
    else:
        send_text(sender, "Please reply with a number 1-7, or type *Hi* to see the menu.")

# ─── Feature Handlers ──────────────────────────────────────────────────────────

def handle_reminder_input(sender: str, text: str, user: dict):
    history = get_recent_history(sender)
    result = chat_with_asi(
        f"Set a medicine reminder: '{text}'. "
        f"Extract medicine, time in HH:MM 24hr, frequency. "
        f"Output <REMINDER> tag and confirm briefly.",
        user, history
    )
    add_message_to_history(sender, "user", text)
    add_message_to_history(sender, "assistant", result["reply"])

    if result["reminder"]:
        r = result["reminder"]
        saved = save_reminder(
            sender,
            r.get("medicine", "Medicine"),
            r.get("time", ""),
            r.get("frequency", "daily")
        )
        if saved:
            send_text(sender,
                f"✅ *Reminder Set!*\n\n"
                f"💊 Medicine: *{r.get('medicine')}*\n"
                f"⏰ Time: *{r.get('time')}*\n"
                f"🔁 Frequency: *{r.get('frequency', 'daily')}*\n\n"
                f"_Reply 0 for menu or set another reminder_"
            )
        else:
            send_text(sender,
                f"⚠️ A reminder for *{r.get('medicine')}* at *{r.get('time')}* already exists!\n\n"
                f"_Reply 0 for menu_"
            )
    else:
        send_text(sender, result["reply"] + "\n\n_Reply 0 for menu_")


def show_reminders(sender: str):
    reminders = get_active_reminders(sender)
    if reminders:
        msg = "📅 *Your Active Reminders:*\n\n"
        for i, r in enumerate(reminders, 1):
            msg += f"{i}. 💊 *{r['medicine']}* at {r['time']} ({r['frequency']})\n"
        msg += "\nTo delete, type: _delete [medicine name]_\n_Reply 0 for menu_"
    else:
        msg = "No reminders set yet.\n\nReply *1* to set a medicine reminder."
    send_text(sender, msg)
    upsert_user(sender, {"state": "delete_reminder"})


def handle_delete_reminder(sender: str, text: str, user: dict):
    if text.lower().startswith("delete "):
        medicine = text[7:].strip()
        delete_reminder(sender, medicine)
        send_text(sender, f"🗑️ Reminder for *{medicine}* deleted.\n\n_Reply 0 for menu_")
    else:
        send_main_menu(sender)


def handle_health_question(sender: str, text: str, user: dict):
    history = get_recent_history(sender)
    result = chat_with_asi(text, user, history)
    add_message_to_history(sender, "user", text)
    add_message_to_history(sender, "assistant", result["reply"])
    send_text(sender, result["reply"] + "\n\n_Ask another or reply 0 for menu_")


def handle_health_log_input(sender: str, text: str, user: dict):
    result = chat_with_asi(
        f"User logged a health reading: '{text}'. "
        f"Extract type (BP/Sugar/Weight/Other) and value. "
        f"Output <HEALTHLOG> tag and confirm briefly.",
        user, []
    )
    if result["health_log"]:
        hl = result["health_log"]
        save_health_log(sender, hl.get("type", "Other"), hl.get("value", text))
        send_text(sender,
            f"📊 *Reading Saved!*\n\n"
            f"Type: *{hl.get('type')}*\n"
            f"Value: *{hl.get('value')}*\n\n"
            f"_Log another or reply 0 for menu_"
        )
    else:
        send_text(sender, result["reply"] + "\n\n_Reply 0 for menu_")


def show_health_history(sender: str):
    logs = get_health_logs(sender, limit=10)
    if logs:
        msg = "📈 *Recent Health Readings:*\n\n"
        for log in logs:
            date = log["timestamp"][:10]
            msg += f"• {log['type']}: *{log['value']}* ({date})\n"
        msg += "\n_Reply 0 for menu_"
    else:
        msg = "No health readings logged yet.\n\nReply *5* to log a reading."
    send_text(sender, msg)
    upsert_user(sender, {"state": "menu"})


def handle_language_input(sender: str, text: str, user: dict):
    lang_map = {
        "1": "English", "2": "Hindi", "3": "Marathi",
        "4": "Gujarati", "5": "Tamil"
    }
    lang = lang_map.get(text)
    if lang:
        upsert_user(sender, {"language": lang, "state": "menu"})
        send_text(sender, f"✅ Language changed to *{lang}*!\n\n_Reply 0 for menu_")
    else:
        send_text(sender, "Please reply with a number 1-5 to choose your language.")


def handle_image_message(sender: str, media_id: str):
    user = get_user(sender)
    if not user or not user.get("onboarded"):
        handle_onboarding_image(sender, media_id)
        return

    state = user.get("state", "")
    if state != "prescription":
        send_text(sender,
            "I see you sent an image!\n\n"
            "To read a prescription, reply *3* from the menu.\n\n"
            "_Reply 0 for menu_"
        )
        return

    send_text(sender, "📋 Reading your prescription... ⏳")
    lang = user.get("language", "English")
    media_url = get_media_url(media_id)

    try:
        explanation = explain_prescription(media_url, lang, user)
        send_text(sender, f"📋 *Prescription ({lang}):*\n\n{explanation}\n\n_Reply 0 for menu_")
    except Exception as e:
        print(f"[Prescription Error] {e}")
        send_text(sender, "Sorry, I couldn't read the prescription. Please try a clearer photo. 🙏")

    upsert_user(sender, {"state": "menu"})


def handle_audio_message(sender: str, media_id: str):
    user = get_user(sender)
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
        print(f"[Audio Error] {e}")
        send_text(sender, "Sorry, couldn't process voice message. Please type instead. 🙏")


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "SeniorCare AI running ✅"}), 200


if __name__ == "__main__":
    start_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=True)