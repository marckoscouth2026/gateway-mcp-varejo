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

# ========== FUNÇÕES TELEGRAM ==========
def send_telegram_message(chat_id: int, text: str, reply_markup: dict = None):
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

def answer_callback_query(callback_id: str, text: str):
    """Responde ao callback query do Telegram (feedback do botão)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id, "text": text}, timeout=5)
    except Exception as e:
        print(f"Erro answer_callback_query: {e}")

def query_supabase(table: str, params: dict = None):
    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()

# ========== FUNÇÕES DE PROCESSAMENTO ==========
def process_inventory_query(chat_id: int, product: str):
    try:
        results = query_supabase("inventory", params={"product_name": f"ilike.*{product}*"})
        if not results:
            send_telegram_message(chat_id, f"❌ Produto '{product}' não encontrado no estoque.\n\nUse /estoque_resumo para ver todos os produtos.")
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

# ========== TECLADOS (KEYBOARDS) ==========
def build_main_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "📦 Resumo do Estoque", "callback_data": "estoque_resumo"},
                {"text": "📋 Estoque Completo", "callback_data": "estoque_completo"}
            ],
            [
                {"text": "🔍 Consultar Produto", "callback_data": "consultar_produto"},
                {"text": "❓ Ajuda", "callback_data": "ajuda"}
            ]
        ]
    }

def build_produtos_keyboard():
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
async def check_inventory(request: InventoryRequest):
    if not AUTO_APPROVE_SECRET or request.secret != AUTO_APPROVE_SECRET:
        raise HTTPException(403, "Secret inválido")
    try:
        results = query_supabase("inventory", params={"product_name": f"ilike.*{request.product_name}*"})
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

        # Verifica se o chat é autorizado
        if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
            print(f"Chat não autorizado: {chat_id}")
            return {"ok": True}

        # ========== COMANDOS DE TEXTO ==========
        if text == "/start" or text == "/menu" or text == "/ajuda":
            send_telegram_message(chat_id, "🤖 *Menu Principal*\n\nEscolha uma opção:", reply_markup=build_main_keyboard())
            return {"ok": True}

        elif text == "/estoque_resumo":
            background_tasks.add_task(process_estoque_resumo, chat_id)
            return {"ok": True}

        elif text == "/estoque_completo":
            background_tasks.add_task(process_estoque_completo, chat_id)
            return {"ok": True}

        # ========== COMANDO /ESTOQUE (texto) ==========
        elif text.startswith("/estoque "):
            product = text.replace("/estoque ", "").strip()
            if product:
                background_tasks.add_task(process_inventory_query, chat_id, product)
            else:
                send_telegram_message(chat_id, "Use: /estoque <nome do produto>\n\nExemplo: /estoque Heineken")
            return {"ok": True}

        # ========== COMANDOS ADMIN ==========
        elif text.startswith("/adicionar_produto"):
            if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
                send_telegram_message(chat_id, "⛔ Apenas administradores podem adicionar produtos.")
                return {"ok": True}
            
            parts_raw = text.replace("/adicionar_produto", "").strip().split("|")
            parts = [p.strip() for p in parts_raw]
            
            if len(parts) != 6:
                send_telegram_message(chat_id, "Formato inválido. Use:\n/adicionar_produto nome|marca|volume|quantidade|preco|gelada\nEx: /adicionar_produto Heineken|Heineken|350|48|690|true")
                return {"ok": True}
            
            nome, marca, volume, quantidade, preco, gelada = parts
            
            try:
                volume_int = int(volume)
                quantidade_int = int(quantidade)
                preco_int = int(preco)
                gelada_bool = gelada.lower() == "true"
            except ValueError:
                send_telegram_message(chat_id, "❌ Erro: Volume, quantidade e preço devem ser números. Preço em centavos (ex: 690 = R$ 6,90).")
                return {"ok": True}
            
            headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": "application/json"}
            check_url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=eq.{nome}"
            check_response = requests.get(check_url, headers=headers)
            
            if check_response.status_code == 200 and check_response.json():
                send_telegram_message(chat_id, f"⚠️ Produto '{nome}' já existe. Use /atualizar_estoque {nome}|+X")
                return {"ok": True}
            
            data = {
                "product_name": nome,
                "brand": marca,
                "volume_ml": volume_int,
                "quantity": quantidade_int,
                "price_cents": preco_int,
                "is_cold": gelada_bool
            }
            response = requests.post(f"{SUPABASE_URL}/rest/v1/inventory", json=data, headers=headers)
            
            if response.status_code in (200, 201):
                send_telegram_message(chat_id, f"✅ Produto '{nome}' adicionado com sucesso!")
            else:
                send_telegram_message(chat_id, f"❌ Erro: {response.text}")
            return {"ok": True}

        elif text.startswith("/atualizar_estoque"):
            if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
                send_telegram_message(chat_id, "⛔ Apenas administradores podem atualizar o estoque.")
                return {"ok": True}
            
            resto = text.replace("/atualizar_estoque", "").strip()
            if "|" not in resto:
                send_telegram_message(chat_id, "Formato inválido. Use: /atualizar_estoque produto|+10")
                return {"ok": True}
            
            parts = [p.strip() for p in resto.split("|")]
            if len(parts) != 2:
                send_telegram_message(chat_id, "Formato inválido. Use: /atualizar_estoque produto|+10")
                return {"ok": True}
            
            nome, operacao = parts
            
            try:
                if not (operacao.startswith("+") or operacao.startswith("-")):
                    raise ValueError("Use + ou -")
                delta = int(operacao)
                
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                check_url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=eq.{nome}"
                response = requests.get(check_url, headers=headers)
                
                if response.status_code != 200 or not response.json():
                    send_telegram_message(chat_id, f"❌ Produto '{nome}' não encontrado.")
                    return {"ok": True}
                
                produto = response.json()[0]
                nova_quantidade = produto["quantity"] + delta
                if nova_quantidade < 0:
                    send_telegram_message(chat_id, f"❌ Estoque não pode ficar negativo. Atual: {produto['quantity']}")
                    return {"ok": True}
                
                update_response = requests.patch(f"{SUPABASE_URL}/rest/v1/inventory?id=eq.{produto['id']}", json={"quantity": nova_quantidade}, headers=headers)
                
                if update_response.status_code in (200, 204):
                    sinal = "adicionadas" if delta > 0 else "removidas"
                    send_telegram_message(chat_id, f"✅ Estoque de '{nome}' atualizado: {abs(delta)} unidades {sinal}. Novo estoque: {nova_quantidade}")
                else:
                    send_telegram_message(chat_id, f"❌ Erro ao atualizar: {update_response.text}")
            except Exception as e:
                send_telegram_message(chat_id, f"❌ Erro: {str(e)}")
            return {"ok": True}

               # ========== CALLBACK QUERIES (CLIQUES NOS BOTÕES) ==========
        elif "callback_query" in body:
            cb = body["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            data = cb["data"]
            callback_id = cb["id"]
            
            print(f"Callback recebido: {data}")
            
            # Responde o callback imediatamente (remove o "loading")
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
            except Exception as e:
                print(f"Erro ao responder callback: {e}")
            
            # Processa cada ação DIRETAMENTE (sem background tasks)
            if data == "estoque_resumo":
                try:
                    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                    url = f"{SUPABASE_URL}/rest/v1/inventory?order=product_name.asc"
                    response = requests.get(url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        produtos = response.json()
                        if not produtos:
                            send_telegram_message(chat_id, "📦 Estoque vazio.")
                            return {"ok": True}
                        
                        msg = "*📦 RESUMO DO ESTOQUE*\n\n"
                        for p in produtos:
                            gelado_emoji = "❄️" if p["is_cold"] else "🌡️"
                            msg += f"{gelado_emoji} *{p['product_name']}*: {p['quantity']} un\n"
                        send_telegram_message(chat_id, msg)
                    else:
                        send_telegram_message(chat_id, f"❌ Erro ao buscar estoque: {response.status_code}")
                except Exception as e:
                    send_telegram_message(chat_id, f"❌ Erro: {str(e)}")
            
            elif data == "estoque_completo":
                try:
                    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                    url = f"{SUPABASE_URL}/rest/v1/inventory?order=product_name.asc"
                    response = requests.get(url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        produtos = response.json()
                        if not produtos:
                            send_telegram_message(chat_id, "📦 Estoque vazio!")
                            return {"ok": True}
                        
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
                    send_telegram_message(chat_id, f"❌ Erro: {str(e)}")
            
            elif data == "consultar_produto":
                keyboard = {
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
                send_telegram_message(chat_id, "🔍 *Consultar Produto*\n\nEscolha um produto:", reply_markup=keyboard)
            
            elif data.startswith("produto|"):
                produto = data.split("|")[1]
                # Consulta o produto diretamente
                try:
                    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                    url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=ilike.*{produto}*"
                    response = requests.get(url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        produtos = response.json()
                        if not produtos:
                            send_telegram_message(chat_id, f"❌ Produto '{produto}' não encontrado.")
                            return {"ok": True}
                        
                        if len(produtos) > 1:
                            msg = f"🔍 *Produtos encontrados para '{produto}':*\n\n"
                            for p in produtos:
                                gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                                msg += f"🍺 *{p['product_name']}* - {p['quantity']} un | R$ {p['price_cents']/100:.2f} | {gelado}\n"
                            send_telegram_message(chat_id, msg)
                        else:
                            p = produtos[0]
                            cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                            msg = (f"🍺 *{p['product_name']}* {cold}\n"
                                   f"📦 Estoque: {p['quantity']} un\n"
                                   f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                            if p.get("brand"):
                                msg += f"\n🏷️ Marca: {p['brand']}"
                            if p.get("volume_ml"):
                                msg += f"\n📏 Volume: {p['volume_ml']}ml"
                            send_telegram_message(chat_id, msg)
                    else:
                        send_telegram_message(chat_id, f"❌ Erro: {response.status_code}")
                except Exception as e:
                    send_telegram_message(chat_id, f"❌ Erro: {str(e)}")
            
            elif data == "digitar_produto":
                send_telegram_message(chat_id, "📝 Digite o nome do produto que deseja consultar (ex: Heineken):")
            
            elif data == "ajuda":
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "📦 Resumo", "callback_data": "estoque_resumo"},
                         {"text": "📋 Completo", "callback_data": "estoque_completo"}],
                        [{"text": "🔍 Consultar", "callback_data": "consultar_produto"},
                         {"text": "🔙 Voltar", "callback_data": "menu_principal"}]
                    ]
                }
                send_telegram_message(chat_id, 
                    "🤖 *Comandos disponíveis*\n\n"
                    "• /estoque <produto> - Consultar\n"
                    "• /estoque_resumo - Resumo\n"
                    "• /estoque_completo - Completo",
                    reply_markup=keyboard)
            
            elif data == "menu_principal":
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "📦 Resumo do Estoque", "callback_data": "estoque_resumo"},
                         {"text": "📋 Estoque Completo", "callback_data": "estoque_completo"}],
                        [{"text": "🔍 Consultar Produto", "callback_data": "consultar_produto"},
                         {"text": "❓ Ajuda", "callback_data": "ajuda"}]
                    ]
                }
                send_telegram_message(chat_id, "🤖 *Menu Principal*\n\nEscolha uma opção:", reply_markup=keyboard)
            
            return {"ok": True}
        # ========== PROCESSAMENTO DE MENSAGENS EM LINGUAGEM NATURAL ==========
        else:
            palavras_estoque = ["tem", "estoque", "possui", "disponível", "tem gelada", "cerveja", "cervejas"]
            palavras_produto = ["heineken", "original", "brahma", "skol", "budweiser", "stella", "colorado", "eisenbahn"]
            
            mensagem_lower = text.lower()
            eh_pergunta_estoque = any(palavra in mensagem_lower for palavra in palavras_estoque)
            produto_mencionado = None
            
            for produto in palavras_produto:
                if produto in mensagem_lower:
                    produto_mencionado = produto.capitalize()
                    break
            
            if eh_pergunta_estoque and produto_mencionado:
                background_tasks.add_task(process_inventory_query, chat_id, produto_mencionado)
            else:
                send_telegram_message(chat_id, 
                    "🤖 *Olá! Sou o assistente virtual da loja.*\n\n"
                    "Você pode usar os botões abaixo ou digitar:\n"
                    "• /estoque <produto> - consultar\n"
                    "• /estoque_resumo - resumo\n"
                    "• /estoque_completo - lista completa",
                    reply_markup=build_main_keyboard())

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
