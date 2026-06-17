import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ASI:ONE is OpenAI-compatible — just swap base_url and api_key
client = OpenAI(
    api_key=os.getenv("ASI_API_KEY"),
    base_url=os.getenv("ASI_BASE_URL"),
)
MODEL = os.getenv("ASI_MODEL", "asi1-mini")

SYSTEM_PROMPT = """You are SeniorCare AI, a compassionate health assistant for elderly people on WhatsApp.
Rules:
- Always reply in the SAME language the user writes in (Hindi, Marathi, English, etc.)
- Keep responses SHORT and SIMPLE (max 3-4 sentences) — users are elderly
- For medical questions, always add: "Please consult your doctor for personal advice."
- For emergencies (chest pain, breathlessness, severe pain), reply with EMERGENCY flag first
- When explaining medicines: name → purpose → dosage tip → precaution
- For reminders, extract: medicine name, time, frequency — output as JSON inside <REMINDER> tags
- Never diagnose. Only explain and guide.
"""

def chat_with_asi(user_message: str, history: list = None) -> dict:
    """
    Send message to ASI:ONE and get response.
    Returns dict with 'reply', 'is_emergency', 'reminder' keys.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add conversation history for context
    if history:
        messages.extend(history[-6:])  # last 3 exchanges
    
    messages.append({"role": "user", "content": user_message})
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=500,
        temperature=0.4,
    )
    
    reply_text = response.choices[0].message.content.strip()
    
    # Parse special flags from ASI response
    is_emergency = detect_emergency(user_message, reply_text)
    reminder = extract_reminder(reply_text)
    
    # Clean reply (remove JSON tags before sending to user)
    clean_reply = reply_text
    if "<REMINDER>" in reply_text:
        clean_reply = reply_text[:reply_text.find("<REMINDER>")].strip()
        clean_reply += "\n✅ Reminder set!"
    
    return {
        "reply": clean_reply,
        "is_emergency": is_emergency,
        "reminder": reminder,
        "raw": reply_text
    }


def explain_prescription(image_url: str, language: str = "English") -> str:
    """
    Send prescription image to ASI:ONE for explanation.
    ASI:ONE supports vision via image_url.
    """
    prompt = f"""This is a prescription image. Please:
1. List each medicine name
2. Explain what it's used for (simple terms)
3. Note the dosage
4. Any important precautions

Reply entirely in {language}. Keep it simple for an elderly person."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        max_tokens=800,
    )
    return response.choices[0].message.content.strip()


def transcribe_and_respond(audio_text: str) -> dict:
    """Handle voice messages (after transcription)."""
    return chat_with_asi(f"[Voice message]: {audio_text}")


def detect_emergency(user_msg: str, ai_reply: str) -> bool:
    """Detect emergency keywords."""
    emergency_keywords = [
        "chest pain", "heart attack", "can't breathe", "unconscious",
        "stroke", "severe pain", "bleeding", "fallen", "not moving",
        "सीने में दर्द", "दिल का दौरा", "सांस नहीं", "बेहोश",
        "छाती दुखतंय", "श्वास घेता येत नाही"
    ]
    text = (user_msg + ai_reply).lower()
    return any(kw in text for kw in emergency_keywords)


def extract_reminder(reply_text: str) -> dict | None:
    """Extract structured reminder from ASI response if present."""
    import json, re
    match = re.search(r'<REMINDER>(.*?)</REMINDER>', reply_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except:
            return None
    return None