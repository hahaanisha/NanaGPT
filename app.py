import os
import json
import base64
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from asi_handler import chat_with_asi, explain_prescription, detect_emergency
from whatsapp import send_text, send_emergency_alert, get_media_url, download_media
from firebase_handler import (get_user, upsert_user, add_message_to_history,
                               get_recent_history, save_reminder, log_health_checkin)
from reminder_scheduler import start_scheduler

load_dotenv()

app = Flask(__name__)
VERIFY_TOKEN = os.getenv("WEBHOOK_VERIFY_TOKEN")
CAREGIVER_PHONE = os.getenv("CAREGIVER_PHONE")


# ─── Webhook Verification (GET) ────────────────────────────────────────────────
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("[Webhook] Verified ✅")
        return challenge, 200
    return "Forbidden", 403


# ─── Incoming Messages (POST) ──────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def handle_webhook():
    data = request.get_json()
    
    try:
        entry = data["entry"][0]["changes"][0]["value"]
        
        # Ignore status updates (delivered, read, etc.)
        if "messages" not in entry:
            return jsonify({"status": "ok"}), 200
        
        message = entry["messages"][0]
        sender = message["from"]          # e.g. "919876543210"
        msg_type = message["type"]        # text / image / audio
        
        # Ensure user exists in DB
        user = get_user(sender)
        if not user:
            upsert_user(sender, {"phone": sender, "joined": True})
            send_text(sender, 
                "🙏 *Welcome to SeniorCare AI!*\n\n"
                "I'm here to help you with:\n"
                "• 💊 Medicine reminders\n"
                "• 📋 Prescription explanations\n"
                "• 🏥 Health questions\n"
                "• 🚨 Emergency alerts\n\n"
                "Just type your question in Hindi, Marathi, or English!"
            )
            return jsonify({"status": "ok"}), 200
        
        # Route by message type
        if msg_type == "text":
            handle_text_message(sender, message["text"]["body"])
            
        elif msg_type == "image":
            handle_image_message(sender, message["image"]["id"])
            
        elif msg_type == "audio":
            # WhatsApp sends voice notes as audio
            handle_audio_message(sender, message["audio"]["id"])
            
    except (KeyError, IndexError) as e:
        print(f"[Webhook] Parse error: {e}")
    
    return jsonify({"status": "ok"}), 200


# ─── Message Handlers ──────────────────────────────────────────────────────────

def handle_text_message(sender: str, text: str):
    """Process text messages through ASI:ONE."""
    print(f"[MSG] {sender}: {text}")
    
    # Special commands
    if text.strip().lower() in ["done", "taken", "हो गया", "घेतली"]:
        send_text(sender, "✅ Great! Medicine logged. Stay healthy! 💪")
        return
    
    if text.strip().lower() in ["reminders", "my reminders", "मेरी दवाइयाँ"]:
        from firebase_handler import get_active_reminders
        reminders = get_active_reminders(sender)
        if reminders:
            msg = "📋 *Your Active Reminders:*\n\n"
            for r in reminders:
                msg += f"💊 {r.get('medicine')} at {r.get('time')} ({r.get('frequency', 'daily')})\n"
        else:
            msg = "No reminders set yet. Tell me: 'Remind me to take Crocin at 8 PM daily'"
        send_text(sender, msg)
        return
    
    # Get conversation history for context
    history = get_recent_history(sender)
    
    # Query ASI:ONE
    result = chat_with_asi(text, history)
    
    # Save to history
    add_message_to_history(sender, "user", text)
    add_message_to_history(sender, "assistant", result["reply"])
    
    # Save reminder if ASI detected one
    if result["reminder"]:
        save_reminder(sender, result["reminder"])
    
    # Handle emergency
    if result["is_emergency"]:
        user = get_user(sender)
        name = user.get("name", "Unknown User")
        send_emergency_alert(CAREGIVER_PHONE, name, sender, text)
        reply = (
            f"🚨 *EMERGENCY DETECTED*\n\n"
            f"{result['reply']}\n\n"
            f"⚠️ Your caregiver has been *alerted immediately*.\n"
            f"Please call *112* if this is life-threatening."
        )
        send_text(sender, reply)
        return
    
    # Log health check-in responses
    if any(w in text.lower() for w in ["not well", "pain", "fever", "sick", 
                                         "बीमार", "दर्द", "आजारी"]):
        log_health_checkin(sender, text)
    
    send_text(sender, result["reply"])


def handle_image_message(sender: str, media_id: str):
    """Handle prescription image uploads."""
    send_text(sender, "📋 Processing your prescription... please wait ⏳")
    
    # Get media URL from WhatsApp
    media_url = get_media_url(media_id)
    
    # Ask ASI:ONE to detect preferred language from user history
    user = get_user(sender)
    lang = user.get("preferred_language", "Hindi")
    
    # Explain prescription via ASI:ONE vision
    explanation = explain_prescription(media_url, language=lang)
    
    send_text(sender, f"📋 *Prescription Explanation ({lang}):*\n\n{explanation}")
    add_message_to_history(sender, "user", "[Uploaded prescription image]")
    add_message_to_history(sender, "assistant", explanation)


def handle_audio_message(sender: str, media_id: str):
    """Handle voice notes — download, transcribe via ASI, respond."""
    send_text(sender, "🎤 Processing your voice message... ⏳")
    
    # Download audio from WhatsApp
    media_url = get_media_url(media_id)
    audio_bytes = download_media(media_url)
    
    # Use ASI:ONE Whisper-compatible transcription
    # ASI:ONE supports audio transcription endpoint
    try:
        import io
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "voice.ogg"
        
        from openai import OpenAI
        asi_client = OpenAI(
            api_key=os.getenv("ASI_API_KEY"),
            base_url=os.getenv("ASI_BASE_URL")
        )
        transcript = asi_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="hi"  # hint: Hindi/Indian languages
        )
        transcribed_text = transcript.text
        send_text(sender, f"🎤 I heard: _{transcribed_text}_\n")
        handle_text_message(sender, transcribed_text)
        
    except Exception as e:
        print(f"[Audio] Transcription error: {e}")
        send_text(sender, 
            "Sorry, I couldn't process the voice message. "
            "Please type your question instead. 🙏"
        )


# ─── Health Check ──────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "SeniorCare AI running ✅"}), 200


# ─── Start ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    start_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=True)