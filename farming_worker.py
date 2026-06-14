#!/usr/bin/env python3
"""
Farming Worker - Executa ações automatizadas para contas de redes sociais
Compartilha o mesmo Supabase e Agent Auth Proxy do Gateway MCP
"""

import os
import sys
import time
import random
import requests
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

# ========== CONFIGURAÇÕES ==========
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
PROXY_URL = os.getenv("PROXY_URL", "https://gateway-mcp-varejo.onrender.com")
AUTO_APPROVE_SECRET = os.getenv("AUTO_APPROVE_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Custos das ações (em centavos)
CUSTOS = {
    "like": 1,      # R$ 0,01
    "follow": 5,    # R$ 0,05
    "comment": 10,  # R$ 0,10
    "post": 50,     # R$ 0,50
}

# ========== FUNÇÕES DE SUPORTE ==========

def send_telegram_message(text, parse_mode="HTML"):
    print(f"📤 [DEBUG] send_telegram_message chamada. Tamanho: {len(text)}")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ [DEBUG] Telegram não configurado: token ou chat_id ausentes")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}
    try:
        print(f"📡 [DEBUG] Enviando para chat_id={TELEGRAM_CHAT_ID}")
        resp = requests.post(url, json=payload, timeout=30)
        print(f"   Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   Erro: {resp.text}")
        else:
            print(f"✅ [DEBUG] Mensagem enviada com sucesso")
    except Exception as e:
        print(f"❌ [DEBUG] Exceção: {e}")

def supabase_request(endpoint, method="GET", data=None, params=None):
    """Faz requisição ao Supabase com headers corretos"""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("❌ Erro: SUPABASE_URL ou SUPABASE_SERVICE_KEY não configurados")
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
    """Consulta saldo da conta via proxy"""
    if not PROXY_URL or not AUTO_APPROVE_SECRET:
        print("❌ PROXY_URL ou AUTO_APPROVE_SECRET não configurados")
        return 0
    
    try:
        url = f"{PROXY_URL}/wallet/balance?agent_id={agent_id}&secret={AUTO_APPROVE_SECRET}"
        print(f"🔍 Consultando saldo: {url.replace(AUTO_APPROVE_SECRET, '***')}")
        resp = requests.post(url, timeout=30)
        print(f"   Status: {resp.status_code}")
        print(f"   Resposta: {resp.text}")
        if resp.status_code == 200:
            data = resp.json()
            balance = data.get("balance", 0)
            print(f"   Saldo interpretado: {balance}")
            return balance
        else:
            return 0
    except Exception as e:
        print(f"   ❌ Erro: {e}")
        return 0

def get_active_accounts():
    """Busca contas ativas para processamento"""
    print("🔍 Buscando contas ativas...")
    resp = supabase_request("farming_accounts?is_active=eq.true")
    
    if resp and resp.status_code == 200:
        contas = resp.json()
        print(f"📋 Encontradas {len(contas)} contas ativas")
        return contas
    else:
        if resp:
            print(f"❌ Erro {resp.status_code}: {resp.text[:200]}")
        else:
            print("❌ Sem resposta do Supabase")
        return []

def debit_action(agent_id, action_type, target):
    """Debita o custo da ação da carteira do agente"""
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
            print(f"      ❌ Saldo insuficiente para debitar R$ {cost/100:.2f}")
            return False, cost
        else:
            print(f"      ❌ Erro no débito: {resp.status_code} - {resp.text}")
            return False, cost
    except Exception as e:
        print(f"      ❌ Exceção no débito: {e}")
        return False, cost

def register_action(agent_id, action_type, target, cost, success, error_msg=None):
    """Registra a ação na tabela farming_actions"""
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
    """
    Executa a ação simulada (substituir por Playwright depois)
    """
    delay = random.uniform(1, 5)
    print(f"      ⏳ Simulando {action_type} (delay {delay:.1f}s)...")
    time.sleep(delay)
    
    # Simular sucesso (95% de taxa de sucesso)
    sucesso = random.random() < 0.95
    if sucesso:
        print(f"      ✅ {action_type} simulado com sucesso!")
    else:
        print(f"      ❌ {action_type} simulado falhou!")
    
    return sucesso

def process_account(account):
    """Processa uma conta: executa ações e envia resumo detalhado"""
    agent_id = account["agent_id"]
    platform = account["platform"]
    daily_goal = account.get("daily_goal", 50)
    
    print(f"\n{'='*50}")
    print(f"📱 Processando conta: {agent_id}")
    print(f"   Plataforma: {platform}")
    print(f"   Meta diária: {daily_goal} ações")
    
    balance_antes = get_account_balance(agent_id)
    print(f"   💰 Saldo: R$ {balance_antes/100:.2f}")
    
    if balance_antes < 10:
        print(f"   ⚠️ Saldo baixo! Considere recarregar a carteira.")
        send_telegram_message(f"⚠️ *Alerta de saldo baixo*\n\nConta `{agent_id}` está com saldo R$ {balance_antes/100:.2f}. Recarregue para continuar as ações.")
        return
    
    acoes = [
        {"type": "like", "target": f"https://instagram.com/p/exemplo_{random.randint(1,100)}"},
        {"type": "follow", "target": f"https://instagram.com/usuario_{random.randint(1,50)}"},
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
        
        # Debita
        success_debit, cost = debit_action(agent_id, action_type, target)
        if not success_debit:
            print(f"      ❌ Falha no débito")
            register_action(agent_id, action_type, target, cost, False, "Saldo/limite insuficiente")
            break
        
        print(f"      💸 Débito de R$ {cost/100:.2f} realizado")
        custo_total += cost
        
        # Executa ação simulada
        success_action = execute_action_simulated(agent_id, action_type, target)
        if success_action:
            register_action(agent_id, action_type, target, cost, True)
            actions_executed += 1
            detalhes.append(f"✅ {action_type}: R$ {cost/100:.2f}")
        else:
            register_action(agent_id, action_type, target, cost, False, "Falha na execução simulada")
            detalhes.append(f"❌ {action_type}: falhou")
        
        pausa = random.uniform(3, 8)
        print(f"      ⏱️ Aguardando {pausa:.1f}s...")
        time.sleep(pausa)
    
    final_balance = get_account_balance(agent_id)
    print(f"\n   📊 Total de ações executadas: {actions_executed}")
    print(f"   💰 Saldo final: R$ {final_balance/100:.2f}")
    
    # Envia resumo detalhado para o Telegram
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
        send_telegram_message(f"⚠️ Nenhuma ação executada para `{agent_id}`. Verifique saldo ou limite.")
        print(f"📤 [DEBUG] Preparando resumo detalhado...")
if actions_executed > 0:
    resumo = (...)
    print(f"📤 [DEBUG] Chamando send_telegram_message para resumo detalhado")
    send_telegram_message(resumo)
else:
    print(f"⚠️ [DEBUG] Nenhuma ação executada, enviando alerta")
    send_telegram_message(...)

def main():
    print("="*50)
    print("🌾 FARMING WORKER")
    print("="*50)
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy: {PROXY_URL}")
    
    # Verificar configurações
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        print("❌ Erro: Configuração do Supabase não encontrada.")
        print("   Verifique o arquivo .env")
        sys.exit(1)
    
    if not AUTO_APPROVE_SECRET:
        print("❌ Erro: AUTO_APPROVE_SECRET não configurado.")
        sys.exit(1)
    
    # Buscar contas ativas
    accounts = get_active_accounts()
    
    if not accounts:
        print("\n📭 Nenhuma conta ativa encontrada.")
        print("   Adicione contas com o comando: /farming_add")
        send_telegram_message("🌾 *Farming Worker*\n\nNenhuma conta ativa encontrada.\nAdicione contas com `/farming_add`.")
        return
    
    # Processar cada conta
    for account in accounts:
        process_account(account)
    
    # Resumo final
    print("\n" + "="*50)
    print("✅ Farming Worker concluído!")
    
    # Enviar resumo simples para o Telegram (opcional, pois cada conta já enviou detalhes)
    # send_telegram_message(f"🌾 *Farming Worker*\n\n✅ Execução concluída\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n📋 Contas processadas: {len(accounts)}")

if __name__ == "__main__":
    main()
