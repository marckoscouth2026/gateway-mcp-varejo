#!/usr/bin/env python3
"""
Playwright Actions - Executa ações reais em redes sociais com workspaces isolados
Uso: python playwright_actions.py --action like --target https://instagram.com/p/... --account insta_conta_01
"""

import os
import sys
import time
import random
import json
import argparse
from playwright.sync_api import sync_playwright

# ========== CONFIGURAÇÕES ==========
WORKSPACE_BASE = "/tmp/playwright_workspaces"  # Pasta onde os perfis serão salvos

# Credenciais das contas (em produção, use variáveis de ambiente ou banco)
# Exemplo: ACCOUNTS = {"insta_conta_01": {"username": "user", "password": "pass"}}
ACCOUNTS = {
    "teste_farming_01": {
        "username": "Teste Farming Bot",
        "password": "acesso2026"
    }
}

def get_workspace_path(account_id):
    """Retorna o caminho do workspace isolado para a conta."""
    path = os.path.join(WORKSPACE_BASE, account_id)
    os.makedirs(path, exist_ok=True)
    return path

def load_cookies(context, account_id):
    """Carrega cookies salvos, se existirem."""
    cookie_file = os.path.join(get_workspace_path(account_id), "cookies.json")
    if os.path.exists(cookie_file):
        with open(cookie_file, "r") as f:
            cookies = json.load(f)
            context.add_cookies(cookies)
        print(f"🍪 Cookies carregados para {account_id}")
        return True
    return False

def save_cookies(context, account_id):
    """Salva cookies após login."""
    cookie_file = os.path.join(get_workspace_path(account_id), "cookies.json")
    cookies = context.cookies()
    with open(cookie_file, "w") as f:
        json.dump(cookies, f)
    print(f"🍪 Cookies salvos para {account_id}")

def login(page, account_id, username, password):
    """Realiza login no Instagram."""
    print(f"🔑 Fazendo login para {account_id}...")
    page.goto("https://www.instagram.com/accounts/login/")
    time.sleep(random.uniform(2, 4))
    
    # Preenche formulário
    page.fill("input[name='username']", username, timeout=10000)
    page.fill("input[name='password']", password, timeout=10000)
    page.click("button[type='submit']")
    
    # Aguarda login (pode pedir 2FA ou salvar informações)
    time.sleep(random.uniform(5, 8))
    
    # Verifica se login foi bem‑sucedido (ex: aparece o feed)
    if page.url.startswith("https://www.instagram.com/accounts/login/"):
        print("❌ Falha no login (credenciais inválidas ou bloqueio)")
        return False
    print("✅ Login bem‑sucedido")
    return True

def like_post(page, post_url):
    """Curtir um post do Instagram."""
    print(f"❤️ Curtindo: {post_url}")
    page.goto(post_url)
    time.sleep(random.uniform(3, 5))
    
    # Tenta encontrar o botão de like (svg com aria-label='Curtir')
    like_button = page.locator("svg[aria-label='Curtir']").first
    if like_button.count():
        like_button.click()
        print("✅ Curtiu!")
        return True
    else:
        print("⚠️ Botão de like não encontrado (já curtiu ou post inválido)")
        return False

def follow_user(page, profile_url):
    """Seguir um perfil do Instagram."""
    print(f"👥 Seguindo: {profile_url}")
    page.goto(profile_url)
    time.sleep(random.uniform(3, 5))
    
    # Botão "Seguir" pode ter diferentes seletores
    follow_button = page.locator("button:has-text('Seguir')").first
    if follow_button.count():
        follow_button.click()
        print("✅ Seguiu!")
        return True
    else:
        print("⚠️ Botão 'Seguir' não encontrado (já segue ou perfil inválido)")
        return False

def execute_action(account_id, action, target):
    """Executa uma ação com Playwright usando workspace isolado."""
    if account_id not in ACCOUNTS:
        print(f"❌ Conta '{account_id}' não encontrada nas configurações.")
        return False
    
    creds = ACCOUNTS[account_id]
    workspace = get_workspace_path(account_id)
    
    with sync_playwright() as p:
        # Lança navegador persistente (mantém cookies e sessão)
        context = p.chromium.launch_persistent_context(
            user_data_dir=workspace,
            headless=False,  # Altere para True em produção (mas aumenta risco de detecção)
            args=['--disable-blink-features=AutomationControlled']
        )
        page = context.new_page()
        
        # Carrega cookies salvos
        cookies_loaded = load_cookies(context, account_id)
        
        # Se não há cookies ou já expiraram, faz login
        if not cookies_loaded:
            success = login(page, account_id, creds["username"], creds["password"])
            if not success:
                context.close()
                return False
            save_cookies(context, account_id)
        else:
            # Navega para uma página qualquer para verificar se a sessão ainda é válida
            page.goto("https://www.instagram.com/")
            time.sleep(3)
            if "login" in page.url:
                print("🔄 Sessão expirada, relogando...")
                success = login(page, account_id, creds["username"], creds["password"])
                if not success:
                    context.close()
                    return False
                save_cookies(context, account_id)
        
        # Executa a ação solicitada
        if action == "like":
            result = like_post(page, target)
        elif action == "follow":
            result = follow_user(page, target)
        else:
            print(f"❌ Ação '{action}' não suportada.")
            result = False
        
        # Pequeno delay antes de fechar
        time.sleep(random.uniform(1, 3))
        context.close()
        return result

def main():
    parser = argparse.ArgumentParser(description="Executa ações reais em redes sociais com Playwright")
    parser.add_argument("--action", required=True, choices=["like", "follow"], help="Ação a executar")
    parser.add_argument("--target", required=True, help="URL do post ou perfil")
    parser.add_argument("--account", required=True, help="ID da conta (ex: insta_conta_01)")
    args = parser.parse_args()
    
    success = execute_action(args.account, args.action, args.target)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
