import streamlit as st
import requests
from datetime import datetime

# ========== CONFIGURAÇÕES (lidas dos secrets) ==========
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "admin123")

# ========== DEBUG: Mostrar configurações (remover depois) ==========
st.sidebar.write(f"URL: {SUPABASE_URL[:30]}..." if SUPABASE_URL else "URL não configurada")
st.sidebar.write(f"Key: {SUPABASE_KEY[:20]}..." if SUPABASE_KEY else "Key não configurada")

# Verifica se as configurações estão corretas
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Configuração do Supabase não encontrada. Verifique os secrets.")
    st.stop()

# ========== FUNÇÕES ==========
def supabase_request(endpoint, method="GET", data=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            resp = requests.post(url, json=data, headers=headers, timeout=30)
        elif method == "PATCH":
            resp = requests.patch(url, json=data, headers=headers, timeout=30)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return None
        return resp
    except Exception as e:
        st.error(f"Erro na requisição: {e}")
        return None

def carregar_produtos():
    resp = supabase_request("inventory?order=product_name.asc")
    if resp and resp.status_code == 200:
        return resp.json()
    else:
        if resp:
            st.error(f"Erro ao carregar produtos: {resp.status_code} - {resp.text[:200]}")
        return []

def adicionar_produto(nome, marca, volume, qtd, preco, gelada):
    # Verificar se produto já existe
    produtos = carregar_produtos()
    for p in produtos:
        if p["product_name"].lower() == nome.lower():
            return False, "Produto já existe"
    
    data = {
        "product_name": nome,
        "brand": marca,
        "volume_ml": volume,
        "quantity": qtd,
        "price_cents": int(preco * 100),
        "is_cold": gelada,
        "last_updated": datetime.now().isoformat()
    }
    resp = supabase_request("inventory", method="POST", data=data)
    if resp and resp.status_code in (200, 201):
        return True, "Sucesso"
    else:
        erro = resp.text if resp else "Sem resposta"
        return False, f"Erro {resp.status_code if resp else 'conexão'}: {erro[:100]}"

def atualizar_produto(produto_id, quantidade):
    data = {"quantity": quantidade, "last_updated": datetime.now().isoformat()}
    resp = supabase_request(f"inventory?id=eq.{produto_id}", method="PATCH", data=data)
    return resp.status_code in (200, 204) if resp else False

def deletar_produto(produto_id):
    resp = supabase_request(f"inventory?id=eq.{produto_id}", method="DELETE")
    return resp.status_code in (200, 204) if resp else False

# ========== AUTENTICAÇÃO ==========
st.set_page_config(page_title="Gateway MCP - Estoque", page_icon="🍺", layout="wide")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Acesso Restrito")
    password = st.text_input("Senha administrativa:", type="password")
    if st.button("Entrar"):
        if password == ADMIN_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Senha incorreta")
    st.stop()

# ========== SIDEBAR ==========
st.sidebar.title("🍺 Gateway MCP")
st.sidebar.markdown("---")
pagina = st.sidebar.radio(
    "Navegação",
    ["📊 Dashboard", "📦 Estoque", "➕ Adicionar Produto", "📈 Relatórios"]
)

# ========== DASHBOARD ==========
if pagina == "📊 Dashboard":
    st.title("📊 Dashboard de Estoque")
    
    produtos = carregar_produtos()
    if produtos:
        total_produtos = len(produtos)
        total_estoque = sum(p['quantity'] for p in produtos)
        valor_total = sum(p['quantity'] * (p['price_cents'] / 100) for p in produtos)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Produtos", total_produtos)
        col2.metric("Total em Estoque", f"{total_estoque} un")
        col3.metric("Valor Total", f"R$ {valor_total:.2f}")
        
        st.subheader("📊 Produtos")
        for p in produtos:
            gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
            st.write(f"🍺 **{p['product_name']}** - {p['quantity']} un - R$ {p['price_cents']/100:.2f} - {gelado}")
        
        st.subheader("🍺 Produtos com Baixo Estoque")
        baixo_estoque = [p for p in produtos if p['quantity'] < 10]
        if baixo_estoque:
            for p in baixo_estoque:
                st.warning(f"🍺 **{p['product_name']}** - apenas {p['quantity']} unidades")
        else:
            st.info("Nenhum produto com estoque baixo.")
    else:
        st.warning("⚠️ Nenhum produto encontrado no banco de dados. Use o Telegram para adicionar produtos.")

# ========== ESTOQUE ==========
elif pagina == "📦 Estoque":
    st.title("📦 Gerenciar Estoque")
    
    produtos = carregar_produtos()
    if produtos:
        for p in produtos:
            gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
            with st.expander(f"🍺 {p['product_name']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Marca:** {p['brand']}")
                    st.write(f"**Volume:** {p['volume_ml']}ml")
                    st.write(f"**Preço:** R$ {p['price_cents']/100:.2f}")
                    st.write(f"**Status:** {gelado}")
                with col2:
                    nova_qtd = st.number_input("Quantidade", min_value=0, value=int(p['quantity']), key=f"qtd_{p['id']}")
                    if st.button("Atualizar", key=f"update_{p['id']}"):
                        if atualizar_produto(p['id'], nova_qtd):
                            st.success("Estoque atualizado!")
                            st.rerun()
                    if st.button("🗑️ Deletar", key=f"delete_{p['id']}"):
                        if deletar_produto(p['id']):
                            st.success("Produto deletado!")
                            st.rerun()
    else:
        st.warning("⚠️ Nenhum produto encontrado. Adicione produtos pelo Telegram.")

# ========== ADICIONAR PRODUTO ==========
elif pagina == "➕ Adicionar Produto":
    st.title("➕ Adicionar Novo Produto")
    
    # Mostrar produtos existentes para referência
    produtos_existentes = carregar_produtos()
    if produtos_existentes:
        st.info(f"📋 Produtos já cadastrados: {', '.join([p['product_name'] for p in produtos_existentes])}")
    
    with st.form("add_product"):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome do Produto *")
            marca = st.text_input("Marca")
            volume = st.number_input("Volume (ml)", min_value=0, step=50)
        with col2:
            quantidade = st.number_input("Quantidade inicial", min_value=0, step=1)
            preco = st.number_input("Preço (R$)", min_value=0.0, step=0.5, format="%.2f")
            gelada = st.checkbox("Produto Gelado")
        
        submitted = st.form_submit_button("💾 Salvar Produto")
        
        if submitted:
            if not nome:
                st.error("Nome do produto é obrigatório")
            elif preco <= 0:
                st.error("Preço deve ser maior que zero")
            else:
                sucesso, mensagem = adicionar_produto(nome, marca, volume, quantidade, preco, gelada)
                if sucesso:
                    st.success(f"✅ Produto '{nome}' adicionado com sucesso!")
                    st.rerun()
                else:
                    st.error(f"❌ {mensagem}")

# ========== RELATÓRIOS ==========
elif pagina == "📈 Relatórios":
    st.title("📈 Relatórios")
    
    produtos = carregar_produtos()
    if produtos:
        st.subheader("📋 Lista de Produtos")
        for p in produtos:
            gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
            st.write(f"🍺 **{p['product_name']}** | {p['brand']} | {p['volume_ml']}ml | {p['quantity']} un | R$ {p['price_cents']/100:.2f} | {gelado}")
        
        st.subheader("📥 Exportar Dados")
        csv_data = "produto,marca,volume,quantidade,preco,gelada\n"
        for p in produtos:
            gelada = "sim" if p["is_cold"] else "nao"
            csv_data += f"{p['product_name']},{p['brand']},{p['volume_ml']},{p['quantity']},{p['price_cents']/100:.2f},{gelada}\n"
        
        st.download_button(
            label="📥 Baixar CSV",
            data=csv_data,
            file_name=f"estoque_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.warning("⚠️ Nenhum produto encontrado.")

# ========== FOOTER ==========
st.sidebar.markdown("---")
st.sidebar.caption(f"Gateway MCP Varejo | {datetime.now().strftime('%Y-%m-%d %H:%M')}")