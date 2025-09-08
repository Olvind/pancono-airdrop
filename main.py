# main.py
import os
import sqlite3
import threading
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from decimal import Decimal, ROUND_DOWN
from fastapi.middleware.cors import CORSMiddleware

# Config from env
BOT_USERNAME = os.getenv("BOT_USERNAME", "PanconoBot")  # used for referral links
PANCONO_CHANNEL = os.getenv("PANCONO_CHANNEL_LINK", "https://t.me/your_pancono_channel")
TWITTER_LINK = os.getenv("TWITTER_LINK", "https://twitter.com/your_twitter")
PANCONO_WALLET_BOT = os.getenv("PANCONO_WALLET_BOT", "@PanconoBot")
PORT = int(os.getenv("PORT", "8000"))

# Reward settings
SESSION_SECONDS = 600  # 10 minutes
PER_SECOND_REWARD = Decimal("1") / Decimal(str(SESSION_SECONDS))  # exact fraction
# Format display precision
DISPLAY_PRECISION = Decimal("0.0001")

# DB
DB_PATH = "pancono.db"
DB_LOCK = threading.Lock()

# FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replit/TG WebApp - tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- DB helpers ---
def init_db():
    with DB_LOCK, sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            balance REAL DEFAULT 0
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            user_id TEXT PRIMARY KEY,
            wallet_address TEXT,
            linked_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id TEXT,
            referred_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS rounds (
            user_id TEXT PRIMARY KEY,
            start_ts INTEGER,
            end_ts INTEGER,
            last_claim_ts INTEGER
        )
        """)
        conn.commit()

def get_conn():
    return sqlite3.connect(DB_PATH)

# Utility: decimal to float for JSON
def d2f(d: Decimal) -> float:
    return float(d.quantize(DISPLAY_PRECISION, rounding=ROUND_DOWN))

# --- Models ---
class StartPayload(BaseModel):
    user_id: str
    username: Optional[str] = ""
    first_name: Optional[str] = ""
    referrer: Optional[str] = None  # referrer id (string)

class WalletPayload(BaseModel):
    user_id: str
    wallet_address: str

# --- App startup ---
@app.on_event("startup")
def startup_event():
    init_db()

# --- Templates / Frontend ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Render main mini-app UI; embed links & bot username
    return templates.TemplateResponse("index.html", {
        "request": request,
        "bot_username": BOT_USERNAME,
        "pancono_channel": PANCONO_CHANNEL,
        "twitter_link": TWITTER_LINK,
        "wallet_bot": PANCONO_WALLET_BOT
    })

# --- API endpoints ---

@app.post("/api/start")
async def api_start(payload: StartPayload):
    """
    Begin a user session (10 min). If a session exists and still active, return it.
    """
    now = int(datetime.utcnow().timestamp())
    start_ts = now
    end_ts = now + SESSION_SECONDS
    with DB_LOCK, get_conn() as conn:
        cur = conn.cursor()
        # ensure user exists
        cur.execute("SELECT 1 FROM users WHERE user_id = ?", (payload.user_id,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                        (payload.user_id, payload.username or "", payload.first_name or ""))
        # register referral if provided and not duplicate
        if payload.referrer:
            # avoid self-referral
            if payload.referrer != payload.user_id:
                cur.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (payload.user_id,))
                if not cur.fetchone():
                    cur.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                                (payload.referrer, payload.user_id))
        # create or replace round record; set last_claim_ts to start_ts-1 so first second can be credited
        cur.execute("REPLACE INTO rounds (user_id, start_ts, end_ts, last_claim_ts) VALUES (?, ?, ?, ?)",
                    (payload.user_id, start_ts, end_ts, start_ts - 1))
        conn.commit()
    return JSONResponse({"ok": True, "start_ts": start_ts, "end_ts": end_ts})

@app.get("/api/status")
async def api_status(user_id: str):
    """
    Return remaining time (seconds), current balance (from DB), and whether a session active.
    """
    now = int(datetime.utcnow().timestamp())
    with DB_LOCK, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        r = cur.fetchone()
        balance = Decimal(str(r[0])) if r else Decimal("0")
        cur.execute("SELECT start_ts, end_ts FROM rounds WHERE user_id = ?", (user_id,))
        rr = cur.fetchone()
        if not rr:
            return {"active": False, "remaining": 0, "balance": d2f(balance)}
        start_ts, end_ts = rr
        remaining = max(0, end_ts - now)
        active = now < end_ts
    return {"active": active, "remaining": remaining, "balance": d2f(balance)}

@app.post("/api/auto-claim")
async def api_auto_claim(payload: StartPayload):
    """
    Called every second by the frontend. Backend calculates how many seconds
    have passed since last_claim_ts (bounded by end_ts) and credits PER_SECOND_REWARD
    multiplied by seconds_to_credit. Returns new balance and remaining seconds.
    """
    uid = payload.user_id
    now = int(datetime.utcnow().timestamp())
    with DB_LOCK, get_conn() as conn:
        cur = conn.cursor()
        # fetch round
        cur.execute("SELECT start_ts, end_ts, last_claim_ts FROM rounds WHERE user_id = ?", (uid,))
        r = cur.fetchone()
        if not r:
            return JSONResponse({"ok": False, "error": "no_active_round", "balance": 0, "remaining": 0})
        start_ts, end_ts, last_claim_ts = r
        if now > end_ts:
            # session ended
            cur.execute("DELETE FROM rounds WHERE user_id = ?", (uid,))
            conn.commit()
            # return current balance
            cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
            b = cur.fetchone()
            bal = Decimal(str(b[0])) if b else Decimal("0")
            return JSONResponse({"ok": False, "error": "expired", "balance": d2f(bal), "remaining": 0})
        # compute seconds to credit
        # last_claim_ts may be None -> treat as start-1
        if last_claim_ts is None:
            last_claim_ts = start_ts - 1
        # seconds eligible are seconds between last_claim_ts and now, but not beyond end_ts
        credit_until = min(now, end_ts)
        seconds_to_credit = max(0, credit_until - last_claim_ts)
        if seconds_to_credit <= 0:
            # nothing to credit (already credited this second)
            cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
            b = cur.fetchone()
            bal = Decimal(str(b[0])) if b else Decimal("0")
            remaining = end_ts - now
            return {"ok": True, "credited": 0, "balance": d2f(bal), "remaining": remaining}
        # compute credit
        credit = PER_SECOND_REWARD * Decimal(seconds_to_credit)
        # update user balance
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        b = cur.fetchone()
        bal = Decimal(str(b[0])) if b else Decimal("0")
        new_bal = (bal + credit)
        cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (float(new_bal), uid))
        # update last_claim_ts to credit_until
        cur.execute("UPDATE rounds SET last_claim_ts = ? WHERE user_id = ?", (credit_until, uid))
        conn.commit()
        remaining = end_ts - now
    return {"ok": True, "credited": float(credit), "balance": d2f(new_bal), "remaining": remaining}

@app.post("/api/wallet")
async def api_wallet(payload: WalletPayload):
    """
    Save wallet address for user.
    """
    with DB_LOCK, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("REPLACE INTO wallets (user_id, wallet_address) VALUES (?, ?)",
                    (payload.user_id, payload.wallet_address))
        conn.commit()
    return {"ok": True}

@app.get("/api/referral")
async def api_referral(user_id: str):
    """
    Return referral count and referral link to share.
    """
    with DB_LOCK, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        count = cur.fetchone()[0]
    bot = BOT_USERNAME.strip("@")
    start_link = f"https://t.me/{bot}?start={user_id}"
    return {"ok": True, "count": count, "link": start_link}

@app.get("/api/instructions")
async def api_instructions():
    text = (
        "Pancono Mini App Instructions:\n\n"
        "1) Press START to begin a 10-minute airdrop session.\n"
        "2) While active, your balance increases every second (1 PANNO total per 10 minutes).\n"
        "3) When the session ends, START reappears and you can begin a new session.\n"
        "4) Link your TON wallet to save address for withdrawals.\n"
        "5) Use your referral link to invite others and earn referral counts.\n"
    )
    return {"ok": True, "instructions": text}

# --- Admin / debug endpoints (optional) ---
@app.get("/api/debug/balance")
async def debug_balance(user_id: str):
    with DB_LOCK, get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        r = cur.fetchone()
        return {"balance": r[0] if r else 0}

# health
@app.get("/health")
async def health():
    return {"ok": True}

# Run: uvicorn main:app --host 0.0.0.0 --port 8000
