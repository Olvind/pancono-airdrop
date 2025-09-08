from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
import json
import os
import asyncio

app = FastAPI()

DB_FILE = "database.json"
CLAIM_AMOUNT = 0.0005  # PANNO per second
REFERRAL_BONUS = 5.0   # PANNO per referral
CLAIM_INTERVAL = 1      # in seconds

# Load or initialize database
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({}, f)

def load_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

# Add user if not exists
def add_user(user_id):
    db = load_db()
    if user_id not in db:
        db[user_id] = {"balance": 0.0, "referrals": 0}
        save_db(db)
    return db[user_id]

# Claim function
async def auto_claim(user_id):
    while True:
        db = load_db()
        if user_id in db:
            db[user_id]["balance"] += CLAIM_AMOUNT
            save_db(db)
        await asyncio.sleep(CLAIM_INTERVAL)

# Referral function
def add_referral(user_id):
    db = load_db()
    if user_id in db:
        db[user_id]["referrals"] += 1
        db[user_id]["balance"] += REFERRAL_BONUS
        save_db(db)

# Simple dark neon UI
FRONTEND_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<title>Pancono Airdrop</title>
<style>
body { background-color:#0d0d0d; color:#00fffc; font-family:Arial, sans-serif; text-align:center; }
button { background-color:#00fffc; color:#0d0d0d; border:none; padding:10px 20px; margin:10px; cursor:pointer; font-weight:bold; }
button:hover { background-color:#00e0e0; }
#referral { color:#ff00ff; font-weight:bold; }
</style>
<script>
async function claim() {
    let res = await fetch("/claim?user_id=USER123");
    let data = await res.json();
    document.getElementById("balance").innerText = data.balance.toFixed(4);
    document.getElementById("referrals").innerText = data.referrals;
}
setInterval(claim, 1000);
</script>
</head>
<body>
<h1>Pancono Airdrop</h1>
<p>Total Balance: <span id="balance">0.0000</span> PANNO</p>
<p>Referral Count: <span id="referrals">0</span></p>
<p id="referral">Invite your friends and earn 5 PANNO each!</p>
<button onclick="claim()">Claim Now</button>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def home():
    add_user("USER123")  # example user
    return FRONTEND_HTML

@app.get("/claim")
async def claim(user_id: str):
    add_user(user_id)
    db = load_db()
    return {"balance": db[user_id]["balance"], "referrals": db[user_id]["referrals"]}
