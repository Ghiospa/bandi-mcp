# Immagine per il deploy pubblico (Railway, Render, Fly, qualsiasi host Docker).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BANDI_HOST=0.0.0.0 \
    BANDI_LOG_DB=/dati/uso.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bandi_mcp/ ./bandi_mcp/
COPY data/ ./data/

# Il log d'uso va su volume: il filesystem dei container è effimero.
# Senza volume montato resta comunque la copia su stdout (vedi bandi_mcp/uso.py).
RUN mkdir -p /dati
VOLUME ["/dati"]

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

CMD ["python", "-m", "bandi_mcp.server", "--http"]
