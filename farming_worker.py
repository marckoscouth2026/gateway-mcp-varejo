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
    """Envia mensagem para o Telegram (alertas)"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": parse_mode}
        requests.post(url, json=payload, timeout=30)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

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

def process_account(account):
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
            register_action(agent_id, action_type, target, cost, False, "Falha na execução")
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
        
def debit_action(agent_id, action_type, target):
    """Debita o custo da ação da carteira do agente"""
    cost = CUSTOS.get(action_type, 1)
    
    if not PROXY_URL or not AUTO_APPROVE_SECRET:
        return False, cost
    
    try:
        # Parâmetros vão na QUERY STRING (URL)
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
    import random  # import local para garantir
    # Simulação de delay aleatório (1-5 segundos)
    delay = random.uniform(1, 5)
    print(f"      ⏳ Simulando {action_type} (delay {delay:.1f}s)...")
    time.sleep(delay)
    
    # Simular sucesso (95% de taxa de sucesso)
    success_rate = 0.95
    sucesso = random.random() < success_rate
    
    if sucesso:
        print(f"      ✅ {action_type} simulado com sucesso!")
    else:
        print(f"      ❌ {action_type} simulado falhou!")
    
    return sucesso
    
def process_account(account):
    """Processa uma conta: executa ações"""
    agent_id = account["agent_id"]
    platform = account["platform"]
    daily_goal = account.get("daily_goal", 50)
    
    print(f"\n{'='*50}")
    print(f"📱 Processando conta: {agent_id}")
    print(f"   Plataforma: {platform}")
    print(f"   Meta diária: {daily_goal} ações")
    
    # Verificar saldo atual
    balance = get_account_balance(agent_id)
    print(f"   💰 Saldo: R$ {balance/100:.2f}")
    
    if balance < 10:  # Menos que R$ 0,10
        print(f"   ⚠️ Saldo baixo! Considere recarregar a carteira.")
        send_telegram_message(f"⚠️ *Alerta de saldo baixo*\n\nConta `{agent_id}` está com saldo R$ {balance/100:.2f}.\nRecarregue para continuar as ações.")
        return
    
    # Definir ações a executar (exemplo)
    import random
    acoes = [
        {"type": "like", "target": f"https://instagram.com/p/exemplo_{random.randint(1,100)}"},
        {"type": "follow", "target": f"https://instagram.com/usuario_{random.randint(1,50)}"},
        {"type": "like", "target": f"https://instagram.com/p/exemplo2_{random.randint(1,100)}"},
    ]
    
    actions_executed = 0
    for acao in acoes:
        action_type = acao["type"]
        target = acao["target"]
        
        print(f"\n   🎬 Executando {action_type}...")
        
        # Debita o custo
        success_debit, cost = debit_action(agent_id, action_type, target)
        
        if not success_debit:
            print(f"      ❌ Falha no débito (saldo ou limite insuficiente)")
            register_action(agent_id, action_type, target, cost, False, "Saldo ou limite insuficiente")
            break
        
        print(f"      💸 Débito de R$ {cost/100:.2f} realizado")
        
        # Executa ação simulada
        success_action = execute_action_simulated(agent_id, action_type, target)
        
        if success_action:
            print(f"      ✅ {action_type} concluído!")
            register_action(agent_id, action_type, target, cost, True)
            actions_executed += 1
        else:
            print(f"      ❌ Falha na execução do {action_type}")
            register_action(agent_id, action_type, target, cost, False, "Falha na execução simulada")
        
        # Pausa entre ações para comportamento mais humano
        pausa = random.uniform(3, 8)
        print(f"      ⏱️ Aguardando {pausa:.1f}s...")
        time.sleep(pausa)
    
    print(f"\n   📊 Total de ações executadas: {actions_executed}")
    
    # Atualizar saldo final
    final_balance = get_account_balance(agent_id)
    print(f"   💰 Saldo final: R$ {final_balance/100:.2f}")

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
    
    # Enviar resumo para o Telegram
    resumo = f"🌾 *Farming Worker*\n\n✅ Execução concluída\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n📋 Contas processadas: {len(accounts)}"
    send_telegram_message(resumo)

if __name__ == "__main__":
    main()
