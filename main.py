from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
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
AUTO_APPROVE_SECRET = os.getenv("AUTO_APPROVE_SECRET", "segredo-padrao-mude")
PROXY_URL = os.getenv("PROXY_URL", "https://gateway-mcp-varejo.onrender.com")

# ========== FUNÇÕES AUXILIARES ==========
def supabase_request(endpoint: str, method: str = "GET", data: dict = None):
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": "application/json"}
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers)
        elif method == "POST":
            resp = requests.post(url, json=data, headers=headers)
        elif method == "PATCH":
            resp = requests.patch(url, json=data, headers=headers)
        else:
            return None
        return resp
    except Exception as e:
        print(f"Erro Supabase: {e}")
        return None

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro send: {e}")

# ========== ENDPOINTS DA CARTEIRA ==========
@app.post("/wallet/balance")
async def wallet_balance(agent_id: str, secret: str):
    if secret != AUTO_APPROVE_SECRET:
        raise HTTPException(403, "Secret inválido")

    resp = supabase_request(f"agent_wallets?agent_id=eq.{agent_id}")
    if resp and resp.status_code == 200 and resp.json():
        wallet = resp.json()[0]
        return {"agent_id": agent_id, "balance": wallet["balance"], "hourly_limit": wallet.get("hourly_limit", 500), "daily_limit": wallet.get("daily_limit", 5000)}

    # Se a carteira não existe, cria uma com saldo 0
    default_wallet = {
        "agent_id": agent_id,
        "balance": 0,
        "hourly_limit": 500,
        "daily_limit": 5000,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    supabase_request("agent_wallets", method="POST", data=default_wallet)
    return {"agent_id": agent_id, "balance": 0, "hourly_limit": 500, "daily_limit": 5000}

@app.post("/wallet/deposit")
async def wallet_deposit(agent_id: str, amount: int, secret: str):
    if secret != AUTO_APPROVE_SECRET:
        raise HTTPException(403, "Secret inválido")
    if amount <= 0:
        raise HTTPException(400, "Amount deve ser positivo")

    # Buscar carteira
    resp = supabase_request(f"agent_wallets?agent_id=eq.{agent_id}")
    if resp and resp.status_code == 200 and resp.json():
        wallet = resp.json()[0]
        new_balance = wallet["balance"] + amount
        update_resp = supabase_request(f"agent_wallets?agent_id=eq.{agent_id}", method="PATCH", data={"balance": new_balance, "updated_at": datetime.now().isoformat()})
        if update_resp and update_resp.status_code in (200, 204):
            return {"status": "deposited", "new_balance": new_balance}
    else:
        # Se não existe, cria com o valor do depósito
        default_wallet = {
            "agent_id": agent_id,
            "balance": amount,
            "hourly_limit": 500,
            "daily_limit": 5000,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        create_resp = supabase_request("agent_wallets", method="POST", data=default_wallet)
        if create_resp and create_resp.status_code in (200, 201):
            return {"status": "deposited", "new_balance": amount}

    raise HTTPException(500, "Erro ao processar depósito")

@app.post("/wallet/pay")
async def wallet_pay(agent_id: str, amount: int, description: str, secret: str):
    if secret != AUTO_APPROVE_SECRET:
        raise HTTPException(403, "Secret inválido")
    if amount <= 0:
        raise HTTPException(400, "Amount deve ser positivo")

    resp = supabase_request(f"agent_wallets?agent_id=eq.{agent_id}")
    if not resp or resp.status_code != 200 or not resp.json():
        raise HTTPException(404, "Carteira não encontrada")

    wallet = resp.json()[0]
    new_balance = wallet["balance"] - amount
    if new_balance < 0:
        raise HTTPException(402, "Saldo insuficiente")

    update_resp = supabase_request(f"agent_wallets?agent_id=eq.{agent_id}", method="PATCH", data={"balance": new_balance, "updated_at": datetime.now().isoformat()})
    if update_resp and update_resp.status_code in (200, 204):
        return {"status": "approved", "new_balance": new_balance, "amount": amount, "description": description}
    else:
        raise HTTPException(500, "Erro ao processar pagamento")

# ========== WEBHOOK DO TELEGRAM ==========
@app.post("/telegram/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
        print("Recebido:", body)
        # Aqui vai o código do seu webhook existente...
    except Exception as e:
        print(f"Erro geral: {e}")
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/.well-known/agent-manifest")
def manifest():
    return {"version": "0.1.0", "services": []}
