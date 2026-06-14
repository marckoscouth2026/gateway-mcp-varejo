def login(page, account_id, username, password):
    print(f"🔑 Fazendo login para {account_id}...")
    page.set_default_navigation_timeout(60000)  # 60 segundos
    page.goto("https://www.instagram.com/accounts/login/")
    
    # Aguarda o formulário e trata pop‑up de cookies
    try:
        page.wait_for_selector("input[name='username']", timeout=20000)
    except:
        # Tenta fechar qualquer pop‑up (ex: "Apenas o essencial" ou "Aceitar cookies")
        try:
            page.click("button:has-text('Apenas o essencial')", timeout=5000)
        except:
            try:
                page.click("button:has-text('Aceitar')", timeout=5000)
            except:
                pass
        page.wait_for_selector("input[name='username']", timeout=20000)
    
    # Preenche os campos
    page.fill("input[name='username']", username, timeout=10000)
    time.sleep(random.uniform(1, 2))
    page.fill("input[name='password']", password, timeout=10000)
    time.sleep(random.uniform(1, 2))
    
    # Clica no botão de login
    page.click("button[type='submit']")
    
    # Aguarda o redirecionamento (pode levar tempo, especialmente com CAPTCHA)
    time.sleep(random.uniform(10, 15))
    
    # Verifica se ainda está na página de login
    if "login" in page.url:
        print("⚠️ Ainda na página de login. Verifique se há CAPTCHA ou pop-up.")
        # Tira um print para diagnóstico
        page.screenshot(path="login_blocked.png")
        print("📸 Screenshot salvo como login_blocked.png")
        return False
    
    # Trata possível pop-up "Salvar informações de login?" ou "Ativar notificações"
    try:
        page.click("button:has-text('Agora não')", timeout=5000)
    except:
        try:
            page.click("button:has-text('Não agora')", timeout=5000)
        except:
            pass
    
    print("✅ Login bem-sucedido")
    return True