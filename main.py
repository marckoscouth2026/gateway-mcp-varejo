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

# ========== MODELOS ==========
class InventoryRequest(BaseModel):
    product_name: str
    secret: str

# ========== FUNÇÕES ==========
def send_telegram_message(chat_id: int, text: str):
    """Envia mensagem para o Telegram (chamada síncrona, mas rápida)."""
    if not TELEGRAM_BOT_TOKEN:
        print("ERRO: TELEGRAM_BOT_TOKEN não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Falha ao enviar mensagem: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def query_supabase(table: str, params: dict = None):
    """Consulta o Supabase (pode ser lenta na primeira vez)."""
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def process_inventory_query(chat_id: int, product: str):
    """Processa a consulta de estoque e envia a resposta (executada em segundo plano)."""
    try:
        # Chama o endpoint local para evitar HTTP
        if not AUTO_APPROVE_SECRET:
            send_telegram_message(chat_id, "❌ Erro de configuração: secret não definido.")
            return
        
        # Consulta direta ao Supabase (evita chamada HTTP interna)
        results = query_supabase("inventory", params={"product_name": f"eq.{product}"})
        if not results:
            send_telegram_message(chat_id, f"❌ Produto '{product}' não encontrado no estoque.")
            return
        
        product_data = results[0]
        cold_status = "🌡️ **Gelada**" if product_data["is_cold"] else "❄️ **Ambiente**"
        msg = (f"🍺 *{product_data['product_name']}*\n"
               f"{cold_status}\n"
               f"📦 Estoque: {product_data['quantity']} unidades\n"
               f"💰 Preço: R$ {product_data['price_cents']/100:.2f}")
        if product_data.get("brand"):
            msg += f"\n🏷️ Marca: {product_data['brand']}"
        if product_data.get("volume_ml"):
            msg += f"\n📏 Volume: {product_data['volume_ml']}ml"
        
        send_telegram_message(chat_id, msg)
    except Exception as e:
        error_msg = f"❌ Erro ao consultar estoque: {str(e)}"
        print(error_msg)
        send_telegram_message(chat_id, error_msg)

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

# ========== WEBHOOK DO TELEGRAM (OTIMIZADO) ==========
@app.post("/telegram/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
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

        # Verifica se o chat é autorizado
        if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
            print(f"Chat não autorizado: {chat_id}. ADMIN_CHAT_ID={ADMIN_CHAT_ID}")
            # Ainda responde 200 para o Telegram, mas não processa
            return {"ok": True}

        if text.startswith("/estoque"):
            product = text.replace("/estoque", "").strip()
            if not product:
                # Envia resposta rápida diretamente
                send_telegram_message(chat_id, "Use: /estoque <nome do produto>")
                return {"ok": True}
            
            # Processa a consulta em segundo plano para não travar o webhook
            background_tasks.add_task(process_inventory_query, chat_id, product)
        else:
            send_telegram_message(chat_id, "Comando não reconhecido. Use /estoque <produto>")

    except Exception as e:
        print(f"Erro geral no webhook: {e}")
    
    # Retorna 200 imediatamente para o Telegram (não espera a consulta terminar)
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