#!/usr/bin/env python3
import os
import sys
import time
import random
import json
import argparse
from playwright.sync_api import sync_playwright

WORKSPACE_BASE = "/tmp/playwright_workspaces"

# >>> SUBSTITUA PELOS DADOS DA SUA CONTA <<<
ACCOUNTS = {
    "teste_farming_01": {
        "username": "testefarmingbot",      # ex: "testefarmingxyz123"
        "password": "acesso2026"         # ex: "T3stF@rm2026!"
    }
}

def get_workspace_path(account_id):
    path = os.path.join(WORKSPACE_BASE, account_id)
    os.makedirs(path, exist_ok=True)
    return path

def load_cookies(context, account_id):
    cookie_file = os.path.join(get_workspace_path(account_id), "cookies.json")
    if os.path.exists(cookie_file):
        with open(cookie_file, "r") as f:
            cookies = json.load(f)
            context.add_cookies(cookies)
        print(f"🍪 Cookies carregados para {account_id}")
        return True
    return False

def save_cookies(context, account_id):
    cookie_file = os.path.join(get_workspace_path(account_id), "cookies.json")
    cookies = context.cookies()
    with open(cookie_file, "w") as f:
        json.dump(cookies, f)
    print(f"🍪 Cookies salvos para {account_id}")

def login(page, account_id, username, password):
    print(f"🔑 Fazendo login para {account_id}...")
    page.goto("https://www.instagram.com/accounts/login/")
    page.screenshot(path="login_step.png")
    print("📸 Screenshot salvo como login_step.png")
    time.sleep(random.uniform(2, 4))
    page.fill("input[name='username']", username, timeout=10000)
    page.fill("input[name='password']", password, timeout=10000)
    page.click("button[type='submit']")
    time.sleep(random.uniform(5, 8))
    if "login" in page.url:
        print("❌ Falha no login")
        return False
    print("✅ Login bem-sucedido")
    return True

def like_post(page, post_url):
    print(f"❤️ Curtindo: {post_url}")
    page.goto(post_url)
    time.sleep(random.uniform(3, 5))
    like_button = page.locator("svg[aria-label='Curtir']").first
    if like_button.count():
        like_button.click()
        print("✅ Curtiu!")
        return True
    print("⚠️ Botão de like não encontrado")
    return False

def follow_user(page, profile_url):
    print(f"👥 Seguindo: {profile_url}")
    page.goto(profile_url)
    time.sleep(random.uniform(3, 5))
    follow_button = page.locator("button:has-text('Seguir')").first
    if follow_button.count():
        follow_button.click()
        print("✅ Seguiu!")
        return True
    print("⚠️ Botão 'Seguir' não encontrado")
    return False

def execute_action(account_id, action, target):
    if account_id not in ACCOUNTS:
        print(f"❌ Conta '{account_id}' não encontrada")
        return False
    creds = ACCOUNTS[account_id]
    workspace = get_workspace_path(account_id)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=workspace,
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )
        page = context.new_page()
        if not load_cookies(context, account_id):
            if not login(page, account_id, creds["username"], creds["password"]):
                context.close()
                return False
            save_cookies(context, account_id)
        else:
            page.goto("https://www.instagram.com/")
            time.sleep(3)
            if "login" in page.url:
                print("🔄 Sessão expirada, relogando...")
                if not login(page, account_id, creds["username"], creds["password"]):
                    context.close()
                    return False
                save_cookies(context, account_id)
        if action == "like":
            result = like_post(page, target)
        elif action == "follow":
            result = follow_user(page, target)
        else:
            result = False
        time.sleep(random.uniform(1, 3))
        context.close()
        return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["like", "follow"])
    parser.add_argument("--target", required=True)
    parser.add_argument("--account", required=True)
    args = parser.parse_args()
    success = execute_action(args.account, args.action, args.target)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
