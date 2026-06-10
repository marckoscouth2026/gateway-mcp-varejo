import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# ========== CONFIGURAÇÕES ==========
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://seu-projeto.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_SERVICE_KEY", "sua-chave")
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "admin123")

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
            resp = requests.get(url, headers=headers)
        elif method == "POST":
            resp = requests.post(url, json=data, headers=headers)
        elif method == "PATCH":
            resp = requests.patch(url, json=data, headers=headers)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers)
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
    return []

def adicionar_produto(nome, marca, volume, qtd, preco, gelada):
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
    return resp.status_code in (200, 201) if resp else False

def atualizar_produto(produto_id, quantidade):
    data = {"quantity": quantidade, "last_updated": datetime.now().isoformat()}
    resp = supabase_request(f"inventory?id=eq.{produto_id}", method="PATCH", data=data)
    return resp.status_code in (200, 204) if resp else False

def deletar_produto(produto_id):
    resp = supabase_request(f"inventory?id=eq.{produto_id}", method="DELETE")
    return resp.status_code in (200, 204) if resp else False

def exportar_csv(produtos):
    df = pd.DataFrame(produtos)
    df['preco'] = df['price_cents'] / 100
    df['gelada'] = df['is_cold'].map({True: 'Sim', False: 'Não'})
    return df.to_csv(index=False)

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
        df = pd.DataFrame(produtos)
        df['preco'] = df['price_cents'] / 100
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Produtos", len(df))
        col2.metric("Total em Estoque", f"{df['quantity'].sum()} un")
        col3.metric("Valor Total", f"R$ {(df['quantity'] * df['preco']).sum():.2f}")
        
        st.subheader("📊 Estoque por Produto")
        st.bar_chart(df.set_index('product_name')['quantity'])
        
        st.subheader("🍺 Produtos com Baixo Estoque")
        baixo_estoque = df[df['quantity'] < 10]
        if len(baixo_estoque) > 0:
            st.dataframe(baixo_estoque[['product_name', 'quantity', 'preco']])
        else:
            st.info("Nenhum produto com estoque baixo.")
    else:
        st.info("Nenhum produto cadastrado.")

# ========== ESTOQUE ==========
elif pagina == "📦 Estoque":
    st.title("📦 Gerenciar Estoque")
    
    produtos = carregar_produtos()
    if produtos:
        df = pd.DataFrame(produtos)
        df['preco'] = df['price_cents'] / 100
        df['gelada'] = df['is_cold'].map({True: '🌡️ Gelada', False: '❄️ Ambiente'})
        
        st.dataframe(
            df[['product_name', 'brand', 'volume_ml', 'quantity', 'preco', 'gelada']],
            use_container_width=True
        )
        
        st.subheader("✏️ Editar Quantidade")
        produto_selecionado = st.selectbox("Selecione o produto", df['product_name'].tolist())
        produto_id = df[df['product_name'] == produto_selecionado]['id'].values[0]
        quantidade_atual = df[df['product_name'] == produto_selecionado]['quantity'].values[0]
        
        col1, col2 = st.columns(2)
        with col1:
            nova_quantidade = st.number_input("Nova quantidade", min_value=0, value=int(quantidade_atual))
            if st.button("Atualizar"):
                if atualizar_produto(produto_id, nova_quantidade):
                    st.success("Estoque atualizado!")
                    st.rerun()
                else:
                    st.error("Erro ao atualizar")
        
        with col2:
            if st.button("🗑️ Deletar Produto", type="secondary"):
                if deletar_produto(produto_id):
                    st.success("Produto deletado!")
                    st.rerun()
                else:
                    st.error("Erro ao deletar")
    else:
        st.info("Nenhum produto cadastrado.")

# ========== ADICIONAR PRODUTO ==========
elif pagina == "➕ Adicionar Produto":
    st.title("➕ Adicionar Novo Produto")
    
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
                if adicionar_produto(nome, marca, volume, quantidade, preco, gelada):
                    st.success(f"Produto '{nome}' adicionado com sucesso!")
                    st.rerun()
                else:
                    st.error("Erro ao adicionar produto")

# ========== RELATÓRIOS ==========
elif pagina == "📈 Relatórios":
    st.title("📈 Relatórios")
    
    produtos = carregar_produtos()
    if produtos:
        df = pd.DataFrame(produtos)
        df['preco'] = df['price_cents'] / 100
        
        st.subheader("📊 Gráfico de Estoque")
        st.bar_chart(df.set_index('product_name')['quantity'])
        
        st.subheader("💰 Valor por Produto")
        df['valor_total'] = df['quantity'] * df['preco']
        st.bar_chart(df.set_index('product_name')['valor_total'])
        
        st.subheader("📥 Exportar Dados")
        csv = exportar_csv(produtos)
        st.download_button(
            label="📥 Baixar CSV",
            data=csv,
            file_name=f"estoque_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("Nenhum produto cadastrado.")

# ========== FOOTER ==========
st.sidebar.markdown("---")
st.sidebar.caption(f"Gateway MCP Varejo | {datetime.now().strftime('%Y-%m-%d %H:%M')}")