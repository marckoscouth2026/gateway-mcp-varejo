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
    print(f"ERRO: ADMIN_CHAT_ID com valor inválido: '{admin_chat_id_str}'. Usando 0.")
    ADMIN_CHAT_ID = 0

# ========== FUNÇÕES ==========
def send_telegram_message(chat_id: int, text: str, reply_markup: dict = None):
    """Envia mensagem para o Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar: {e}")

def answer_callback(callback_id: str):
    """Responde o callback (remove o loading do botão)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
    except Exception as e:
        print(f"Erro answer: {e}")

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

def process_estoque_resumo(chat_id: int):
    try:
        headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
        url = f"{SUPABASE_URL}/rest/v1/inventory?order=product_name.asc"
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            produtos = response.json()
            if not produtos:
                send_telegram_message(chat_id, "📦 Estoque vazio.")
                return
            msg = "*📦 RESUMO DO ESTOQUE*\n\n"
            for p in produtos:
                emoji = "❄️" if p["is_cold"] else "🌡️"
                msg += f"{emoji} *{p['product_name']}*: {p['quantity']} un\n"
            send_telegram_message(chat_id, msg)
        else:
            send_telegram_message(chat_id, f"❌ Erro: {response.status_code}")
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Erro: {str(e)}")

def process_estoque_completo(chat_id: int):
    try:
        headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
        url = f"{SUPABASE_URL}/rest/v1/inventory?order=product_name.asc"
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            produtos = response.json()
            if not produtos:
                send_telegram_message(chat_id, "📦 Estoque vazio!")
                return
            msg = "*📦 ESTOQUE COMPLETO*\n\n"
            for p in produtos:
                gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                msg += (f"🍺 *{p['product_name']}*\n"
                       f"   🏷️ {p['brand']} | 📏 {p['volume_ml']}ml\n"
                       f"   📦 {p['quantity']} un | 💰 R$ {p['price_cents']/100:.2f}\n"
                       f"   {gelado}\n\n")
            if len(msg) > 4000:
                msg = msg[:4000] + "\n\n... (mais produtos)"
            send_telegram_message(chat_id, msg)
        else:
            send_telegram_message(chat_id, f"❌ Erro: {response.status_code}")
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Erro: {str(e)}")

# ========== TECLADOS ==========
def build_main_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📦 Resumo do Estoque", "callback_data": "estoque_resumo"},
             {"text": "📋 Estoque Completo", "callback_data": "estoque_completo"}],
            [{"text": "🔍 Consultar Produto", "callback_data": "consultar_produto"},
             {"text": "❓ Ajuda", "callback_data": "ajuda"}]
        ]
    }

def build_produtos_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🍺 Heineken", "callback_data": "produto|Heineken"},
             {"text": "🍺 Original", "callback_data": "produto|Original"}],
            [{"text": "🍺 Brahma", "callback_data": "produto|Brahma"},
             {"text": "🍺 Skol", "callback_data": "produto|Skol"}],
            [{"text": "🍺 Stella Artois", "callback_data": "produto|Stella Artois"},
             {"text": "🍺 Colorado", "callback_data": "produto|Colorado"}],
            [{"text": "🔍 Digitar outro...", "callback_data": "digitar_produto"},
             {"text": "🔙 Voltar", "callback_data": "menu_principal"}]
        ]
    }

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

        # ========== COMANDOS ==========
        if text == "/menu" or text == "/start":
            send_telegram_message(chat_id, "🤖 *Menu Principal*\n\nEscolha uma opção:", reply_markup=build_main_keyboard())
            return {"ok": True}

        elif text == "/estoque_resumo":
            background_tasks.add_task(process_estoque_resumo, chat_id)
            return {"ok": True}

        elif text == "/estoque_completo":
            background_tasks.add_task(process_estoque_completo, chat_id)
            return {"ok": True}

        elif text.startswith("/estoque"):
            product = text.replace("/estoque", "").strip()
            if product:
                background_tasks.add_task(process_inventory_query, chat_id, product)
            else:
                send_telegram_message(chat_id, "Use: /estoque <produto>")
            return {"ok": True}

        # ========== CALLBACKS ==========
        elif "callback_query" in body:
            cb = body["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            data = cb["data"]
            callback_id = cb["id"]
            
            print(f"Callback: {data}")
            answer_callback(callback_id)
            
            if data == "estoque_resumo":
                background_tasks.add_task(process_estoque_resumo, chat_id)
            elif data == "estoque_completo":
                background_tasks.add_task(process_estoque_completo, chat_id)
            elif data == "consultar_produto":
                send_telegram_message(chat_id, "🔍 *Consultar Produto*\n\nEscolha um produto:", reply_markup=build_produtos_keyboard())
            elif data.startswith("produto|"):
                produto = data.split("|")[1]
                background_tasks.add_task(process_inventory_query, chat_id, produto)
            elif data == "digitar_produto":
                send_telegram_message(chat_id, "📝 Digite o nome do produto (ex: Heineken):")
            elif data == "ajuda":
                send_telegram_message(chat_id, "🤖 *Comandos*\n\n/menu - Abrir menu\n/estoque <produto> - Consultar\n/estoque_resumo - Resumo\n/estoque_completo - Completo")
            elif data == "menu_principal":
                send_telegram_message(chat_id, "🤖 *Menu Principal*", reply_markup=build_main_keyboard())
            
            return {"ok": True}

        # ========== PERGUNTAS NATURAIS ==========
        else:
            palavras_chave = ["tem", "estoque", "possui", "disponível", "tem gelada"]
            palavras_produtos = ["heineken", "original", "brahma", "skol", "stella", "colorado", "eisenbahn"]
            mensagem = text.lower()
            eh_pergunta = any(p in mensagem for p in palavras_chave)
            produto = next((p for p in palavras_produtos if p in mensagem), None)
            
            if eh_pergunta and produto:
                background_tasks.add_task(process_inventory_query, chat_id, produto)
            else:
                send_telegram_message(chat_id, "🤖 *Assistente*\n\n/menu - Abrir menu\n/estoque <produto> - Consultar")

    except Exception as e:
        print(f"Erro: {e}")
    
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}