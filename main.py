from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Gateway MCP para Varejo - Caso 1")

# ========== CONFIGURAÇÕES ==========
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
AUTO_APPROVE_SECRET = os.getenv("AUTO_APPROVE_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

admin_chat_id_str = os.getenv("ADMIN_CHAT_ID", "0")
try:
    ADMIN_CHAT_ID = int(admin_chat_id_str)
except ValueError:
    ADMIN_CHAT_ID = 0

def send_telegram_message(chat_id: int, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro: {e}")

def query_supabase(table: str, params: dict = None):
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def process_inventory_query(chat_id: int, product: str):
    try:
        results = query_supabase("inventory", params={"product_name": f"ilike.*{product}*"})
        if not results:
            send_telegram_message(chat_id, f"❌ Produto '{product}' não encontrado.")
            return
        p = results[0]
        cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
        msg = (f"🍺 *{p['product_name']}* {cold}\n"
               f"📦 Estoque: {p['quantity']} un\n"
               f"💰 Preço: R$ {p['price_cents']/100:.2f}")
        send_telegram_message(chat_id, msg)
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Erro: {str(e)}")

@app.post("/telegram/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.json()
        print("Recebido:", body)

        chat_id = None
        text = None
        if "message" in body:
            chat_id = body["message"]["chat"]["id"]
            text = body["message"].get("text", "")
        elif "channel_post" in body:
            chat_id = body["channel_post"]["chat"]["id"]
            text = body["channel_post"].get("text", "")

        if chat_id is None or text is None:
            return {"ok": True}

        if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
            return {"ok": True}

        if text.startswith("/estoque"):
            product = text.replace("/estoque", "").strip()
            if product:
                background_tasks.add_task(process_inventory_query, chat_id, product)
            else:
                send_telegram_message(chat_id, "Use: /estoque <produto>")

    except Exception as e:
        print(f"Erro: {e}")
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}