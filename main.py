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
    if not TELEGRAM_BOT_TOKEN:
        print("ERRO: TELEGRAM_BOT_TOKEN não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def query_supabase(table: str, params: dict = None):
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

def process_inventory_query(chat_id: int, product: str):
    try:
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
        send_telegram_message(chat_id, f"❌ Erro ao consultar estoque: {str(e)}")

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

        # Verifica se o chat é autorizado (se ADMIN_CHAT_ID estiver configurado)
          if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
            print(f"Chat não autorizado: {chat_id}")
            return {"ok": True}

        # ========== COMANDO /ESTOQUE ==========
        if text.startswith("/estoque"):
            product = text.replace("/estoque", "").strip()
            if not product:
                send_telegram_message(chat_id, "Use: /estoque <nome do produto>")
                return {"ok": True}
            background_tasks.add_task(process_inventory_query, chat_id, product)
        
        # ========== COMANDO /ADICIONAR_PRODUTO ==========
        elif text.startswith("/adicionar_produto"):
            # Verifica se é administrador (apenas o admin pode adicionar)
            if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
                send_telegram_message(chat_id, "⛔ Apenas administradores podem adicionar produtos.")
                return {"ok": True}
            
            # Formato: /adicionar_produto nome|marca|volume|quantidade|preco|gelada
            parts = text.replace("/adicionar_produto", "").strip().split("|")
            if len(parts) != 6:
                send_telegram_message(chat_id, 
                    "📝 *Formato inválido!*\n\n"
                    "Use:\n"
                    "`/adicionar_produto nome|marca|volume|quantidade|preco|gelada`\n\n"
                    "Exemplo:\n"
                    "`/adicionar_produto Heineken|Heineken|350|48|690|true`\n\n"
                    "Parâmetros:\n"
                    "• nome: Nome do produto\n"
                    "• marca: Marca (Ambev, Heineken, etc.)\n"
                    "• volume: Volume em ml\n"
                    "• quantidade: Número em estoque\n"
                    "• preco: Preço em centavos (690 = R$ 6,90)\n"
                    "• gelada: true/false"
                )
                return {"ok": True}
            
            nome, marca, volume, quantidade, preco, gelada = parts
            
            # Validações básicas
            try:
                volume_int = int(volume)
                quantidade_int = int(quantidade)
                preco_int = int(preco)
                gelada_bool = gelada.lower() == "true"
                if volume_int <= 0 or quantidade_int < 0 or preco_int <= 0:
                    raise ValueError("Valores inválidos")
            except ValueError:
                send_telegram_message(chat_id, "❌ Erro: Volume, quantidade e preço devem ser números positivos. Preço em centavos (ex: 690 = R$ 6,90).")
                return {"ok": True}
            
            # Insere no Supabase
            try:
                headers = {
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json"
                }
                data = {
                    "product_name": nome,
                    "brand": marca,
                    "volume_ml": volume_int,
                    "quantity": quantidade_int,
                    "price_cents": preco_int,
                    "is_cold": gelada_bool
                }
                url = f"{SUPABASE_URL}/rest/v1/inventory"
                response = requests.post(url, json=data, headers=headers)
                
                if response.status_code in (200, 201):
                    send_telegram_message(chat_id, 
                        f"✅ *Produto adicionado com sucesso!*\n\n"
                        f"🍺 {nome}\n"
                        f"🏷️ Marca: {marca}\n"
                        f"📏 Volume: {volume_int}ml\n"
                        f"📦 Estoque: {quantidade_int} unidades\n"
                        f"💰 Preço: R$ {preco_int/100:.2f}\n"
                        f"🌡️ {'Gelada' if gelada_bool else 'Ambiente'}"
                    )
                else:
                    send_telegram_message(chat_id, f"❌ Erro ao adicionar produto:\n{response.text}")
            except Exception as e:
                send_telegram_message(chat_id, f"❌ Erro interno: {str(e)}")
        
        else:
            send_telegram_message(chat_id, "Comando não reconhecido. Use /estoque <produto> ou /adicionar_produto ...")
    
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
