from fastapi import FastAPI, HTTPException, Request
import os
import requests
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Gateway MCP para Varejo - Caso 1")

# ========== CONFIGURAÇÕES ==========
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
AUTO_APPROVE_SECRET = os.getenv("AUTO_APPROVE_SECRET", "segredo-padrao-mude")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0"))

# ========== FUNÇÕES AUXILIARES ==========
def send_telegram_message(chat_id: int, text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def query_supabase(table: str, params: dict = None):
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    if resp.status_code != 200:
        raise Exception(f"Erro na consulta Supabase: {resp.text}")
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
async def check_inventory(product_name: str, secret: str):
    if secret != AUTO_APPROVE_SECRET:
        raise HTTPException(403, "Secret inválido")

    try:
        results = query_supabase("inventory", params={"product_name": f"eq.{product_name}"})
        if not results:
            return {"found": False, "message": f"Produto '{product_name}' não encontrado."}

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

    if chat_id != ADMIN_CHAT_ID:
        print(f"Chat não autorizado: {chat_id}")
        return {"ok": True}

    if text.startswith("/estoque"):
        product = text.replace("/estoque", "").strip()
        if not product:
            send_telegram_message(chat_id, "Use: /estoque <nome do produto>")
        else:
            proxy_url = os.getenv("PROXY_URL", "https://gateway-mcp-varejo.onrender.com")
            try:
                resp = requests.post(
                    f"{proxy_url}/inventory/check",
                    params={"product_name": product, "secret": AUTO_APPROVE_SECRET},
                    timeout=10
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data["found"]:
                        cold_status = "🌡️ **Gelada**" if data["is_cold"] else "❄️ **Ambiente**"
                        msg = (f"🍺 *{data['product']}*\n"
                               f"{cold_status}\n"
                               f"📦 Estoque: {data['quantity']} unidades\n"
                               f"💰 Preço: {data['price']}")
                    else:
                        msg = data["message"]
                else:
                    msg = "❌ Erro ao consultar estoque. Tente novamente."
            except Exception as e:
                msg = f"❌ Erro: {str(e)}"
            send_telegram_message(chat_id, msg)
    else:
        send_telegram_message(chat_id, "Comando não reconhecido. Use /estoque <produto>")

    return {"ok": True}
