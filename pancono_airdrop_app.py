from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import os
import json
from datetime import datetime, timedelta

app = FastAPI()

# --- Environment Variables ---
CLAIM_AMOUNT = float(os.environ.get("CLAIM_AMOUNT", 0.0005))
CLAIM_INTERVAL = int(os.environ.get("CLAIM_INTERVAL", 3600))  # 1 hour default
REFERRAL_BONUS = float(os.environ.get("REFERRAL_BONUS", 5))
TELEGRAM_BOT_LINK = os.environ.get("TELEGRAM_BOT_LINK", "https://t.me/PanconoBot")
TELEGRAM_CHANNEL_LINK = os.environ.get("TELEGRAM_CHANNEL_LINK", "https://t.me/PanconoCoin")
TWITTER_LINK = os.environ.get("TWITTER_LINK", "https://x.com/PanconaCoin")

DATABASE_FILE = "database.json"

# --- Initialize Database ---
if not os.path.exists(DATABASE_FILE):
    with open(DATABASE_FILE, "w") as f:
        json.dump({}, f)

def load_db():
    with open(DATABASE_FILE, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DATABASE_FILE, "w") as f:
        json.dump(db, f, indent=4)

# --- Claim / Referral Logic ---
def claim(user_id):
    db = load_db()
    user = db.get(user_id, {"balance": 0, "last_claim": None, "referrals": 0})
    now = datetime.utcnow()
    last_claim = datetime.fromisoformat(user["last_claim"]) if user["last_claim"] else None

    if last_claim and now < last_claim + timedelta(seconds=CLAIM_INTERVAL):
        return False, (last_claim + timedelta(seconds=CLAIM_INTERVAL) - now).seconds

    user["balance"] += CLAIM_AMOUNT
    user["last_claim"] = now.isoformat()
    db[user_id] = user
    save_db(db)
    return True, CLAIM_AMOUNT

def add_referral(user_id):
    db = load_db()
    user = db.get(user_id, {"balance": 0, "last_claim": None, "referrals": 0})
    user["balance"] += REFERRAL_BONUS
    user["referrals"] += 1
    db[user_id] = user
    save_db(db)

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <title>Pancono Airdrop</title>
    </head>
    <body>
    <h1>Pancono Airdrop</h1>
    <p>Claim Amount: {CLAIM_AMOUNT} PANCA every {CLAIM_INTERVAL/3600} hours</p>
    <p>Referral Bonus: {REFERRAL_BONUS} PANCA per friend</p>
    <p><a href="{TELEGRAM_BOT_LINK}">Pancono Wallet Bot</a></p>
    <p><a href="{TELEGRAM_CHANNEL_LINK}">Telegram Channel</a></p>
    <p><a href="{TWITTER_LINK}">Twitter/X</a></p>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

# Optional: Add API endpoints for claim and referral if frontend needs AJAX
