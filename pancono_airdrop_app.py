from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Pancono Airdrop Mini App")

# Serve static files if needed
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------- Frontend HTML ----------------
FRONTEND_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pancono Airdrop Mini App</title>
<style>
body { font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 0; }
header { background: #3b82f6; color: white; text-align: center; padding: 1rem; }
.container { padding: 2rem; max-width: 500px; margin: auto; background: white; border-radius: 10px; margin-top: 2rem; }
button { background: #3b82f6; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; }
button:hover { background: #2563eb; }
.nav { display: flex; justify-content: space-between; margin-top: 1rem; }
.hidden { display: none; }
</style>
</head>
<body>

<header>
<h1>Pancono Airdrop</h1>
<p>Total Balance: <span id="balance">0.0000</span> Panca</p>
</header>

<div class="container">
<div id="home-page">
<button id="claim-btn">Claim 0.0005 Panca</button>
<p id="status-msg"></p>
<div class="nav">
<button onclick="showPage('home')">Home</button>
<button onclick="showPage('referral')">Referral</button>
<button onclick="showPage('instructions')">Instructions</button>
</div>
</div>

<div id="referral-page" class="hidden">
<p>Invite your friends and earn 5 Panca for each friend!</p>
<input type="text" id="referral-link" readonly value="https://t.me/PanconoBot?start=USERID">
<button onclick="copyReferral()">Copy Link</button>
<p>Referral Count: <span id="ref-count">0</span></p>
<button onclick="showPage('home')">Back</button>
</div>

<div id="instructions-page" class="hidden">
<h2>Instructions</h2>
<p>1. Claim reward every 1 hour.</p>
<p>2. Invite friends via your referral link.</p>
<p>3. Join our Telegram: <a href="https://t.me/PanconoCoin" target="_blank">@PanconoCoin</a></p>
<p>4. Pancono Wallet Bot: <a href="https://t.me/PanconoBot" target="_blank">@PanconoBot</a></p>
<p>5. Follow Twitter: <a href="https://x.com/PanconaCoin" target="_blank">PanconaCoin</a></p>
<button onclick="showPage('home')">Back</button>
</div>
</div>

<script>
function showPage(page) {
    document.getElementById('home-page').classList.add('hidden');
    document.getElementById('referral-page').classList.add('hidden');
    document.getElementById('instructions-page').classList.add('hidden');
    document.getElementById(page + '-page').classList.remove('hidden');
}

function copyReferral() {
    const copyText = document.getElementById("referral-link");
    copyText.select();
    copyText.setSelectionRange(0, 99999);
    document.execCommand("copy");
    alert("Referral link copied!");
}

// Example init app
function initApp() {
    let balanceEl = document.getElementById('balance');
    let claimBtn = document.getElementById('claim-btn');
    let refCountEl = document.getElementById('ref-count');

    let balance = 0;
    let refCount = 0;
    let lastClaim = 0;

    claimBtn.addEventListener('click', function() {
        let now = Date.now();
        if (now - lastClaim >= 3600*1000) {  // 1 hour
            balance += 0.0005;
            balanceEl.textContent = balance.toFixed(4);
            lastClaim = now;
            document.getElementById('status-msg').textContent = "Claim successful!";
        } else {
            document.getElementById('status-msg').textContent = "Claim available once every 1 hour.";
        }
    });

    // Simulate referral count update (replace with backend logic)
    setInterval(() => {
        refCountEl.textContent = refCount;
    }, 1000);
}

showPage('home');
initApp();
</script>

</body>
</html>
"""

# ---------------- Routes ----------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return FRONTEND_HTML
