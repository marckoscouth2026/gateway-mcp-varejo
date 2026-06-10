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
        print("ERRO: TELEGRAM_BOT_TOKEN não configurado.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

def query_supabase(table: str, params: dict = None):
    """Consulta o Supabase."""
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

# ========== FUNÇÕES DE PROCESSAMENTO ==========
def process_inventory_query(chat_id: int, product: str):
    """Consulta produto específico."""
    try:
        results = query_supabase("inventory", params={"product_name": f"ilike.*{product}*"})
        if not results:
            send_telegram_message(chat_id, f"❌ Produto '{product}' não encontrado no estoque.")
            return
        
        if len(results) > 1:
            msg = f"🔍 *Produtos encontrados para '{product}':*\n\n"
            for p in results:
                gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                msg += f"🍺 *{p['product_name']}* - {p['quantity']} un | R$ {p['price_cents']/100:.2f} | {gelado}\n"
            send_telegram_message(chat_id, msg)
        else:
            p = results[0]
            cold_status = "🌡️ **Gelada**" if p["is_cold"] else "❄️ **Ambiente**"
            msg = (f"🍺 *{p['product_name']}* {cold_status}\n"
                   f"📦 Estoque: {p['quantity']} unidades\n"
                   f"💰 Preço: R$ {p['price_cents']/100:.2f}")
            if p.get("brand"):
                msg += f"\n🏷️ Marca: {p['brand']}"
            if p.get("volume_ml"):
                msg += f"\n📏 Volume: {p['volume_ml']}ml"
            send_telegram_message(chat_id, msg)
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Erro ao consultar estoque: {str(e)}")

def process_estoque_resumo(chat_id: int):
    """Envia resumo do estoque (nome + quantidade)."""
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
                gelado_emoji = "❄️" if p["is_cold"] else "🌡️"
                msg += f"{gelado_emoji} *{p['product_name']}*: {p['quantity']} un\n"
            send_telegram_message(chat_id, msg)
        else:
            send_telegram_message(chat_id, f"❌ Erro ao buscar estoque: {response.status_code}")
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Erro interno: {str(e)}")

def process_estoque_completo(chat_id: int):
    """Envia lista completa do estoque (com detalhes)."""
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
            send_telegram_message(chat_id, f"❌ Erro ao buscar estoque: {response.status_code}")
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Erro interno: {str(e)}")

# ========== TECLADOS ==========
def build_main_keyboard():
    """Cria o teclado principal com botões."""
    return {
        "inline_keyboard": [
            [
                {"text": "📦 Resumo do Estoque", "callback_data": "estoque_resumo"},
                {"text": "📋 Estoque Completo", "callback_data": "estoque_completo"}
            ]
        ]
    }

def build_produtos_keyboard():
    """Cria o teclado de produtos populares."""
    return {
        "inline_keyboard": [
            [
                {"text": "🍺 Heineken", "callback_data": "produto|Heineken"},
                {"text": "🍺 Original", "callback_data": "produto|Original"}
            ],
            [
                {"text": "🍺 Brahma", "callback_data": "produto|Brahma"},
                {"text": "🍺 Skol", "callback_data": "produto|Skol"}
            ],
            [
                {"text": "🍺 Stella Artois", "callback_data": "produto|Stella Artois"},
                {"text": "🍺 Colorado", "callback_data": "produto|Colorado"}
            ],
            [
                {"text": "🔍 Digitar outro...", "callback_data": "digitar_produto"},
                {"text": "🔙 Voltar", "callback_data": "menu_principal"}
            ]
        ]
    }

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
async def check_inventory(request: Request):
    """Endpoint para consulta de estoque (usado pelo webhook)."""
    try:
        body = await request.json()
        product_name = body.get("product_name")
        secret = body.get("secret")
        
        if not AUTO_APPROVE_SECRET or secret != AUTO_APPROVE_SECRET:
            raise HTTPException(403, "Secret inválido")
        
        results = query_supabase("inventory", params={"product_name": f"ilike.*{product_name}*"})
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
            print(f"Chat não autorizado: {chat_id}")
            return {"ok": True}

        # ========== COMANDOS DE TEXTO ==========
        if text == "/start" or text == "/menu":
            send_telegram_message(chat_id, "🤖 *Menu Principal*\n\nEscolha uma opção:", reply_markup=build_main_keyboard())
            return {"ok": True}

        elif text == "/estoque_resumo":
            background_tasks.add_task(process_estoque_resumo, chat_id)
            return {"ok": True}

        elif text == "/estoque_completo":
            background_tasks.add_task(process_estoque_completo, chat_id)
            return {"ok": True}

        elif text.startswith("/estoque "):
            product = text.replace("/estoque ", "").strip()
            if product:
                background_tasks.add_task(process_inventory_query, chat_id, product)
            else:
                send_telegram_message(chat_id, "Use: /estoque <nome do produto>\n\nExemplo: /estoque Heineken")
            return {"ok": True}

        # ========== CALLBACK QUERIES (BOTÕES) ==========
        elif "callback_query" in body:
            cb = body["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            data = cb["data"]
            callback_id = cb["id"]
            
            print(f"Callback recebido: {data} - chat_id: {chat_id}")
            
            # Responde o callback imediatamente (remove o "loading")
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
            except Exception as e:
                print(f"Erro ao responder callback: {e}")
            
            # Processa cada ação
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
                send_telegram_message(chat_id, "📝 Digite o nome do produto que deseja consultar (ex: Heineken):")
            elif data == "menu_principal":
                send_telegram_message(chat_id, "🤖 *Menu Principal*\n\nEscolha uma opção:", reply_markup=build_main_keyboard())
            
            return {"ok": True}

        # ========== PERGUNTAS EM LINGUAGEM NATURAL ==========
        else:
            # Palavras que indicam pergunta sobre estoque
            palavras_chave = ["tem", "estoque", "possui", "disponível", "tem gelada", "cerveja"]
            palavras_produtos = ["heineken", "original", "brahma", "skol", "stella", "colorado", "eisenbahn"]
            
            mensagem = text.lower()
            eh_pergunta = any(palavra in mensagem for palavra in palavras_chave)
            
            produto_encontrado = None
            for produto in palavras_produtos:
                if produto in mensagem:
                    produto_encontrado = produto
                    break
            
            if eh_pergunta and produto_encontrado:
                background_tasks.add_task(process_inventory_query, chat_id, produto_encontrado)
            else:
                send_telegram_message(chat_id, 
                    "🤖 *Assistente da Loja*\n\n"
                    "Comandos disponíveis:\n"
                    "/menu - Abrir menu\n"
                    "/estoque <produto> - Consultar produto\n"
                    "/estoque_resumo - Resumo do estoque\n"
                    "/estoque_completo - Lista completa\n\n"
                    "Exemplo: /estoque Heineken ou digite 'tem Heineken?'")

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