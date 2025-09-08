from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
import json
import asyncio
from pathlib import Path

app = FastAPI()
DB_FILE = Path("database.json")

# Load database
def load_db():
    if DB_FILE.exists():
        with open(DB_FILE, "r") as f:
            return json.load(f)
    else:
        return {}

# Save database
def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

# Auto-claim PANNO every second
async def auto_claim(user_id):
    while True:
        db = load_db()
        if user_id in db:
            db[user_id]["balance"] += 0.0005
            save_db(db)
        await asyncio.sleep(1)  # 1 second interval

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user_id = request.query_params.get("user", "USER123")
    db = load_db()
    if user_id not in db:
        db[user_id] = {"balance": 0.0, "referrals": 0}
        save_db(db)
    user_data = db[user_id]

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Pancono Airdrop</title>
        <style>
            body {{
                font-family: 'Arial', sans-serif;
                background-color: #0d0d0d;
                color: #00ffea;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
            }}
            .card {{
                background-color: #1a1a1a;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 0 20px #00ffea;
                text-align: center;
            }}
            button {{
                background-color: #00ffea;
                color: #0d0d0d;
                border: none;
                padding: 10px 20px;
                font-size: 16px;
                border-radius: 10px;
                cursor: pointer;
                margin-top
