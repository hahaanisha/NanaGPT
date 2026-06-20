<p align="center">
  <img src="readme_img/hero.png" alt="ContextBridge Hero" width="1000" />
</p>

# NanaGPT: WhatsApp Health Companion for Elderly Care

A WhatsApp-based AI health assistant for senior citizens, powered by ASI:ONE. No app to install. No new interface to learn. Just WhatsApp.

---

## Overview

NanaGPT helps elderly individuals manage their daily healthcare through simple WhatsApp messages. It handles medicine reminders with automatic follow-ups, prescription explanations, health question answering, and health log tracking — all in the user's preferred Indian language.

---

## Features

| Feature | Description |
|---|---|
| Onboarding Profile | Collects name, age, conditions, medicines, and prescription image on first use |
| Medicine Reminders | Natural language input → structured reminder → automatic WhatsApp delivery |
| Follow-Up Nudges | If "done" isn't received, sends up to 2 escalating follow-ups at 10-minute intervals |
| Prescription Reader | Photo of prescription → plain-language explanation in user's language |
| Health Q&A | Ask any health question, answered with awareness of user's medical profile |
| Health Log | Log BP, blood sugar, weight — stored with timestamps, viewable as history |
| Multilingual | English, Hindi, Marathi, Gujarati, Tamil — changeable anytime |

---

## Architecture

```
WhatsApp User
     |
     v
Meta WABA Webhook  (POST /webhook)
     |
     v
Flask App  (Render)
     |
     ├── State Machine  (onboarding / menu / reminder / prescription / ...)
     ├── ASI:ONE API    (language understanding, vision, multilingual replies)
     ├── PostgreSQL (Supabase) (user profiles, reminders, health logs, chat history)
     └── APScheduler    (reminder delivery + follow-up nudges, checked every minute)

UptimeRobot pings the deployed URL every 5 minutes to keep the Render free
instance awake, since the scheduler only runs while the instance is alive.
```

---

## Tech Stack

