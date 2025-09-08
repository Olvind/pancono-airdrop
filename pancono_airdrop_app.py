import os
import json
import time
import uuid
import aiosqlite
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta

# Config
APP_TITLE = "Pancono Airdrop"
CLAIM_AMOUNT = 0.0005  # PANCA per claim
CLAIM_COOLDOWN_SECONDS = 60 * 60  # 1 hour
REF_BONUS = 5.0
DB_FILE = os.getenv("DB_FILE", "airdrop.db")
MODE = os.getenv("MODE", "telegram")  # or 'direct'
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "PanconoBot")

app = FastAPI(title=APP_TITLE)

# serve static if present
if not os.path.exists("static"):
    os.makedirs("static" , exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------- DB helpers (SQLite via aiosqlite for demo)
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                created_at INTEGER,
                mode TEXT,
                telegram_id INTEGER,
                balance REAL DEFAULT 0,
                last_claim_ts INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id TEXT,
                referred_id TEXT,
                PRIMARY KEY (referrer_id, referred_id)
            )
        """)
        await db.commit()

@app.on_event("startup")
async def startup_event():
    await init_db()

async def create_user(user_id: str, mode: str, telegram_id: int = None):
    now = int(time.time())
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO users (id, created_at, mode, telegram_id, balance, last_claim_ts) VALUES (?,?,?,?,?,?)",
                         (user_id, now, mode, telegram_id, 0.0, 0))
        await db.commit()

async def get_user_by_id(user_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id, created_at, mode, telegram_id, balance, last_claim_ts FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "created_at": row[1], "mode": row[2], "telegram_id": row[3], "balance": row[4], "last_claim_ts": row[5]}

async def get_user_by_telegram(telegram_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id, created_at, mode, telegram_id, balance, last_claim_ts FROM users WHERE telegram_id = ?", (telegram_id,))
        row = await cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "created_at": row[1], "mode": row[2], "telegram_id": row[3], "balance": row[4], "last_claim_ts": row[5]}

async def add_balance(user_id: str, amount: float):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
        await db.commit()

async def update_last_claim(user_id: str, ts: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET last_claim_ts = ? WHERE id = ?", (ts, user_id))
        await db.commit()

async def referral_exists(referrer_id: str, referred_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT 1 FROM referrals WHERE referrer_id = ? AND referred_id = ?", (referrer_id, referred_id))
        return await cur.fetchone() is not None

async def add_referral(referrer_id: str, referred_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?,?)", (referrer_id, referred_id))
        await db.commit()

async def get_referral_count(referrer_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT count(*) FROM referrals WHERE referrer_id = ?", (referrer_id,))
        row = await cur.fetchone()
        return row[0] if row else 0

# ------------------ API Endpoints ------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # serve unified frontend (same UI for both modes) - client JS will adapt
    html = FRONTEND_HTML.replace("__TELEGRAM_BOT_USERNAME__", TELEGRAM_BOT_USERNAME).replace("__MODE__", MODE)
    return HTMLResponse(content=html)

@app.post("/api/init")
async def api_init(payload: dict):
    """Initialize user session.
    payload may include:
      - mode: 'telegram' or 'direct' (optional)
      - telegram_id: int (if available)
      - start_ref: referrer id (could be telegram id or internal id depending on flow)
    """
    mode = payload.get("mode", MODE)
    telegram_id = payload.get("telegram_id")
    start_ref = payload.get("start_ref")

    # Create or find user
    if mode == 'telegram' and telegram_id:
        u = await get_user_by_telegram(telegram_id)
        if u is None:
            uid = str(telegram_id)  # use telegram id as primary id in telegram mode
            await create_user(uid, 'telegram', telegram_id)
            # process referral
            if start_ref and int(start_ref) != telegram_id:
                # treat start_ref as telegram id of referrer
                ref_uid = str(start_ref)
                exists = await referral_exists(ref_uid, uid)
                if not exists:
                    await add_referral(ref_uid, uid)
                    await add_balance(ref_uid, REF_BONUS)
            u = await get_user_by_telegram(telegram_id)
        return JSONResponse(u)
    else:
        # direct mode: we expect client to provide or request an internal uid
        uid = payload.get('internal_id')
        if not uid:
            uid = str(uuid.uuid4())
            await create_user(uid, 'direct', None)
            # process referral (start_ref is internal id)
            if start_ref and start_ref != uid:
                exists = await referral_exists(start_ref, uid)
                if not exists:
                    await add_referral(start_ref, uid)
                    await add_balance(start_ref, REF_BONUS)
        else:
            u = await get_user_by_id(uid)
            if not u:
                # create
                await create_user(uid, 'direct', None)
                if start_ref and start_ref != uid:
                    exists = await referral_exists(start_ref, uid)
                    if not exists:
                        await add_referral(start_ref, uid)
                        await add_balance(start_ref, REF_BONUS)
        u = await get_user_by_id(uid)
        return JSONResponse(u)

@app.post("/api/claim")
async def api_claim(payload: dict):
    """User attempts to claim the hourly reward.
    payload: {mode, telegram_id or internal_id}
    """
    mode = payload.get('mode', MODE)
    if mode == 'telegram':
        telegram_id = int(payload.get('telegram_id'))
        if not telegram_id:
            raise HTTPException(400, "telegram_id required for telegram mode")
        u = await get_user_by_telegram(telegram_id)
        if not u:
            raise HTTPException(400, "user not found; init first")
        now = int(time.time())
        last = u['last_claim_ts'] or 0
        if now - last < CLAIM_COOLDOWN_SECONDS:
            remaining = CLAIM_COOLDOWN_SECONDS - (now - last)
            return JSONResponse({"status":"cooldown", "seconds_remaining": remaining, "balance": u['balance']})
        # credit
        await add_balance(u['id'], CLAIM_AMOUNT)
        await update_last_claim(u['id'], now)
        u2 = await get_user_by_id(u['id'])
        return JSONResponse({"status":"ok", "balance": u2['balance']})
    else:
        uid = payload.get('internal_id')
        if not uid:
            raise HTTPException(400, "internal_id required for direct mode")
        u = await get_user_by_id(uid)
        if not u:
            raise HTTPException(400, "user not found; init first")
        now = int(time.time())
        last = u['last_claim_ts'] or 0
        if now - last < CLAIM_COOLDOWN_SECONDS:
            remaining = CLAIM_COOLDOWN_SECONDS - (now - last)
            return JSONResponse({"status":"cooldown", "seconds_remaining": remaining, "balance": u['balance']})
        await add_balance(uid, CLAIM_AMOUNT)
        await update_last_claim(uid, now)
        u2 = await get_user_by_id(uid)
        return JSONResponse({"status":"ok", "balance": u2['balance']})

@app.get("/api/status")
async def api_status_get(mode: str = None, telegram_id: int = None, internal_id: str = None):
    mode = mode or MODE
    if mode == 'telegram':
        if not telegram_id:
            raise HTTPException(400, "telegram_id required")
        u = await get_user_by_telegram(telegram_id)
        if not u:
            raise HTTPException(404, "user not found")
        ref_count = await get_referral_count(u['id'])
        next_available = 0
        now = int(time.time())
        if u['last_claim_ts']:
            elapsed = now - u['last_claim_ts']
            if elapsed < CLAIM_COOLDOWN_SECONDS:
                next_available = CLAIM_COOLDOWN_SECONDS - elapsed
        referral_link = f"https://t.me/{TELEGRAM_BOT_USERNAME}?start={u['id']}"
        return JSONResponse({"balance": u['balance'], "next_available_seconds": next_available, "referral_count": ref_count, "referral_link": referral_link})
    else:
        if not internal_id:
            raise HTTPException(400, "internal_id required")
        u = await get_user_by_id(internal_id)
        if not u:
            raise HTTPException(404, "user not found")
        ref_count = await get_referral_count(u['id'])
        next_available = 0
        now = int(time.time())
        if u['last_claim_ts']:
            elapsed = now - u['last_claim_ts']
            if elapsed < CLAIM_COOLDOWN_SECONDS:
                next_available = CLAIM_COOLDOWN_SECONDS - elapsed
        referral_link = f"{get_base_url()}/?start={u['id']}"
        return JSONResponse({"balance": u['balance'], "next_available_seconds": next_available, "referral_count": ref_count, "referral_link": referral_link})

@app.get("/api/referrals")
async def api_referrals_get(referrer_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT referred_id FROM referrals WHERE referrer_id = ?", (referrer_id,))
        rows = await cur.fetchall()
        ids = [r[0] for r in rows]
    return JSONResponse({"referred_ids": ids, "count": len(ids)})

# small helper to craft base url (best-effort)
def get_base_url():
    # in serverless environment, recommend setting BASE_URL env var
    base = os.getenv('BASE_URL')
    if base:
        return base.rstrip('/')
    return 'https://your-app.vercel.app'

# ------------------ Frontend HTML (single-page) ------------------
FRONTEND_HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pancono Airdrop</title>
  <style>
    body{font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;margin:0;background:#f6f7fb;color:#0b1020}
    .container{max-width:700px;margin:24px auto;padding:18px;background:#fff;border-radius:12px;box-shadow:0 6px 18px rgba(12,20,40,0.08)}
    .balance{font-size:20px;font-weight:700;margin-bottom:12px}
    .muted{color:#6b7280}
    .btn{display:inline-block;padding:12px 16px;border-radius:10px;background:#111827;color:#fff;text-decoration:none;font-weight:600;margin:6px 4px;border:none}
    .ghost{background:#eef2ff;color:#111827}
    .bottom-nav{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid #eee;padding:8px;display:flex;justify-content:space-around}
    .card{padding:12px;border-radius:10px;background:#fafafa;margin-top:12px}
    .small{font-size:13px}
    .linkbox{background:#fff;padding:10px;border-radius:8px;border:1px dashed #e5e7eb}
  </style>
</head>
<body>
  <div class="container" id="page">
    <div id="homePage">
      <div class="balance">💰 Total Balance: <span id="balance">0.0000</span> PANCA</div>
      <div id="statusText" class="muted">Loading status...</div>
      <div id="controls" style="margin-top:12px"></div>
      <div class="card small">
        <div>Rate: <strong>0.0005 PANCA / claim</strong></div>
        <div>Cooldown: <strong>1 hour</strong></div>
        <div>Referral bonus: <strong>5 PANCA</strong></div>
      </div>
    </div>

    <div id="refPage" style="display:none">
      <h3>👥 Referral</h3>
      <p>Invite your friends and earn <strong>5 PANCA</strong> for inviting each friend.</p>
      <div class="linkbox">
        <div id="refLink">—</div>
        <button class="btn ghost" id="copyLink">📋 Copy Link</button>
      </div>
      <div style="margin-top:10px">Referrals Count: <strong id="refCount">0</strong></div>
    </div>

    <div id="instPage" style="display:none">
      <h3>ℹ️ Instructions</h3>
      <ol>
        <li>Click <strong>Claim</strong> to earn 0.0005 PANCA once every 1 hour.</li>
        <li>Invite friends using your referral link — you get <strong>5 PANCA</strong> per new referred user.</li>
        <li>Links: <br>
            Telegram Channel: <a href="https://t.me/PanconoCoin" target="_blank">https://t.me/PanconoCoin</a><br>
            Pancono Wallet Bot: <a href="https://t.me/PanconoBot" target="_blank">@PanconoBot</a><br>
            Twitter (X): <a href="https://x.com/PanconaCoin" target="_blank">https://x.com/PanconaCoin</a>
        </li>
      </ol>
    </div>

  </div>

  <div class="bottom-nav">
    <button onclick="showPage('home')" class="btn ghost">🏠 Home</button>
    <button onclick="showPage('ref')" class="btn ghost">👥 Referral</button>
    <button onclick="showPage('inst')" class="btn ghost">ℹ️ Instructions</button>
  </div>

<script>
const MODE = '__MODE__'; // 'telegram' or 'direct'
const TELEGRAM_BOT_USERNAME = '__TELEGRAM_BOT_USERNAME__';
let tg = window.Telegram ? window.Telegram.WebApp : null;
let user = null; // {mode, telegram_id?, internal_id?}

function showPage(p){
  document.getElementById('homePage').style.display = p==='home' ? 'block':'none';
  document.getElementById('refPage').style.display = p==='ref' ? 'block':'none';
  document.getElementById('instPage').style.display = p==='inst' ? 'block':'none';
}

async function api(path, data){
  const resp = await fetch('/api/'+path, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  });
  return resp.json();
}

async function getStatus(){
  if(MODE==='telegram'){
    const resp = await fetch(`/api/status?mode=telegram&telegram_id=${user.telegram_id}`);
    const js = await resp.json();
    document.getElementById('balance').innerText = Number(js.balance).toFixed(4);
    document.getElementById('refCount').innerText = js.referral_count;
    document.getElementById('refLink').innerText = js.referral_link;
    if(js.next_available_seconds>0){
      document.getElementById('statusText').innerText = `Next claim available in ${Math.ceil(js.next_available_seconds/60)} min`;
      document.getElementById('controls').innerHTML = `<button class=\"btn\" id=\"claimBtn\">⏳ Wait (${Math.ceil(js.next_available_seconds/60)}m)</button>`;
      document.getElementById('claimBtn').disabled = true;
    } else {
      document.getElementById('statusText').innerText = `You can claim now.`;
      document.getElementById('controls').innerHTML = `<button class=\"btn\" id=\"claimBtn\">▶️ Claim</button>`;
      document.getElementById('claimBtn').onclick = async ()=>{ const r = await api('claim',{mode:'telegram', telegram_id:user.telegram_id}); alert(JSON.stringify(r)); await refresh(); };
    }
  } else {
    const resp = await fetch(`/api/status?mode=direct&internal_id=${user.internal_id}`);
    const js = await resp.json();
    document.getElementById('balance').innerText = Number(js.balance).toFixed(4);
    document.getElementById('refCount').innerText = js.referral_count;
    document.getElementById('refLink').innerText = js.referral_link;
    if(js.next_available_seconds>0){
      document.getElementById('statusText').innerText = `Next claim available in ${Math.ceil(js.next_available_seconds/60)} min`;
      document.getElementById('controls').innerHTML = `<button class=\"btn\" id=\"claimBtn\">⏳ Wait (${Math.ceil(js.next_available_seconds/60)}m)</button>`;
      document.getElementById('claimBtn').disabled = true;
    } else {
      document.getElementById('statusText').innerText = `You can claim now.`;
      document.getElementById('controls').innerHTML = `<button class=\"btn\" id=\"claimBtn\">▶️ Claim</button>`;
      document.getElementById('claimBtn').onclick = async ()=>{ const r = await api('claim',{mode:'direct', internal_id:user.internal_id}); alert(JSON.stringify(r)); await refresh(); };
    }
  }
}

async function refresh(){
  await getStatus();
}

async function initApp(){
  // If opened inside Telegram WebApp, read user info
  let start_ref = null;
  try{
    const params = new URLSearchParams(window.location.search);
    start_ref = params.get('start') || params.get('ref');
  }catch(e){ }

  if(window.Telegram && window.Telegram.WebApp){
    try{
      const tu = window.Telegram.WebApp.initDataUnsafe.user;
      if(MODE==='telegram'){
        user = {mode:'telegram', telegram_id: tu.id};
        // call init
        await api('init',{mode:'telegram', telegram_id: tu.id, start_ref: start_ref});
      } else {
        // direct inside TG WebApp; behave like direct mode but prefer telegram id mapping
        // create internal id tied to telegram id to avoid duplicates
        const internal_id = 'tg-'+tu.id;
        user = {mode:'direct', internal_id: internal_id};
        await api('init', {mode:'direct', internal_id: internal_id, start_ref: start_ref});
      }
    }catch(e){
      console.warn('tg init error', e);
    }
  }

  if(!user){
    // Direct mode or testing outside Telegram. Use localStorage stored internal_id
    let internal_id = localStorage.getItem('pancono_internal_id');
    if(!internal_id){
      internal_id = self.crypto ? ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,c=> (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)) : (Date.now()+Math.random()).toString(36);
      localStorage.setItem('pancono_internal_id', internal_id);
    }
    user = {mode:'direct', internal_id: internal_id};
    await api('init', {mode:'direct', internal_id: internal_id, start_ref: start_ref});
  }

  await refresh();
}

// copy button
document.addEventListener('click', function(e){
  if(e.target && e.target.id==='copyLink'){
    const txt = document.getElementById('refLink').innerText;
    navigator.clipboard.writeText(txt).then(()=>{ alert('Referral link copied!'); });
  }
});

showPage('home');
initApp();
</script>
</body>
</html>
