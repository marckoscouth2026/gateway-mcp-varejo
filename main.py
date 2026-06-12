from fastapi import FastAPI, Request
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

def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro send: {e}")

def answer_callback(callback_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
    except Exception:
        pass

def consultar_supabase(chat_id, endpoint):
    try:
        headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
        url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        else:
            send_message(chat_id, f"❌ Erro {resp.status_code}")
            return None
    except Exception as e:
        send_message(chat_id, f"❌ Erro: {str(e)}")
        return None

# ========== TECLADOS ==========
def cliente_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📦 RESUMO", "callback_data": "resumo"},
             {"text": "📋 COMPLETO", "callback_data": "completo"}],
            [{"text": "🍺 HEINEKEN", "callback_data": "heineken"},
             {"text": "🍺 STELLA", "callback_data": "stella"}],
            [{"text": "🍺 ORIGINAL", "callback_data": "original"},
             {"text": "🍺 BRAHMA", "callback_data": "brahma"}],
            [{"text": "🍺 SKOL", "callback_data": "skol"},
             {"text": "🍺 COLORADO", "callback_data": "colorado"}],
            [{"text": "🔧 ADMIN", "callback_data": "admin"}]
        ]
    }

def admin_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "➕ ADICIONAR PRODUTO", "callback_data": "adicionar"}],
            [{"text": "📦 ATUALIZAR ESTOQUE", "callback_data": "atualizar"}],
            [{"text": "📊 EXPORTAR ESTOQUE", "callback_data": "exportar"}],
            [{"text": "🔙 VOLTAR", "callback_data": "voltar"}]
        ]
    }

