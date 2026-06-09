from fastapi import FastAPI, HTTPException, Request
import os
import requests
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env, se existir
load_dotenv()

app = FastAPI(title="Gateway MCP para Varejo - Caso 1")

# ========== CONFIGURAÇÕES COM TRATAMENTO DE ERRO ==========
# Lê as variáveis de ambiente com valores padrão seguros
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
AUTO_APPROVE_SECRET = os.getenv("AUTO_APPROVE_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Tratamento especial para ADMIN_CHAT_ID: se não existir ou for inválido, assume 0
admin_chat_id_str = os.getenv("ADMIN_CHAT_ID", "0")
try:
    ADMIN_CHAT_ID = int(admin_chat_id_str)
except ValueError:
    print(f"ERRO: ADMIN_CHAT_ID com valor inválido: '{admin_chat_id_str}'. Usando 0 (nenhum administrador).")
    ADMIN_CHAT_ID = 0

# ========== FUNÇÕES AUXILIARES ==========
def send_telegram_message(chat_id: int, text: str):
    """Envia mensagem para um chat específico do Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        print("ERRO: TELEGRAM_BOT_TOKEN não configurado.")
        return
    if not chat_id:
        print("ERRO: chat_id inválido para enviar mensagem.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code != 200:
            print(f"Falha ao enviar mensagem: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def query_supabase(table: str, params: dict = None):
    """Consulta genérica ao Supabase REST API."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise Exception("SUPABASE_URL ou SUPABASE_SERVICE_KEY não configurados")
    
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
    }
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status() # Lança exceção para códigos de erro HTTP
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro na consulta Supabase: {e}")
        if e.response:
            print(f"Resposta do Supabase: {e.response.text}")
        raise Exception(f"Erro na consulta Supabase: {str(e)}")

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
    if not AUTO_APPROVE_SECRET or secret != AUTO_APPROVE_SECRET:
        raise HTTPException(403, "Secret inválido ou não configurado")

    try:
        # Consulta o Supabase filtrando pelo nome do produto
        results = query_supabase("inventory", params={"product_name": f"eq.{product_name}"})
        
        if not results:
            return {"found": False, "message": f"Produto '{product_name}' não encontrado no estoque."}

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
        print(f"Erro interno em /inventory/check: {e}")
        raise HTTPException(500, f"Erro interno ao consultar estoque: {str(e)}")

# ========== WEBHOOK DO TELEGRAM (SIMPLIFICADO) ==========
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

        # Verifica se o chat_id é o administrador configurado
        if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
            print(f"Chat não autorizado: {chat_id}. ADMIN_CHAT_ID configurado: {ADMIN_CHAT_ID}")
            return {"ok": True}

        if text.startswith("/estoque"):
            product = text.replace("/estoque", "").strip()
            if not product:
                await send_telegram_message(chat_id, "Use: /estoque <nome do produto>")
                return {"ok": True}
            
            # Determina a URL do proxy (usa variável de ambiente ou a URL base da requisição)
            proxy_url = os.getenv("PROXY_URL")
            if not proxy_url:
                # Fallback para construir a URL a partir da requisição recebida
                forwarded_host = request.headers.get("X-Forwarded-Host")
                if forwarded_host:
                    proxy_url = f"https://{forwarded_host}"
                else:
                    proxy_url = "https://gateway-mcp-varejo.onrender.com" # URL padrão
            
            inventory_url = f"{proxy_url}/inventory/check"
            params = {"product_name": product, "secret": AUTO_APPROVE_SECRET}
            
            try:
                response = requests.post(inventory_url, params=params, timeout=15)
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
                elif response.status_code == 403:
                    msg = "❌ Erro de autenticação. Contate o administrador."
                else:
                    msg = f"❌ Erro ao consultar estoque. Status: {response.status_code}"
                    try:
                        error_detail = response.json()
                        msg += f"\nDetalhe: {error_detail.get('detail', 'Erro desconhecido')}"
                    except:
                        pass
            except requests.exceptions.Timeout:
                msg = "❌ Tempo limite excedido ao consultar estoque. Tente novamente."
            except Exception as e:
                msg = f"❌ Erro interno: {str(e)}"
            
            await send_telegram_message(chat_id, msg)
        else:
            await send_telegram_message(chat_id, "Comando não reconhecido. Use /estoque <produto>")

    except Exception as e:
        print(f"Erro geral no webhook: {e}")
    
    return {"ok": True}

# ========== INICIALIZAÇÃO ==========
@app.on_event("startup")
async def startup_event():
    """Verifica configurações críticas ao iniciar."""
    print("="*50)
    print("Iniciando Gateway MCP para Varejo - Caso 1")
    print("="*50)
    
    # Lista as variáveis configuradas (sem expor os valores)
    config_status = {
        "SUPABASE_URL": "✅" if SUPABASE_URL else "❌",
        "SUPABASE_SERVICE_KEY": "✅" if SUPABASE_SERVICE_KEY else "❌",
        "AUTO_APPROVE_SECRET": "✅" if AUTO_APPROVE_SECRET else "❌",
        "TELEGRAM_BOT_TOKEN": "✅" if TELEGRAM_BOT_TOKEN else "❌",
        "ADMIN_CHAT_ID": f"✅ ({ADMIN_CHAT_ID})" if ADMIN_CHAT_ID != 0 else "❌ (0)",
    }
    
    for key, status in config_status.items():
        print(f"{key}: {status}")
    
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("ERRO: Configuração do Supabase incompleta. O serviço pode não funcionar.")
    
    if not AUTO_APPROVE_SECRET:
        print("ERRO: AUTO_APPROVE_SECRET não configurado. O endpoint /inventory/check não funcionará.")
    
    if not TELEGRAM_BOT_TOKEN:
        print("ERRO: TELEGRAM_BOT_TOKEN não configurado. O webhook do Telegram não funcionará.")
    
    if ADMIN_CHAT_ID == 0:
        print("AVISO: ADMIN_CHAT_ID não configurado ou inválido. O bot não responderá a comandos.")
    
    print("="*50)