- **AI** — [ASI:ONE](https://asi1.ai) (`asi1-mini`)
- **Backend** — Python, Flask
- **Database** — PostgreSQL, hosted on [Supabase](https://supabase.com) (free tier)
- **Scheduler** — APScheduler
- **WhatsApp** — Meta WhatsApp Business API (WABA)
- **Hosting** — [Render](https://render.com) (free tier)
- **Uptime Monitoring** — [UptimeRobot](https://uptimerobot.com) (free tier)

---

## How ASI:ONE Is Used

ASI:ONE is the core intelligence layer. It is accessed via an OpenAI-compatible API, integrated using the standard Python `openai` SDK with a custom `base_url`.

- **Personalized responses** — Every API call includes a dynamically built system prompt with the user's name, known conditions, and current medicines. Responses are contextual, not generic.

- **Multilingual output** — The system prompt instructs ASI:ONE to respond in the user's selected language and correct script (Devanagari for Hindi/Marathi, Gujarati script, Tamil script), with explicit, repeated enforcement to prevent fallback to English.

- **Structured data extraction** — ASI:ONE embeds structured JSON inside custom tags in its response:
```
<REMINDER>{"medicine":"Metformin","time":"08:00","frequency":"daily"}</REMINDER>
<HEALTHLOG>{"type":"BP","value":"130/85"}</HEALTHLOG>
```
These are parsed by the app and written to the database. The tags are stripped before the reply reaches the user.

- **Prescription image analysis** — Prescription photos are downloaded from WhatsApp, converted to base64, and sent to ASI:ONE as vision input via a data URI (not a direct URL, since WhatsApp media links expire within minutes). The model returns a structured explanation in the user's language.

- **Conversation context** — The last three exchanges are retrieved from the database and included in every API call, maintaining session context across stateless webhook requests.

---

## Project Structure

```
nanagpt/
├── app.py                  # Flask app, webhook handler, state machine
├── asi_handler.py          # ASI:ONE API calls, prompt building, tag extraction
├── whatsapp.py             # WABA message sending, media download
├── firebase_handler.py     # PostgreSQL operations (users, reminders, logs, history)
├── reminder_scheduler.py   # APScheduler — due reminders + follow-up nudges
├── requirements.txt
├── render.yaml             # Render deployment config
└── .env                    # Environment variables (not committed)
```

> Note: `firebase_handler.py` is named for historical reasons from an earlier
> prototype that used Firebase. It currently contains PostgreSQL (via `psycopg`)
> operations.

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/nanagpt.git
cd nanagpt
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up a PostgreSQL database

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to **Project Settings → Database → Connection String → URI**
3. Copy the connection string (use a password with no special characters
   such as `@` or `/`, since they break URL parsing)

### 4. Configure environment variables

Create a `.env` file:

```env
ASI_API_KEY=your_asi_one_api_key
ASI_BASE_URL=https://api.asi1.ai/v1
ASI_MODEL=asi1-mini

WHATSAPP_TOKEN=your_meta_permanent_access_token
PHONE_NUMBER_ID=your_whatsapp_phone_number_id
WEBHOOK_VERIFY_TOKEN=your_chosen_verify_token

CAREGIVER_PHONE=91XXXXXXXXXX

DATABASE_URL=postgresql://postgres:[password]@db.xxxxxxxx.supabase.co:5432/postgres
```

### 5. Run locally

```bash
python app.py
```

### 6. Expose locally with ngrok (for webhook testing)

```bash
ngrok http 5000
```

Use the generated `https://` URL as your webhook in the Meta Developer Portal.

---

## Deployment on Render

1. Push the repository to GitHub
2. Go to [render.com](https://render.com) → New Web Service → Connect repository
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1`
5. Add all environment variables from `.env`, including `DATABASE_URL`, in the Render dashboard
6. Deploy — your webhook URL will be `https://your-app.onrender.com/webhook`

### Keep the free instance alive (required for reminders to fire on time)

Render's free tier spins the instance down after 15 minutes of inactivity,
which stops the background scheduler entirely.

1. Go to [uptimerobot.com](https://uptimerobot.com) → create a free account
2. New Monitor → HTTP(S) → URL: `https://your-app.onrender.com/`
3. Interval: every 5 minutes

This keeps the instance continuously awake so reminders and follow-up nudges
fire at the correct time.

---

## WhatsApp Business API Setup

1. Create an app at [developers.facebook.com](https://developers.facebook.com) → Business type
2. Add the WhatsApp product
3. Under WhatsApp → Configuration, set:
   - **Callback URL**: `https://your-app.onrender.com/webhook`
   - **Verify Token**: value of `WEBHOOK_VERIFY_TOKEN` in your `.env`
4. Subscribe to the `messages` webhook field
5. For a permanent access token (the default token expires every 24 hours),
   create a System User in Meta Business Manager with
   `whatsapp_business_messaging` permission

---

## User Flow

```
First message (Hi)
  └── Onboarding
        ├── Name
        ├── Age
        ├── Known conditions
        ├── Current medicines
        └── Prescription photo (optional)
              └── Main Menu

Main Menu
  ├── 1 - Set Medicine Reminder
  ├── 2 - View My Reminders
  ├── 3 - Read Prescription
  ├── 4 - Ask Health Question
  ├── 5 - Log Health Reading
  ├── 6 - View Health History
  └── 7 - Change Language

Reminder Flow
  ├── Initial reminder sent at scheduled time
  ├── +10 min, if no "done" → Follow-up 1
  ├── +10 min, if no "done" → Follow-up 2 (final)
  └── User reply "done" at any point → clears all pending follow-ups

Reply 0 anytime → Main Menu
```

---

## Requirements

```
flask==3.0.3
openai==1.30.5
httpx==0.27.0
requests==2.32.3
APScheduler==3.10.4
python-dotenv==1.0.1
gunicorn==22.0.0
Pillow==10.4.0
psycopg[binary]==3.3.4
pytz==2024.1
```

---

## Environment Variables Reference

| Variable | Description |
|---|---|
| `ASI_API_KEY` | API key from ASI:ONE dashboard |
| `ASI_BASE_URL` | `https://api.asi1.ai/v1` |
| `ASI_MODEL` | `asi1-mini` |
| `WHATSAPP_TOKEN` | Meta permanent system user token |
| `PHONE_NUMBER_ID` | WhatsApp phone number ID from Meta dashboard |
| `WEBHOOK_VERIFY_TOKEN` | Any string you choose — must match Meta webhook config |
| `CAREGIVER_PHONE` | Caregiver's number in E.164 format without `+` (e.g. `919876543210`) |
| `DATABASE_URL` | PostgreSQL connection string from Supabase |

---

## Implementation Screenshots

<p align="center">
  <img src="readme_img/ss.png" alt="demo" width="700" />
</p>
<p align="center">
  <img src="readme_img/WABA.png" alt="demo" width="700" />
</p>
<p align="center">
  <img src="readme_img/render.png" alt="demo" width="700" />
</p>

---

## Issues Faced During Development

A non-exhaustive log of real issues hit while building and deploying, kept
here for anyone extending this project:

- **`401 Authentication Error` on every outbound message** — Meta's
  temporary access token expires every 24 hours. Fixed by generating a
  permanent token via a System User in Meta Business Manager.
- **`TypeError: Client.__init__() got an unexpected keyword argument
  'proxies'`** — version mismatch between `openai` and `httpx`. Fixed by
  pinning `openai==1.30.5` and `httpx==0.27.0`.
- **`undefined symbol: _PyInterpreterState_Get`** — `psycopg2-binary` has no
  compiled wheel for Python 3.14. Fixed by switching to `psycopg[binary]`
  (psycopg3).
- **`ImportError: cannot import name 'db'`** — leftover Firebase-style
  import after migrating to SQL, caught by keeping all DB access behind the
  same function names (`get_user`, `upsert_user`, etc.) regardless of the
  underlying engine.
- **Reminders saved but never delivered** — root cause was twofold:
  1. APScheduler was started inside `if __name__ == "__main__":`, which
     Gunicorn never executes. Fixed by starting the scheduler at module load.
  2. Render's free tier sleeps after 15 minutes idle, stopping the scheduler
     entirely. Fixed with an UptimeRobot monitor pinging every 5 minutes.
- **Profile reset and reminders disappearing every session** — Render's
  free-tier filesystem is ephemeral; the original SQLite file was wiped on
  every redeploy/restart. Fixed by migrating to a hosted PostgreSQL database
  on Supabase.
- **`failed to resolve host` on DB connection** — password containing `@`
  broke the connection string parsing. Fixed by resetting the Supabase DB
  password to one without special characters.
- **Prescription reading silently failing** — WhatsApp media URLs expire
  within minutes and require an auth header to fetch, which ASI:ONE's
  vision endpoint can't supply. Fixed by downloading the image server-side
  and sending it to ASI:ONE as a base64 data URI instead of a raw link.
- **Numeric menu replies misrouted** (e.g., selecting language option "2"
  was interpreted as main menu option "2") — fixed by making state-based
  routing strictly take priority over any number/keyword detection.
- **`TypeError: 'datetime.datetime' object is not subscriptable`** —
  PostgreSQL returns `timestamp` columns as native `datetime` objects, not
  strings (unlike SQLite). Fixed by formatting with `.strftime()` instead of
  string slicing.

---

## Notes

- The Meta temporary access token expires every 24 hours. Use a System User
  permanent token for any deployment beyond local testing.
- ASI:ONE's vision capability is used for prescription reading. Ensure
  images sent by users are reasonably well-lit and in focus for accurate
  results.
- On WhatsApp's free/test tier, outbound messages can only be sent to a user
  within a 24-hour window after they last messaged the bot. This window
  resets every time the user sends a new message.
- Render's free tier is sufficient for demos and testing but is not suited
  for reliable production-grade scheduled delivery without an external
  uptime monitor keeping the instance awake.

---

## Team

<p align="left">
  <a href="mailto:teaminspire2226@gmail.com">
    <img src="readme_img/team.png" alt="Contact Team INSPIRE" width="200"/>
  </a>
</p>

- [Tejas Gadge](https://www.linkedin.com/in/tejas-gadge-8a395b258/)
- [Anisha Shankar](https://www.linkedin.com/in/anisha-shankar-/)