@app.post("/telegram/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
        print("Recebido:", body)

        chat_id = None
        if "message" in body:
            chat_id = body["message"]["chat"]["id"]
            text = body["message"].get("text", "")
            
            if text == "/menu" or text == "/start":
                send_message(chat_id, "🤖 *MENU CLIENTE*", reply_markup=cliente_keyboard())
                        # ========== PERGUNTAS EM LINGUAGEM NATURAL ==========
        # Se não é comando e não é callback, tenta interpretar como pergunta
        if "message" in body and chat_id:
            text = body["message"].get("text", "")
            if text and not text.startswith("/"):
                palavras_chave = ["tem", "estoque", "possui", "disponível", "tem gelada", "cerveja"]
                palavras_produtos = ["heineken", "stella", "original", "brahma", "skol", "colorado"]
                
                mensagem = text.lower()
                eh_pergunta = any(p in mensagem for p in palavras_chave)
                produto_encontrado = None
                
                for produto in palavras_produtos:
                    if produto in mensagem:
                        produto_encontrado = produto
                        break
                
                if eh_pergunta and produto_encontrado:
                    # Busca o produto no Supabase
                    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                    url = f"{SUPABASE_URL}/rest/v1/inventory?product_name=ilike.*{produto_encontrado}*"
                    resp = requests.get(url, headers=headers, timeout=10)
                    
                    if resp.status_code == 200 and resp.json():
                        p = resp.json()[0]
                        cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                        msg = (f"🍺 *{p['product_name']}* {cold}\n"
                               f"📦 Estoque: {p['quantity']} un\n"
                               f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                        send_message(chat_id, msg)
                    else:
                        send_message(chat_id, f"❌ Produto '{produto_encontrado}' não encontrado.")
                    return {"ok": True}
                return {"ok": True}
            
            # ========== COMANDO EXPORTAR (texto) ==========
            if text == "/exportar_estoque" and chat_id == ADMIN_CHAT_ID:
                produtos = consultar_supabase(chat_id, "inventory?order=product_name.asc")
                if produtos:
                    csv_data = "produto,marca,volume,quantidade,preco,gelada\n"
                    for p in produtos:
                        gelada = "sim" if p["is_cold"] else "nao"
                        csv_data += f"{p['product_name']},{p['brand']},{p['volume_ml']},{p['quantity']},{p['price_cents']/100:.2f},{gelada}\n"
                    if len(csv_data) < 4000:
                        send_message(chat_id, f"📊 *ESTOQUE CSV*\n\n<code>{csv_data}</code>")
                    else:
                        send_message(chat_id, "📊 Estoque muito grande. Use o Supabase para exportar.")
                else:
                    send_message(chat_id, "❌ Erro ao gerar exportação.")
                return {"ok": True}

        elif "callback_query" in body:
            cb = body["callback_query"]
            chat_id = cb["message"]["chat"]["id"]
            data = cb["data"]
            callback_id = cb["id"]
            
            print(f"Callback: {data}")
            answer_callback(callback_id)
            
            # ========== MENU ADMIN ==========
            if data == "admin":
                if chat_id == ADMIN_CHAT_ID:
                    send_message(chat_id, "🔧 *MENU ADMIN*", reply_markup=admin_keyboard())
                else:
                    send_message(chat_id, "⛔ Acesso negado. Apenas administradores.")
            
            elif data == "voltar":
                send_message(chat_id, "🤖 *MENU CLIENTE*", reply_markup=cliente_keyboard())
            
            # ========== ADICIONAR PRODUTO ==========
            elif data == "adicionar":
                if chat_id != ADMIN_CHAT_ID:
                    send_message(chat_id, "⛔ Acesso negado.")
                    return {"ok": True}
                send_message(chat_id, "📝 *Adicionar Produto*\n\nUse o comando:\n`/adicionar nome|marca|volume|qtd|preco|gelada`\n\nExemplo:\n`/adicionar Heineken|Heineken|350|50|690|true`")
            
            # ========== ATUALIZAR ESTOQUE ==========
            elif data == "atualizar":
                if chat_id != ADMIN_CHAT_ID:
                    send_message(chat_id, "⛔ Acesso negado.")
                    return {"ok": True}
                send_message(chat_id, "📦 *Atualizar Estoque*\n\nUse o comando:\n`/atualizar produto|+10` ou `/atualizar produto|-5`\n\nExemplo:\n`/atualizar Heineken|+10`")
            
            # ========== EXPORTAR ESTOQUE ==========
            elif data == "exportar":
                if chat_id != ADMIN_CHAT_ID:
                    send_message(chat_id, "⛔ Acesso negado.")
                    return {"ok": True}
                produtos = consultar_supabase(chat_id, "inventory?order=product_name.asc")
                if produtos:
                    csv_data = "produto,marca,volume,quantidade,preco,gelada\n"
                    for p in produtos:
                        gelada = "sim" if p["is_cold"] else "nao"
                        csv_data += f"{p['product_name']},{p['brand']},{p['volume_ml']},{p['quantity']},{p['price_cents']/100:.2f},{gelada}\n"
                    if len(csv_data) < 4000:
                        send_message(chat_id, f"📊 *ESTOQUE CSV*\n\n<code>{csv_data}</code>")
                    else:
                        send_message(chat_id, "📊 Estoque muito grande. Use o Supabase para exportar.")
                else:
                    send_message(chat_id, "❌ Erro ao gerar exportação.")
            
            # ========== CONSULTAS ==========
            elif data == "resumo":
                produtos = consultar_supabase(chat_id, "inventory?order=product_name.asc")
                if produtos:
                    if len(produtos) == 0:
                        send_message(chat_id, "📦 Estoque vazio.")
                    else:
                        msg = "*📦 RESUMO DO ESTOQUE*\n\n"
                        for p in produtos:
                            emoji = "❄️" if p["is_cold"] else "🌡️"
                            msg += f"{emoji} *{p['product_name']}*: {p['quantity']} un\n"
                        send_message(chat_id, msg)
            
            elif data == "completo":
                produtos = consultar_supabase(chat_id, "inventory?order=product_name.asc")
                if produtos:
                    if len(produtos) == 0:
                        send_message(chat_id, "📦 Estoque vazio!")
                    else:
                        msg = "*📦 ESTOQUE COMPLETO*\n\n"
                        for p in produtos:
                            gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                            msg += (f"🍺 *{p['product_name']}*\n"
                                   f"   🏷️ {p['brand']} | 📏 {p['volume_ml']}ml\n"
                                   f"   📦 {p['quantity']} un | 💰 R$ {p['price_cents']/100:.2f}\n"
                                   f"   {gelado}\n\n")
                        if len(msg) > 4000:
                            msg = msg[:4000] + "\n\n... (mais produtos)"
                        send_message(chat_id, msg)
            
            # ========== PRODUTOS ESPECÍFICOS ==========
            elif data == "heineken":
                produtos = consultar_supabase(chat_id, "inventory?product_name=ilike.*heineken*")
                if produtos and len(produtos) > 0:
                    p = produtos[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Heineken não encontrada.")
            
            elif data == "stella":
                produtos = consultar_supabase(chat_id, "inventory?product_name=ilike.*stella*")
                if produtos and len(produtos) > 0:
                    p = produtos[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Stella Artois não encontrada.")
            
            elif data == "original":
                produtos = consultar_supabase(chat_id, "inventory?product_name=ilike.*original*")
                if produtos and len(produtos) > 0:
                    p = produtos[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Original não encontrada.")
            
            elif data == "brahma":
                produtos = consultar_supabase(chat_id, "inventory?product_name=ilike.*brahma*")
                if produtos and len(produtos) > 0:
                    p = produtos[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Brahma não encontrada.")
            
            elif data == "skol":
                produtos = consultar_supabase(chat_id, "inventory?product_name=ilike.*skol*")
                if produtos and len(produtos) > 0:
                    p = produtos[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Skol não encontrada.")
            
            elif data == "colorado":
                produtos = consultar_supabase(chat_id, "inventory?product_name=ilike.*colorado*")
                if produtos and len(produtos) > 0:
                    p = produtos[0]
                    cold = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
                    msg = (f"🍺 *{p['product_name']}* {cold}\n"
                           f"📦 Estoque: {p['quantity']} un\n"
                           f"💰 Preço: R$ {p['price_cents']/100:.2f}")
                    send_message(chat_id, msg)
                else:
                    send_message(chat_id, "❌ Colorado não encontrada.")
            
            return {"ok": True}
                # ========== COMANDOS DE TEXTO (FARMING) ==========
        if "message" in body and chat_id == ADMIN_CHAT_ID:
            text = body["message"].get("text", "")
            
            # Comando: /farming_status
            if text.startswith("/farming_status"):
                try:
                    headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                    resp = requests.get(f"{SUPABASE_URL}/rest/v1/farming_accounts?select=agent_id,platform,username,is_active,daily_goal", headers=headers, timeout=15)
                    
                    if resp.status_code == 200:
                        contas = resp.json()
                        if contas:
                            msg = "*🌾 FARMING STATUS*\n\n"
                            for c in contas:
                                status_icon = "✅" if c["is_active"] else "⏸️"
                                status_text = "Ativo" if c["is_active"] else "Pausado"
                                msg += f"{status_icon} *{c['agent_id']}*\n"
                                msg += f"   📱 {c['platform']} | 👤 {c['username']}\n"
                                msg += f"   📊 Meta: {c['daily_goal']} ações/dia | {status_text}\n\n"
                            send_message(chat_id, msg)
                        else:
                            send_message(chat_id, "📭 Nenhuma conta de farming cadastrada.\n\nUse `/farming_add` para adicionar.")
                    else:
                        send_message(chat_id, f"❌ Erro ao buscar contas: {resp.status_code}")
                except Exception as e:
                    send_message(chat_id, f"❌ Erro: {str(e)}")
                return {"ok": True}
            
            # Comando: /farming_add
            elif text.startswith("/farming_add"):
                parts = text.replace("/farming_add", "").strip().split("|")
                if len(parts) != 5:
                    send_message(chat_id, "📝 *Formato inválido!*\n\nUse:\n`/farming_add agent_id|platform|username|workspace_path|daily_goal`\n\nExemplo:\n`/farming_add insta_oficial|instagram|meu_insta|/workspaces/insta|50`")
                    return {"ok": True}
                
                agent_id, platform, username, workspace_path, daily_goal = parts
                try:
                    daily_goal_int = int(daily_goal)
                    if daily_goal_int <= 0:
                        raise ValueError
                except ValueError:
                    send_message(chat_id, "❌ daily_goal deve ser um número positivo.")
                    return {"ok": True}
                
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                check_resp = requests.get(f"{SUPABASE_URL}/rest/v1/farming_accounts?agent_id=eq.{agent_id}", headers=headers)
                if check_resp.status_code == 200 and check_resp.json():
                    send_message(chat_id, f"⚠️ Conta '{agent_id}' já existe!")
                    return {"ok": True}
                
                # Criar carteira para o agente
                requests.post(f"{PROXY_URL}/wallet/balance", params={"agent_id": agent_id, "secret": AUTO_APPROVE_SECRET})
                
                data = {
                    "agent_id": agent_id,
                    "platform": platform,
                    "username": username,
                    "workspace_path": workspace_path,
                    "daily_goal": daily_goal_int,
                    "is_active": True
                }
                headers["Content-Type"] = "application/json"
                resp = requests.post(f"{SUPABASE_URL}/rest/v1/farming_accounts", json=data, headers=headers)
                
                if resp.status_code in (200, 201):
                    send_message(chat_id, f"✅ *Conta adicionada com sucesso!*\n\n🆔 Agent ID: `{agent_id}`\n📱 Plataforma: {platform}\n👤 Usuário: {username}\n📊 Meta diária: {daily_goal_int} ações\n\n💰 Carteira criada com saldo R$ 0.")
                else:
                    send_message(chat_id, f"❌ Erro ao adicionar conta: {resp.text[:200]}")
                return {"ok": True}
            
            # Comando: /farming_pause
            elif text.startswith("/farming_pause"):
                agent_id = text.replace("/farming_pause", "").strip()
                if not agent_id:
                    send_message(chat_id, "Use: `/farming_pause <agent_id>`\n\nExemplo: `/farming_pause insta_oficial`")
                    return {"ok": True}
                
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": "application/json"}
                resp = requests.patch(f"{SUPABASE_URL}/rest/v1/farming_accounts?agent_id=eq.{agent_id}", json={"is_active": False}, headers=headers)
                
                if resp.status_code in (200, 204):
                    send_message(chat_id, f"⏸️ Conta `{agent_id}` foi *pausada*.\n\nPara reativar, use `/farming_resume {agent_id}`")
                else:
                    send_message(chat_id, f"❌ Erro ao pausar: {resp.text[:100]}")
                return {"ok": True}
            
            # Comando: /farming_resume
            elif text.startswith("/farming_resume"):
                agent_id = text.replace("/farming_resume", "").strip()
                if not agent_id:
                    send_message(chat_id, "Use: `/farming_resume <agent_id>`\n\nExemplo: `/farming_resume insta_oficial`")
                    return {"ok": True}
                
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": "application/json"}
                resp = requests.patch(f"{SUPABASE_URL}/rest/v1/farming_accounts?agent_id=eq.{agent_id}", json={"is_active": True}, headers=headers)
                
                if resp.status_code in (200, 204):
                    send_message(chat_id, f"▶️ Conta `{agent_id}` foi *reativada*.")
                else:
                    send_message(chat_id, f"❌ Erro ao reativar: {resp.text[:100]}")
                return {"ok": True}
            
            # Comando: /farming_executar
            elif text.startswith("/farming_executar"):
                send_message(chat_id, "🔄 *Iniciando execução das ações de farming...*\n\n⚙️ Funcionalidade em desenvolvimento. Em breve, o farming worker será executado automaticamente.")
                return {"ok": True}
        # ========== COMANDOS DE TEXTO (ADMIN) ==========
        if "message" in body and chat_id == ADMIN_CHAT_ID:
            text = body["message"].get("text", "")
            
            if text.startswith("/adicionar"):
                parts = text.replace("/adicionar", "").strip().split("|")
                if len(parts) != 6:
                    send_message(chat_id, "Formato inválido. Use: /adicionar nome|marca|volume|qtd|preco|gelada")
                    return {"ok": True}
                
                nome, marca, volume, qtd, preco, gelada = parts
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "Content-Type": "application/json"}
                data = {
                    "product_name": nome.strip(),
                    "brand": marca.strip(),
                    "volume_ml": int(volume),
                    "quantity": int(qtd),
                    "price_cents": int(preco),
                    "is_cold": gelada.strip().lower() == "true"
                }
                resp = requests.post(f"{SUPABASE_URL}/rest/v1/inventory", json=data, headers=headers)
                if resp.status_code in (200, 201):
                    send_message(chat_id, f"✅ Produto '{nome}' adicionado!")
                else:
                    send_message(chat_id, f"❌ Erro: {resp.text}")
            
            elif text.startswith("/atualizar"):
                parts = text.replace("/atualizar", "").strip().split("|")
                if len(parts) != 2:
                    send_message(chat_id, "Formato inválido. Use: /atualizar produto|+10")
                    return {"ok": True}
                
                nome, operacao = parts
                delta = int(operacao)
                headers = {"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"}
                resp = requests.get(f"{SUPABASE_URL}/rest/v1/inventory?product_name=eq.{nome}", headers=headers)
                if resp.status_code == 200 and resp.json():
                    produto = resp.json()[0]
                    nova_qtd = produto["quantity"] + delta
                    if nova_qtd < 0:
                        send_message(chat_id, "❌ Estoque não pode ficar negativo.")
                        return {"ok": True}
                    update_resp = requests.patch(f"{SUPABASE_URL}/rest/v1/inventory?id=eq.{produto['id']}", json={"quantity": nova_qtd}, headers=headers)
                    if update_resp.status_code in (200, 204):
                        sinal = "adicionadas" if delta > 0 else "removidas"
                        send_message(chat_id, f"✅ Estoque de '{nome}' atualizado: {abs(delta)} unidades {sinal}. Novo estoque: {nova_qtd}")
                    else:
                        send_message(chat_id, f"❌ Erro: {update_resp.text}")
                else:
                    send_message(chat_id, f"❌ Produto '{nome}' não encontrado.")

    except Exception as e:
        print(f"Erro geral: {e}")
    
    return {"ok": True}

@app.get("/")
def root():
    return {"status": "ok"}
