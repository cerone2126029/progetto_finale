# DOCKERFILE BACKEND 

# 1. Utilizzo dell'immagine base Python ufficiale in versione "slim" 
# per garantire un ambiente leggero ma completo.
FROM python:3.10-slim

# 2. Definizione della directory di lavoro all'interno del container.
# Viene chiamata "/progetto" per coerenza con la struttura root definita nelle specifiche.
WORKDIR /progetto

# 3. OTTIMIZZAZIONE CACHE: Copiamo prima solo il file dei requisiti.
# Docker creerà un layer separato per le dipendenze; se il codice cambia 
# ma i requisiti no, questo step verrà saltato nelle build successive (build veloce).
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# 4. CONFIGURAZIONE PLAYWRIGHT: Necessaria per il funzionamento di Crawl4AI.
# Installiamo il browser Chromium in modalità headless e le relative 
# librerie di sistema (dependencies) necessarie per l'esecuzione su Linux.
RUN playwright install chromium
RUN playwright install-deps

# 5. COPIA DEL CODICE SORGENTE:
# Copiamo l'intera cartella backend nella relativa sottodirectory del container.
COPY backend/ ./backend/

# 6. COPIA DEI FILE CONDIVISI (DATA & CONFIG):
# Questi file risiedono nella root del progetto e sono fondamentali 
# per la logica di business (domini supportati e Gold Standard).
COPY domains.json .
COPY gs_data/ ./gs_data/

# 7. ESPOSIZIONE PORTA:
# Dichiariamo la porta 8003 come richiesto
EXPOSE 8003

# 8. COMANDO DI AVVIO:
# Avviamo il server FastAPI tramite Uvicorn. 
# Usiamo il modulo python -m per garantire che il PYTHONPATH sia risolto correttamente
# partendo dalla root /progetto, puntando all'istanza 'app' dentro server.py.
CMD ["python", "-m", "uvicorn", "backend.src.server:app", "--host", "0.0.0.0", "--port", "8003"]
