from fastapi import FastAPI, Request
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

def send_telegram_message(chat_id: int, text: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro: {e}")

@app.post("/telegram/webhook")
async def webhook(request: Request):
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

        if chat_id is None:
            return {"ok": True}

        if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
            print(f"Chat nao autorizado: {chat_id}")
            return {"ok": True}

        # ========== MENU COM BOTÕES ==========
        if text == "/menu" or text == "/start":
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📦 TESTE", "callback_data": "teste"}]
                ]
            }
            send_telegram_message(chat_id, "Clique no botão:", reply_markup=keyboard)
            return {"ok": True}

        # ========== CALLBACK DO BOTÃO ==========
        if "callback_query" in body:
            cb = body["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            data = cb["data"]
            callback_id = cb["id"]
            
            print(f"Callback recebido: {data}")
            
            # Responde o callback
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
            requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
            
            # Envia mensagem de confirmação
            send_telegram_message(chat_id, f"✅ Você clicou em: {data}")
            
            return {"ok": True}

    except Exception as e:
        print(f"Erro: {e}")
    
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}