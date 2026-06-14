#!/usr/bin/env python3
"""
Farming Worker - Executa ações automatizadas para contas de redes sociais
"""

import os
import sys
import time
import random
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ========== CONFIGURAÇÕES ==========
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
PROXY_URL = os.getenv("PROXY_URL", "https://gateway-mcp-varejo.onrender.com")
AUTO_APPROVE_SECRET = os.getenv("AUTO_APPROVE_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CUSTOS = {
    "like": 1,
    "follow": 5,
    "comment": 10,
    "post": 50,
}

# ========== FUNÇÕES ==========
def send_telegram_message(text, parse_mode="HTML"):
    print(f"📤 [DEBUG] Enviando mensagem (tamanho: {len(text)})")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        print(f"   Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   Erro: {resp.text}")
        else:
            print("✅ Mensagem enviada")
    except Exception as e:
        print(f"❌ Exceção: {e}")

def supabase_request(endpoint, method="GET", data=None, params=None):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        elif method == "POST":
            resp = requests.post(url, json=data, headers=headers, timeout=30)
        elif method == "PATCH":
            resp = requests.patch(url, json=data, headers=headers, timeout=30)
        else:
            return None
        return resp
    except Exception as e:
        print(f"Erro Supabase: {e}")
        return None

def get_account_balance(agent_id):
    if not PROXY_URL or not AUTO_APPROVE_SECRET:
        return 0
    try:
        url = f"{PROXY_URL}/wallet/balance?agent_id={agent_id}&secret={AUTO_APPROVE_SECRET}"
        print(f"🔍 Consultando saldo: {url.replace(AUTO_APPROVE_SECRET, '***')}")
        resp = requests.post(url, timeout=30)
        print(f"   Status: {resp.status_code}")
        if resp.status_code == 200:
            balance = resp.json().get("balance", 0)
            print(f"   Saldo: {balance}")
            return balance
        return 0
    except Exception as e:
        print(f"   ❌ Erro: {e}")
        return 0

def get_active_accounts():
    print("🔍 Buscando contas ativas...")
    resp = supabase_request("farming_accounts?is_active=eq.true")
    if resp and resp.status_code == 200:
        contas = resp.json()
        print(f"📋 Encontradas {len(contas)} contas ativas")
        return contas
    print("❌ Nenhuma conta ativa ou erro na consulta")
    return []

def debit_action(agent_id, action_type, target):
    cost = CUSTOS.get(action_type, 1)
    if not PROXY_URL or not AUTO_APPROVE_SECRET:
        return False, cost
    try:
        url = f"{PROXY_URL}/wallet/pay?agent_id={agent_id}&amount={cost}&description={action_type}+em+{target}&secret={AUTO_APPROVE_SECRET}"
        resp = requests.post(url, timeout=30)
        if resp.status_code == 200:
            print(f"      💸 Débito de R$ {cost/100:.2f} realizado")
            return True, cost
        elif resp.status_code == 402:
            print(f"      ❌ Saldo insuficiente")
            return False, cost
        else:
            print(f"      ❌ Erro débito: {resp.status_code}")
            return False, cost
    except Exception as e:
        print(f"      ❌ Exceção: {e}")
        return False, cost

def register_action(agent_id, action_type, target, cost, success, error_msg=None):
    data = {
        "agent_id": agent_id,
        "action_type": action_type,
        "target": target,
        "cost_cents": cost,
        "status": "success" if success else "failed",
        "error_message": error_msg,
        "completed_at": datetime.now().isoformat() if success else None
    }
    supabase_request("farming_actions", method="POST", data=data)

def execute_action_simulated(agent_id, action_type, target):
    delay = random.uniform(1, 5)
    print(f"      ⏳ Simulando {action_type} (delay {delay:.1f}s)...")
    time.sleep(delay)
    sucesso = random.random() < 0.95
    if sucesso:
        print(f"      ✅ {action_type} simulado com sucesso!")
    else:
        print(f"      ❌ {action_type} simulado falhou!")
    return sucesso

def process_account(account):
    agent_id = account["agent_id"]
    platform = account["platform"]
    daily_goal = account.get("daily_goal", 50)
    print(f"\n{'='*50}")
    print(f"📱 Processando conta: {agent_id} ({platform})")
    print(f"   Meta diária: {daily_goal} ações")

    balance_antes = get_account_balance(agent_id)
    print(f"   💰 Saldo: R$ {balance_antes/100:.2f}")

    if balance_antes < 10:
        print("   ⚠️ Saldo baixo. Enviando alerta.")
        send_telegram_message(f"⚠️ *Alerta de saldo baixo*\n\nConta `{agent_id}` está com saldo R$ {balance_antes/100:.2f}.")
        return

    acoes = [
        {"type": "like", "target": f"https://instagram.com/p/exemplo_{random.randint(1,100)}"},
        {"type": "follow", "target": f"https://instagram.com/u/{random.randint(1,50)}"},
        {"type": "like", "target": f"https://instagram.com/p/exemplo2_{random.randint(1,100)}"},
    ]

    actions_executed = 0
    custo_total = 0
    detalhes = []

    for acao in acoes:
        action_type = acao["type"]
        target = acao["target"]
        cost = CUSTOS.get(action_type, 1)

        print(f"\n   🎬 Executando {action_type}...")
        success_debit, cost = debit_action(agent_id, action_type, target)
        if not success_debit:
            register_action(agent_id, action_type, target, cost, False, "Falha no débito")
            break

        custo_total += cost
        success_action = execute_action_simulated(agent_id, action_type, target)
        if success_action:
            register_action(agent_id, action_type, target, cost, True)
            actions_executed += 1
            detalhes.append(f"✅ {action_type}: R$ {cost/100:.2f}")
        else:
            register_action(agent_id, action_type, target, cost, False, "Falha na execução")
            detalhes.append(f"❌ {action_type}: falhou")

        pausa = random.uniform(3, 8)
        print(f"      ⏱️ Aguardando {pausa:.1f}s...")
        time.sleep(pausa)

    final_balance = get_account_balance(agent_id)
    print(f"\n   📊 Total de ações: {actions_executed}")
    print(f"   💰 Saldo final: R$ {final_balance/100:.2f}")

    # Envia resumo detalhado
    if actions_executed > 0:
        resumo = (
            f"🌾 *Farming Worker - Execução concluída*\n\n"
            f"📱 Conta: `{agent_id}`\n"
            f"✅ Ações executadas: {actions_executed}\n"
            f"💰 Custo total: R$ {custo_total/100:.2f}\n"
            f"📊 Saldo anterior: R$ {balance_antes/100:.2f}\n"
            f"💳 Saldo atual: R$ {final_balance/100:.2f}\n"
            f"📝 Detalhes:\n" + "\n".join(detalhes)
        )
        send_telegram_message(resumo)
    else:
        send_telegram_message(f"⚠️ Nenhuma ação executada para `{agent_id}`.")

def main():
    print("="*50)
    print("🌾 FARMING WORKER")
    print("="*50)
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy: {PROXY_URL}")

    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("❌ Erro: Configuração do Supabase não encontrada.")
        sys.exit(1)
    if not AUTO_APPROVE_SECRET:
        print("❌ Erro: AUTO_APPROVE_SECRET não configurado.")
        sys.exit(1)

    accounts = get_active_accounts()
    if not accounts:
        print("📭 Nenhuma conta ativa.")
        send_telegram_message("🌾 *Farming Worker*\n\nNenhuma conta ativa encontrada.")
        return

    for account in accounts:
        process_account(account)

    print("\n✅ Farming Worker concluído!")

if __name__ == "__main__":
    main()