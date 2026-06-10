FROM python:3.11-slim

WORKDIR /app

COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt

COPY dashboard.py .
COPY .streamlit/secrets.toml .streamlit/ 2>/dev/null || true

EXPOSE 10000

CMD ["streamlit", "run", "dashboard.py", "--server.port=10000", "--server.enableCORS=false"]
