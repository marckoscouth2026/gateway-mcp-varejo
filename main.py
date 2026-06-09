from fastapi import FastAPI, HTTPException, Request
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

# ========== MODELOS ==========
class InventoryRequest(BaseModel):
    product_name: str
    secret: str

# ========== FUNÇÕES ==========
def send_telegram_message(chat_id: int, text: str):
    if not TELEGRAM_BOT_TOKEN:
        print("ERRO: TELEGRAM_BOT_TOKEN não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def query_supabase(table: str, params: dict = None):
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

# ========== ENDPOINTS ==========
@app.get("/")
def root():
    return {"status": "ok", "message": "Gateway MCP para Varejo rodando"}

@app.get("/.well-known/agent-manifest")
def manifest():
    return {
        "version": "0.1.0",
        "services": [
            {"id": "inventory", "description": "Consulta de estoque", "auth_type": "api_key"}
        ]
    }

@app.post("/inventory/check")
async def check_inventory(request: InventoryRequest):
    if not AUTO_APPROVE_SECRET or request.secret != AUTO_APPROVE_SECRET:
        raise HTTPException(403, "Secret inválido")
    try:
        results = query_supabase("inventory", params={"product_name": f"eq.{request.product_name}"})
        if not results:
            return {"found": False, "message": f"Produto '{request.product_name}' não encontrado."}
        product = results[0]
        return {
            "found": True,
            "product": product["product_name"],
            "quantity": product["quantity"],
            "price": f"R$ {product['price_cents']/100:.2f}",
            "is_cold": product["is_cold"],
            "brand": product.get("brand", ""),
            "volume_ml": product.get("volume_ml")
        }
    except Exception as e:
        raise HTTPException(500, f"Erro interno: {str(e)}")

# ========== WEBHOOK DO TELEGRAM ==========
@app.post("/telegram/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
        print("Webhook recebido:", body)

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
            print(f"Chat não autorizado: {chat_id}")
            return {"ok": True}

        if text.startswith("/estoque"):
            product = text.replace("/estoque", "").strip()
            if not product:
                await send_telegram_message(chat_id, "Use: /estoque <nome do produto>")
                return {"ok": True}
            
            proxy_url = os.getenv("PROXY_URL", "https://gateway-mcp-varejo.onrender.com")
            inventory_url = f"{proxy_url}/inventory/check"
            
            payload = {"product_name": product, "secret": AUTO_APPROVE_SECRET}
            try:
                response = requests.post(inventory_url, json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    if data["found"]:
                        cold_status = "🌡️ **Gelada**" if data["is_cold"] else "❄️ **Ambiente**"
                        msg = (f"🍺 *{data['product']}*\n"
                               f"{cold_status}\n"
                               f"📦 Estoque: {data['quantity']} unidades\n"
                               f"💰 Preço: {data['price']}")
                    else:
                        msg = data["message"]
                else:
                    msg = f"❌ Erro ao consultar estoque. Status: {response.status_code}"
            except Exception as e:
                msg = f"❌ Erro: {str(e)}"
            
            await send_telegram_message(chat_id, msg)
        else:
            await send_telegram_message(chat_id, "Comando não reconhecido. Use /estoque <produto>")

    except Exception as e:
        print(f"Erro geral no webhook: {e}")
    
    return {"ok": True}

@app.on_event("startup")
async def startup_event():
    print("="*50)
    print("Gateway MCP para Varejo - Caso 1 iniciado")
    print(f"SUPABASE_URL: {'✅' if SUPABASE_URL else '❌'}")
    print(f"SUPABASE_SERVICE_KEY: {'✅' if SUPABASE_SERVICE_KEY else '❌'}")
    print(f"AUTO_APPROVE_SECRET: {'✅' if AUTO_APPROVE_SECRET else '❌'}")
    print(f"TELEGRAM_BOT_TOKEN: {'✅' if TELEGRAM_BOT_TOKEN else '❌'}")
    print(f"ADMIN_CHAT_ID: {ADMIN_CHAT_ID}")
    print("="*50)