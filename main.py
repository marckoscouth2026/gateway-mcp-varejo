from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
import os
import requests
from dotenv import load_dotenv
from datetime import datetime

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

        # ========== COMANDO /ESTOQUE_COMPLETO ==========
        if text == "/estoque_completo":
            try:
                headers = {
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
                }
                url = f"{SUPABASE_URL}/rest/v1/inventory?order=product_name.asc"
                response = requests.get(url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    produtos = response.json()
                    if not produtos:
                        send_telegram_message(chat_id, "📦 *Estoque vazio!*")
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
                send_telegram_message(chat_id, f"❌ Erro interno: {str(e)}")

        # ========== COMANDO /ESTOQUE_RESUMO ==========
        elif text == "/estoque_resumo":
            try:
                headers = {
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"
                }
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
                send_telegram_message(chat_id, f"❌ Erro interno: {str(e)}")

        # ========== COMANDO /ADICIONAR_PRODUTO ==========
        elif text.startswith("/adicionar_produto"):
            if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
                send_telegram_message(chat_id, "⛔ Apenas administradores podem adicionar produtos.")
                return {"ok": True}
            
            parts_raw = text.replace("/adicionar_produto", "").strip().split("|")
            parts = [p.strip() for p in parts_raw]
            
            if len(parts) != 6:
                send_telegram_message(chat_id, 
                    "📝 *Formato inválido!*\n\n"
                    "Use:\n"
                    "`/adicionar_produto nome|marca|volume|quantidade|preco|gelada`\n\n"
                    "Exemplo:\n"
                    "`/adicionar_produto Heineken|Heineken|350|48|690|true`"
                )
                return {"ok": True}
            
            nome, marca, volume, quantidade, preco, gelada = parts
            
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
            
            # Verificar se produto já existe
            headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
            check_url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=eq.{nome}"
            check_response = requests.get(check_url, headers=headers)
            
            if check_response.status_code == 200 and check_response.json():
                send_telegram_message(chat_id, f"⚠️ Produto '{nome}' já existe no estoque. Use `/atualizar_estoque {nome}|+X` para adicionar unidades.")
                return {"ok": True}
            
            # Insere no Supabase
            try:
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

        # ========== COMANDO /ATUALIZAR_ESTOQUE ==========
        elif text.startswith("/atualizar_estoque"):
            if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
                send_telegram_message(chat_id, "⛔ Apenas administradores podem atualizar o estoque.")
                return {"ok": True}
            
            resto = text.replace("/atualizar_estoque", "").strip()
            if "|" not in resto:
                send_telegram_message(chat_id, 
                    "📝 *Formato inválido!*\n\n"
                    "Use:\n"
                    "`/atualizar_estoque produto|+10`\n\n"
                    "Exemplo:\n"
                    "`/atualizar_estoque Heineken|+5`"
                )
                return {"ok": True}
            
            parts = [p.strip() for p in resto.split("|")]
            if len(parts) != 2:
                send_telegram_message(chat_id, "Formato inválido. Use: `/atualizar_estoque produto|+10`")
                return {"ok": True}
            
            nome = parts[0].strip()
            operacao = parts[1].strip()
            
            try:
                if not (operacao.startswith("+") or operacao.startswith("-")):
                    raise ValueError("Use + ou - antes do número")
                
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
                    send_telegram_message(chat_id, f"❌ Estoque não pode ficar negativo. Atual: {produto['quantity']} unidades.")
                    return {"ok": True}
                
                update_url = f"{SUPABASE_URL}/rest/v1/inventory?id=eq.{produto['id']}"
                update_data = {"quantity": nova_quantidade}
                update_response = requests.patch(update_url, json=update_data, headers=headers)
                
                if update_response.status_code in (200, 204):
                    sinal = "adicionadas" if delta > 0 else "removidas"
                    send_telegram_message(chat_id, 
                        f"✅ *Estoque atualizado*\n\n"
                        f"🍺 {nome}\n"
                        f"📦 {abs(delta)} unidades {sinal}\n"
                        f"📊 Novo estoque: {nova_quantidade} unidades"
                    )
                else:
                    send_telegram_message(chat_id, f"❌ Erro ao atualizar estoque: {update_response.text}")
            except ValueError as e:
                send_telegram_message(chat_id, f"❌ Erro: {str(e)}")
            except Exception as e:
                send_telegram_message(chat_id, f"❌ Erro interno: {str(e)}")

        # ========== COMANDO /RESERVAR ==========
        elif text.startswith("/reservar"):
            if ADMIN_CHAT_ID != 0 and chat_id != ADMIN_CHAT_ID:
                send_telegram_message(chat_id, "⛔ Apenas administradores podem fazer reservas.")
                return {"ok": True}
            
            parts = text.replace("/reservar", "").strip().split()
            if len(parts) != 2:
                send_telegram_message(chat_id, "Use: `/reservar <produto> <quantidade>`")
                return {"ok": True}
            
            produto, qtd = parts
            try:
                qtd_int = int(qtd)
                if qtd_int <= 0:
                    raise ValueError
            except ValueError:
                send_telegram_message(chat_id, "Quantidade inválida. Use um número positivo.")
                return {"ok": True}
            
            headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
            check_url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=eq.{produto}"
            response = requests.get(check_url, headers=headers)
            
            if response.status_code != 200 or not response.json():
                send_telegram_message(chat_id, f"❌ Produto '{produto}' não encontrado.")
                return {"ok": True}
            
            produto_data = response.json()[0]
            if produto_data["quantity"] < qtd_int:
                send_telegram_message(chat_id, f"😔 Desculpe, só temos {produto_data['quantity']} unidades de {produto} no momento.")
                return {"ok": True}
            
            # Registra reserva (simples - apenas confirma)
            send_telegram_message(chat_id, 
                f"✅ *Reserva confirmada!*\n\n"
                f"🍺 {produto} x {qtd_int} unidades\n"
                f"💰 Total: R$ {produto_data['price_cents']/100 * qtd_int:.2f}\n\n"
                f"📌 Sua reserva está garantida. Passe na loja para retirar.")

        # ========== COMANDO /ESTOQUE (produto específico) ==========
        elif text.startswith("/estoque"):
            product = text.replace("/estoque", "").strip()
            if not product:
                send_telegram_message(chat_id, "Use: /estoque <nome do produto>")
                return {"ok": True}
            background_tasks.add_task(process_inventory_query, chat_id, product)

        # ========== PROCESSAMENTO DE MENSAGENS EM LINGUAGEM NATURAL ==========
        else:
            # Lista de palavras-chave para identificar pergunta de estoque
            palavras_estoque = ["tem", "estoque", "possui", "disponível", "tem gelada", "cerveja", "cervejas"]
            palavras_produto = ["heineken", "original", "brahma", "skol", "budweiser", "stella", "colorado", "eisenbahn"]
            
            mensagem_lower = text.lower()
            
            # Verifica se a mensagem parece uma pergunta sobre estoque
            eh_pergunta_estoque = any(palavra in mensagem_lower for palavra in palavras_estoque)
            produto_mencionado = None
            
            # Tenta encontrar um produto conhecido na mensagem
            for produto in palavras_produto:
                if produto in mensagem_lower:
                    produto_mencionado = produto.capitalize()
                    break
            
            if eh_pergunta_estoque and produto_mencionado:
                # Cliente perguntou sobre um produto que temos no estoque
                try:
                    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                    check_url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=eq.{produto_mencionado}"
                    response = requests.get(check_url, headers=headers, timeout=10)
                    
                    if response.status_code == 200 and response.json():
                        produto = response.json()[0]
                        quantidade = produto["quantity"]
                        preco = produto["price_cents"] / 100
                        gelada = "gelada" if produto["is_cold"] else "ambiente"
                        
                        if quantidade > 0:
                            msg = (
                                f"🍺 *{produto['product_name']}* {gelada}\n\n"
                                f"✅ *Sim, temos!*\n"
                                f"📦 Estoque: {quantidade} unidades\n"
                                f"💰 Preço: R$ {preco:.2f}\n\n"
                                f"📝 Deseja reservar? Envie `/reservar {produto['product_name']} {quantidade}`\n"
                                f"Ou digite a quantidade desejada."
                            )
                        else:
                            msg = f"😔 *{produto['product_name']}* {gelada}\n\n❌ Infelizmente está esgotado no momento.\nEstamos aguardando novo lote!"
                        
                        send_telegram_message(chat_id, msg)
                    else:
                        send_telegram_message(chat_id, f"😔 Desculpe, não encontrei *{produto_mencionado}* no nosso estoque.\n\nUse `/estoque {produto_mencionado}` para verificar ou tente outro produto.")
                except Exception as e:
                    send_telegram_message(chat_id, f"❌ Erro ao consultar estoque. Tente novamente.\n\nUse `/estoque {produto_mencionado}`.")
            else:
                # Mensagem não reconhecida
                send_telegram_message(chat_id, 
                    "🤖 *Olá! Sou o assistente virtual da loja.*\n\n"
                    "Você pode:\n"
                    "• Perguntar sobre um produto (ex: 'tem Heineken?')\n"
                    "• Usar `/estoque <produto>` para consultar\n"
                    "• Usar `/estoque_resumo` para ver todos os produtos\n"
                    "• Fazer uma reserva com `/reservar <produto> <quantidade>`\n\n"
                    "Em breve teremos mais funcionalidades!")

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
