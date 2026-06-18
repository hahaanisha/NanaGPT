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
    if conditions and conditions.lower() != "none":
        context += f"Known conditions: {conditions}. "
    if medicines and medicines.lower() != "none":
        context += f"Current medicines: {medicines}. "

    return f"""You are NanaGPT, a compassionate health assistant for elderly people on WhatsApp.
{context}

CRITICAL INSTRUCTION — LANGUAGE:
You MUST reply ONLY in {lang}.
Do NOT use English if the language is not English.
Do NOT mix languages.
Every single word of your response must be in {lang}.
If {lang} is Hindi, write in Devanagari script (हिंदी).
If {lang} is Marathi, write in Devanagari script (मराठी).
If {lang} is Gujarati, write in Gujarati script (ગુજરાતી).
If {lang} is Tamil, write in Tamil script (தமிழ்).

Other rules:
- Keep responses SHORT and SIMPLE — max 4 sentences — users are elderly
- For medical questions always end with: consult your doctor for personal advice
- Never diagnose. Only explain and guide.
- For reminders, extract medicine name, time in HH:MM 24hr format, frequency
  and output as JSON inside <REMINDER> tags like:
  <REMINDER>{{"medicine":"Crocin","time":"21:00","frequency":"daily"}}</REMINDER>
- For health logs (BP, sugar, weight), extract type and value and output inside <HEALTHLOG> tags like:
  <HEALTHLOG>{{"type":"BP","value":"140/90"}}</HEALTHLOG>
- Never output both tags in one response
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

    # Strip tags from user-facing reply
    clean_reply = re.sub(r'<REMINDER>.*?</REMINDER>', '', reply_text, flags=re.DOTALL).strip()
    clean_reply = re.sub(r'<HEALTHLOG>.*?</HEALTHLOG>', '', clean_reply, flags=re.DOTALL).strip()

    return {
        "reply": clean_reply,
        "reminder": reminder,
        "health_log": health_log,
    }


def explain_prescription(image_b64: str, language: str, user: dict) -> str:
    conditions = user.get("conditions", "")
    context = (
        f"Note: Patient has {conditions}."
        if conditions and conditions.lower() != "none"
        else ""
    )

    prompt = f"""This is a prescription image. {context}
Please explain:
1. Each medicine name
2. What it is used for (simple words)
3. Dosage instructions
4. Important precautions

IMPORTANT: Reply entirely in {language} only. 
Every single word must be in {language}.
Keep it very simple for an elderly person."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": build_system_prompt(user)},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}"
                        }
                    },
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