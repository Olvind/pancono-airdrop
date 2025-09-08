// static/app.js
// Minimal client logic to run inside Telegram WebApp or any browser.
// Expects user_id to be set from Telegram initData or manually for testing.

const API = "";

const USER = {
  // In production, you'll get these from Telegram WebApp initData / secure payload.
  // For testing on Replit, change user_id to any unique string (e.g., "testuser123").
  user_id: null,
  username: "",
  first_name: ""
};

// Simple helper for Decimal display
function fmt(n) {
  return Number(n).toFixed(4) + " PANNO";
}

// DOM
const balanceEl = document.getElementById("balance");
const startBtn = document.getElementById("start-btn");
const activeArea = document.getElementById("active-area");
const timerEl = document.getElementById("timer");
const navHome = document.getElementById("nav-home");
const navRef = document.getElementById("nav-ref");
const navInst = document.getElementById("nav-inst");
const homeView = document.getElementById("home-view");
const refView = document.getElementById("referral-view");
const instView = document.getElementById("instructions-view");
const refCountEl = document.getElementById("ref-count");
const refLinkEl = document.getElementById("ref-link");
const copyRefBtn = document.getElementById("copy-ref");
const instructionsText = document.getElementById("instructions-text");

let autoClaimInterval = null;
let sessionRemaining = 0;

// Attempt to extract Telegram WebApp initDataUnsafe if available
function detectTelegramUser() {
  try {
    if (window.TelegramWebApp) {
      const webapp = window.TelegramWebApp;
      const user = webapp.initDataUnsafe?.user;
      if (user) {
        USER.user_id = String(user.id);
        USER.username = user.username || "";
        USER.first_name = user.first_name || "";
      }
    }
  } catch (e) {
    console.warn("Telegram detection failed", e);
  }
  // If not available, check URL param ?testid=xxx for local testing
  if (!USER.user_id) {
    const urlParams = new URLSearchParams(window.location.search);
    const t = urlParams.get("testid");
    if (t) USER.user_id = t;
  }
  // fallback to a local test id
  if (!USER.user_id) {
    USER.user_id = "test_user_" + Math.floor(Math.random() * 99999);
    USER.username = "tester";
    USER.first_name = "Tester";
  }
}

// Fetch helpers
async function postJSON(url, data) {
  const res = await fetch(url, {
    method: "POST",
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  return res.json();
}
async function getJSON(url) {
  const res = await fetch(url);
  return res.json();
}

// UI actions
async function onStartClick() {
  startBtn.disabled = true;
  startBtn.innerText = "Starting...";
  const payload = { user_id: USER.user_id, username: USER.username, first_name: USER.first_name };
  const res = await postJSON("/api/start", payload);
  if (res && res.ok) {
    // show active area
    startBtn.classList.add("hidden");
    activeArea.classList.remove("hidden");
    startAutoClaim();
  } else {
    alert("Could not start session");
    startBtn.disabled = false;
    startBtn.innerText = "Start Airdrop";
  }
}

function startAutoClaim() {
  // clear prior interval
  if (autoClaimInterval) {
    clearInterval(autoClaimInterval);
    autoClaimInterval = null;
  }
  // immediately call to update balance
  doAutoClaimTick();
  autoClaimInterval = setInterval(doAutoClaimTick, 1000);
}

async function doAutoClaimTick() {
  // call /api/auto-claim
  const payload = { user_id: USER.user_id, username: USER.username, first_name: USER.first_name };
  try {
    const res = await postJSON("/api/auto-claim", payload);
    if (res && res.ok) {
      // update balance and timer
      const bal = res.balance !== undefined ? Number(res.balance) : 0;
      balanceEl.innerText = fmt(bal);
      const remaining = res.remaining !== undefined ? Number(res.remaining) : 0;
      sessionRemaining = remaining;
      updateTimer(remaining);
      if (remaining <= 0) {
        // session ended
        clearInterval(autoClaimInterval);
        autoClaimInterval = null;
        activeArea.classList.add("hidden");
        startBtn.classList.remove("hidden");
        startBtn.disabled = false;
        startBtn.innerText = "Start Airdrop";
      }
    } else {
      // expired or error
      if (res.error === "expired") {
        clearInterval(autoClaimInterval);
        autoClaimInterval = null;
        activeArea.classList.add("hidden");
        startBtn.classList.remove("hidden");
        startBtn.disabled = false;
        startBtn.innerText = "Start Airdrop";
        if (res.balance !== undefined) balanceEl.innerText = fmt(res.balance);
      } else {
        // unknown; stop to avoid spamming
        console.warn("auto-claim error", res);
      }
    }
  } catch (e) {
    console.error("auto-claim fetch error", e);
  }
}

function updateTimer(seconds) {
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  timerEl.innerText = `${mm}:${ss}`;
}

// Nav handlers
navHome.addEventListener("click", showHome);
navRef.addEventListener("click", showRef);
navInst.addEventListener("click", showInst);
startBtn.addEventListener("click", onStartClick);

copyRefBtn.addEventListener("click", () => {
  refLinkEl.select();
  document.execCommand("copy");
  copyRefBtn.innerText = "Copied";
  setTimeout(()=> copyRefBtn.innerText = "Copy", 1500);
});

// View switchers
async function showHome() {
  navHome.classList.add("active");
  navRef.classList.remove("active");
  navInst.classList.remove("active");
  homeView.classList.remove("hidden");
  refView.classList.add("hidden");
  instView.classList.add("hidden");
}
async function showRef() {
  navHome.classList.remove("active");
  navRef.classList.add("active");
  navInst.classList.remove("active");
  homeView.classList.add("hidden");
  refView.classList.remove("hidden");
  instView.classList.add("hidden");
  // load referral
  const res = await getJSON(`/api/referral?user_id=${encodeURIComponent(USER.user_id)}`);
  if (res && res.ok) {
    refCountEl.innerText = res.count;
    refLinkEl.value = res.link;
  }
}
async function showInst() {
  navHome.classList.remove("active");
  navRef.classList.remove("active");
  navInst.classList.add("active");
  homeView.classList.add("hidden");
  refView.classList.add("hidden");
  instView.classList.remove("hidden");
  const res = await getJSON("/api/instructions");
  if (res && res.ok) {
    instructionsText.innerText = res.instructions;
  }
}

// init
(async function init() {
  detectTelegramUser();
  showHome();
  // try fetch status to show current balance & if session active
  const status = await getJSON(`/api/status?user_id=${encodeURIComponent(USER.user_id)}`);
  if (status) {
    balanceEl.innerText = fmt(status.balance || 0);
    if (status.active) {
      // session in-progress
      startBtn.classList.add("hidden");
      activeArea.classList.remove("hidden");
      sessionRemaining = status.remaining;
      updateTimer(sessionRemaining);
      startAutoClaim();
    } else {
      startBtn.classList.remove("hidden");
      activeArea.classList.add("hidden");
      startBtn.disabled = false;
      startBtn.innerText = "Start Airdrop";
    }
  }
})();
