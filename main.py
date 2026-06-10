from fastapi import FastAPI, Request
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# ========== CONFIGURAÇÕES ==========
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

def send_message(chat_id: int, text: str, reply_markup: dict = None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro: {e}")

def answer_callback(callback_id: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
    except Exception:
        pass

# ========== TECLADO ==========
def main_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📦 RESUMO", "callback_data": "resumo"}],
            [{"text": "📋 COMPLETO", "callback_data": "completo"}],
            [{"text": "🍺 HEINEKEN", "callback_data": "heineken"}]
        ]
    }

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
            return {"ok": True}

        # ========== COMANDOS (ordem correta) ==========
        if text == "/menu" or text == "/start":
            send_message(chat_id, "🤖 *MENU*", reply_markup=main_keyboard())
            return {"ok": True}

        # Comandos específicos PRIMEIRO
        if text == "/resumo" or text == "/estoque_resumo":
            headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/inventory?order=product_name.asc", headers=headers)
            if resp.status_code == 200 and resp.json():
                msg = "*📦 RESUMO DO ESTOQUE*\n\n"
                for p in resp.json():
                    emoji = "❄️" if p["is_cold"] else "🌡️"
                    msg += f"{emoji} *{p['product_name']}*: {p['quantity']} un\n"
                send_message(chat_id, msg)
            else:
                send_message(chat_id, "📦 Estoque vazio.")
            return {"ok": True}

        if text == "/completo" or text == "/estoque_completo":
            headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
            resp = requests.get(f"{SUPABASE_URL}/rest/v1/inventory?order=product_name.asc", headers=headers)
            if resp.status_code == 200 and resp.json():
                msg = "*📦 ESTOQUE COMPLETO*\n\n"
                for p in resp.json():
                    gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg += (f"🍺 *{p['product_name']}*\n"
                           f"   🏷️ {p['brand']} | 📏 {p['volume_ml']}ml\n"
                           f"   📦 {p['quantity']} un | 💰 R$ {p['price_cents']/100:.2f}\n"
                           f"   {gelado}\n\n")
                send_message(chat_id, msg)
            else:
                send_message(chat_id, "📦 Estoque vazio.")
            return {"ok": True}

        # Comando /estoque (genérico) por ÚLTIMO
        if text.startswith("/estoque"):
            produto = text.replace("/estoque", "").strip()
            if produto:
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=ilike.*{produto}*"
                resp = requests.get(url, headers=headers)
                if resp.status_code == 200 and resp.json():
                    p = resp.json()[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, f"❌ Produto '{produto}' não encontrado.")
            else:
                send_message(chat_id, "Use: /estoque <produto>")
            return {"ok": True}

        # ========== CALLBACKS ==========
        if "callback_query" in body:
            cb = body["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            data = cb["data"]
            callback_id = cb["id"]
            
            print(f"Callback: {data}")
            answer_callback(callback_id)
            
            if data == "resumo":
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                resp = requests.get(f"{SUPABASE_URL}/rest/v1/inventory?order=product_name.asc", headers=headers)
                if resp.status_code == 200 and resp.json():
                    msg = "*📦 RESUMO*\n\n"
                    for p in resp.json():
                        emoji = "❄️" if p["is_cold"] else "🌡️"
                        msg += f"{emoji} *{p['product_name']}*: {p['quantity']} un\n"
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "📦 Estoque vazio.")
            elif data == "completo":
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                resp = requests.get(f"{SUPABASE_URL}/rest/v1/inventory?order=product_name.asc", headers=headers)
                if resp.status_code == 200 and resp.json():
                    msg = "*📦 COMPLETO*\n\n"
                    for p in resp.json():
                        gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                        msg += (f"🍺 *{p['product_name']}*\n"
                               f"   🏷️ {p['brand']} | 📏 {p['volume_ml']}ml\n"
                               f"   📦 {p['quantity']} un | 💰 R$ {p['price_cents']/100:.2f}\n"
                               f"   {gelado}\n\n")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "📦 Estoque vazio.")
            elif data == "heineken":
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=ilike.*heineken*"
                resp = requests.get(url, headers=headers)
                if resp.status_code == 200 and resp.json():
                    p = resp.json()[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Heineken não encontrada.")
            
            return {"ok": True}

        # ========== PERGUNTAS NATURAIS ==========
        texto_lower = text.lower()
        if any(p in texto_lower for p in ["heineken", "stella", "original", "brahma", "skol", "colorado"]):
            headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
            for palavra in ["heineken", "stella", "original", "brahma", "skol", "colorado"]:
                if palavra in texto_lower:
                    url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=ilike.*{palavra}*"
                    resp = requests.get(url, headers=headers)
                    if resp.status_code == 200 and resp.json():
                        p = resp.json()[0]
                        cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                        msg = (f"🍺 *{p['product_name']}* {cold}\n"
                               f"📦 Estoque: {p['quantity']} un\n"
                               f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                        send_message(chat_id, msg)
                    break
            return {"ok": True}

        send_message(chat_id, "Use /menu para ver as opções")

    except Exception as e:
        print(f"Erro: {e}")
    
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}
