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

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro send: {e}")

def answer_callback(callback_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
    except Exception as e:
        print(f"Erro answer: {e}")

def consultar_supabase(chat_id, endpoint):
    """Função genérica para consultar o Supabase com tratamento de erro."""
    try:
        headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
        url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
        print(f"Consultando: {url}")
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            return resp.json()
        else:
            send_message(chat_id, f"❌ Erro {resp.status_code} ao consultar o banco de dados.")
            return None
    except requests.exceptions.Timeout:
        send_message(chat_id, "❌ Tempo limite excedido. Tente novamente.")
        return None
    except Exception as e:
        send_message(chat_id, f"❌ Erro: {str(e)}")
        return None

@app.post("/telegram/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
        print("Recebido:", body)

        chat_id = None
        if "message" in body:
            chat_id = body["message"]["chat"]["id"]
            text = body["message"].get("text", "")
            
            if text == "/menu":
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "📦 RESUMO", "callback_data": "resumo"}],
                        [{"text": "📋 COMPLETO", "callback_data": "completo"}],
                        [{"text": "🍺 HEINEKEN", "callback_data": "heineken"}],
                        [{"text": "🍺 STELLA", "callback_data": "stella"}]
                    ]
                }
                send_message(chat_id, "🤖 *MENU*", reply_markup=keyboard)
                return {"ok": True}

        elif "callback_query" in body:
            cb = body["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            data = cb["data"]
            callback_id = cb["id"]
            
            print(f"Callback: {data}")
            answer_callback(callback_id)
            
            # ========== RESUMO ==========
            if data == "resumo":
                produtos = consultar_supabase(chat_id, "inventory?order=product_name.asc")
                if produtos:
                    if len(produtos) == 0:
                        send_message(chat_id, "📦 Estoque vazio.")
                    else:
                        msg = "*📦 RESUMO DO ESTOQUE*\n\n"
                        for p in produtos:
                            emoji = "❄️" if p["is_cold"] else "🌡️"
                            msg += f"{emoji} *{p['product_name']}*: {p['quantity']} un\n"
                        send_message(chat_id, msg)
            
            # ========== COMPLETO ==========
            elif data == "completo":
                produtos = consultar_supabase(chat_id, "inventory?order=product_name.asc")
                if produtos:
                    if len(produtos) == 0:
                        send_message(chat_id, "📦 Estoque vazio!")
                    else:
                        msg = "*📦 ESTOQUE COMPLETO*\n\n"
                        for p in produtos:
                            gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                            msg += (f"🍺 *{p['product_name']}*\n"
                                   f"   🏷️ {p['brand']} | 📏 {p['volume_ml']}ml\n"
                                   f"   📦 {p['quantity']} un | 💰 R$ {p['price_cents']/100:.2f}\n"
                                   f"   {gelado}\n\n")
                        if len(msg) > 4000:
                            msg = msg[:4000] + "\n\n... (mais produtos)"
                        send_message(chat_id, msg)
            
            # ========== HEINEKEN ==========
            elif data == "heineken":
                produtos = consultar_supabase(chat_id, "inventory?product_name=ilike.*heineken*")
                if produtos and len(produtos) > 0:
                    p = produtos[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Heineken não encontrada no estoque.")
            
            # ========== STELLA ==========
            elif data == "stella":
                produtos = consultar_supabase(chat_id, "inventory?product_name=ilike.*stella*")
                if produtos and len(produtos) > 0:
                    p = produtos[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Stella Artois não encontrada no estoque.")
            
            return {"ok": True}

    except Exception as e:
        print(f"Erro geral: {e}")
    
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}