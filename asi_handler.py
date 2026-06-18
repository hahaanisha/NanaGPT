import os
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.getenv("ASI_API_KEY"),
    base_url=os.getenv("ASI_BASE_URL"),
)
MODEL = os.getenv("ASI_MODEL", "asi1-mini")

def build_system_prompt(user: dict) -> str:
    lang = user.get("language", "English")
    name = user.get("name", "")
    conditions = user.get("conditions", "")
    medicines = user.get("medicines", "")

    context = ""
    if name:
        context += f"User's name: {name}. "
    if conditions:
        context += f"Known conditions: {conditions}. "
    if medicines:
        context += f"Current medicines: {medicines}. "

    return f"""You are NanaGPT, a compassionate health assistant for elderly people on WhatsApp.
{context}

Rules:
- Always reply in {lang}
- Keep responses SHORT and SIMPLE — users are elderly
- For medical questions always add: consult your doctor for personal advice
- Never diagnose. Only explain and guide.
- For reminders, extract medicine name, time (HH:MM 24hr format), frequency
  and output as JSON inside <REMINDER> tags like:
  <REMINDER>{{"medicine":"Crocin","time":"21:00","frequency":"daily"}}</REMINDER>
- For health logs (BP, sugar), extract type and value and output inside <HEALTHLOG> tags like:
  <HEALTHLOG>{{"type":"BP","value":"140/90"}}</HEALTHLOG>
"""

def chat_with_asi(user_message: str, user: dict, history: list = None) -> dict:
    messages = [{"role": "system", "content": build_system_prompt(user)}]
    if history:
        messages.extend(history[-6:])
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=500,
        temperature=0.4,
    )
    reply_text = response.choices[0].message.content.strip()

    reminder = extract_tag(reply_text, "REMINDER")
    health_log = extract_tag(reply_text, "HEALTHLOG")

    # Clean tags from reply
    clean_reply = re.sub(r'<REMINDER>.*?</REMINDER>', '', reply_text, flags=re.DOTALL).strip()
    clean_reply = re.sub(r'<HEALTHLOG>.*?</HEALTHLOG>', '', clean_reply, flags=re.DOTALL).strip()

    return {
        "reply": clean_reply,
        "reminder": reminder,
        "health_log": health_log,
    }

def explain_prescription(image_url: str, language: str, user: dict) -> str:
    conditions = user.get("conditions", "")
    context = f"Note: Patient has {conditions}." if conditions else ""

    prompt = f"""This is a prescription image. {context}
Please:
1. List each medicine name
2. Explain what it is used for in simple words
3. Note the dosage
4. Any important precautions

Reply entirely in {language}. Keep it very simple for an elderly person."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": build_system_prompt(user)},
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

def extract_tag(text: str, tag: str):
    match = re.search(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except:
            return None
    return None