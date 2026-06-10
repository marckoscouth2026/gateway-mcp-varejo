FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema necessárias
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências Python
COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt

# Copia o código
COPY dashboard.py .

# Expõe a porta
EXPOSE 10000

# Comando para rodar o Streamlit
CMD ["streamlit", "run", "dashboard.py", "--server.port=10000", "--server.enableCORS=false", "--server.enableXsrfProtection=false"]
