# DOCKERFILE BACKEND
# Container che ospita FastAPI + i parser + il connettore MariaDB + il client Ollama.


FROM python:3.10-slim


WORKDIR /progetto


# Dipendenze di sistema:
#   * libmariadb-dev + gcc: necessari a compilare/linkare il client Python MariaDB
#   * curl/ca-certificates: utili per healthcheck e fetch da Ollama
# Le installiamo prima del pip install per sfruttare la cache dei layer Docker.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmariadb-dev \
        gcc \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*


# Installa le dipendenze Python (layer separato per ottimizzare la cache)
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt


# Setup Chromium per Crawl4AI (Playwright)
RUN playwright install chromium
RUN playwright install-deps


# Codice sorgente del backend
COPY backend/ ./backend/


# File condivisi (lista domini + Gold Standard JSON per il bootstrap del DB)
COPY domains.json .
COPY gs_data/ ./gs_data/


EXPOSE 8003


# Avvio del server (no reload in produzione)
CMD ["python", "-m", "uvicorn", "backend.src.server:app", "--host", "0.0.0.0", "--port", "8003"]
