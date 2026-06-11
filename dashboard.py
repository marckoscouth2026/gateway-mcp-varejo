import streamlit as st
import requests
from datetime import datetime

# ========== CONFIGURAÇÕES ==========
# Tentar ler dos secrets, se não existir, usar valores diretos
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
except:
    # Fallback para teste (remova depois que funcionar)
    SUPABASE_URL = "https://ofcejjyvpaflekkzrhll.supabase.co"
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9mY2Vqanl2cGFmbGVra3pyaGxsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4MTAwMDYwNCwiZXhwIjoyMDk2NTc2NjA0fQ.7LUu6N5DSKB_NEjBJ41HQC0d7gkX2e0a0c_EY14ZuVA"
    ADMIN_PASSWORD = "admin123"
    st.warning("Usando configurações padrão (não secrets)")

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
        else:
            return None
        return resp
    except Exception as e:
        st.error(f"Erro: {e}")
        return None

def carregar_produtos():
    resp = supabase_request("inventory?order=product_name.asc")
    if resp and resp.status_code == 200:
        return resp.json()
    else:
        if resp:
            st.error(f"Erro {resp.status_code}: {resp.text[:200]}")
        return []

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

# Mostrar status da conexão
test_resp = supabase_request("inventory?limit=1")
if test_resp and test_resp.status_code == 200:
    st.sidebar.success("✅ Conectado ao Supabase")
else:
    st.sidebar.error("❌ Falha na conexão com Supabase")

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
        
        st.subheader("📋 Lista de Produtos")
        for p in produtos:
            gelado = "🌡️ Gelada" if p["is_cold"] else "❄️ Ambiente"
            st.write(f"🍺 **{p['product_name']}** - {p['quantity']} un - R$ {p['price_cents']/100:.2f} - {gelado}")
    else:
        st.warning("⚠️ Nenhum produto encontrado. Use o Telegram para adicionar produtos (ex: /adicionar Skol|Ambev|350|12|400|false)")

# ========== ESTOQUE ==========
elif pagina == "📦 Estoque":
    st.title("📦 Gerenciar Estoque")
    
    produtos = carregar_produtos()
    if produtos:
        for p in produtos:
            with st.expander(f"🍺 {p['product_name']}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Marca:** {p['brand']}")
                    st.write(f"**Volume:** {p['volume_ml']}ml")
                    st.write(f"**Preço:** R$ {p['price_cents']/100:.2f}")
                    st.write(f"**Gelada:** {'Sim' if p['is_cold'] else 'Não'}")
                with col2:
                    nova_qtd = st.number_input("Quantidade", min_value=0, value=int(p['quantity']), key=f"qtd_{p['id']}")
                    if st.button("Atualizar", key=f"update_{p['id']}"):
                        data = {"quantity": nova_qtd, "last_updated": datetime.now().isoformat()}
                        resp = supabase_request(f"inventory?id=eq.{p['id']}", method="PATCH", data=data)
                        if resp and resp.status_code in (200, 204):
                            st.success("Estoque atualizado!")
                            st.rerun()
                        else:
                            st.error("Erro ao atualizar")
    else:
        st.warning("⚠️ Nenhum produto encontrado.")

# ========== ADICIONAR PRODUTO ==========
elif pagina == "➕ Adicionar Produto":
    st.title("➕ Adicionar Novo Produto")
    
    with st.form("add_product"):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome do Produto *")
            marca = st.text_input("Marca")
            volume = st.number_input("Volume (ml)", min_value=0, step=50, value=350)
        with col2:
            quantidade = st.number_input("Quantidade inicial", min_value=0, step=1, value=10)
            preco = st.number_input("Preço (R$)", min_value=0.0, step=0.5, format="%.2f", value=5.00)
            gelada = st.checkbox("Produto Gelado", value=True)
        
        submitted = st.form_submit_button("💾 Salvar Produto")
        
        if submitted:
            if not nome:
                st.error("Nome do produto é obrigatório")
            else:
                data = {
                    "product_name": nome,
                    "brand": marca,
                    "volume_ml": volume,
                    "quantity": quantidade,
                    "price_cents": int(preco * 100),
                    "is_cold": gelada,
                    "last_updated": datetime.now().isoformat()
                }
                resp = supabase_request("inventory", method="POST", data=data)
                if resp and resp.status_code in (200, 201):
                    st.success(f"✅ Produto '{nome}' adicionado com sucesso!")
                    st.rerun()
                else:
                    erro = resp.text if resp else "Sem resposta"
                    st.error(f"❌ Erro: {erro[:200]}")

# ========== RELATÓRIOS ==========
elif pagina == "📈 Relatórios":
    st.title("📈 Relatórios")
    
    produtos = carregar_produtos()
    if produtos:
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

st.sidebar.markdown("---")
st.sidebar.caption(f"Gateway MCP | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
