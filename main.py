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