# DOCKERFILE FRONTEND


# 1. Immagine Python ufficiale in versione "slim"
# Leggera e coerente con quella utilizzata per il backend.
FROM python:3.10-slim


# 2. Directory di lavoro all'interno del container
# Impostata su /progetto per garantire che i path relativi usati nel codice
# (es. per caricare i template Jinja2) siano risolti correttamente.
WORKDIR /progetto


# 3. VARIABILE D'AMBIENTE PYTHONPATH
# Istruisce Python a considerare la root /progetto come punto di partenza
# per la ricerca dei moduli, permettendo l'importazione corretta di frontend.src.frontend.
ENV PYTHONPATH=/progetto


# 4. INSTALLAZIONE DIPENDENZE (Cache Optimized)
# Copiamo solo il file dei requisiti per evitare di reinstallare tutto
# ad ogni modifica del codice sorgente.
COPY frontend/requirements.txt ./frontend/
RUN pip install --no-cache-dir -r frontend/requirements.txt


# 5. COPIA SORGENTI FRONTEND
# Include il codice Python, la cartella 'src' e la cartella 'templates' con i file HTML.
COPY frontend/ ./frontend/


# 6. COPIA FILE CONDIVISI
# Fondamentale: il frontend ha bisogno di accedere a domains.json e ai dati del Gold Standard
# per popolare dinamicamente i menu di selezione nell'interfaccia utente.
COPY domains.json .
COPY gs_data/ ./gs_data/


# 7. ESPOSIZIONE PORTA
# Dichiariamo la porta 8004, dedicata al servizio Web Frontend come da specifiche.
EXPOSE 8004


# 8. COMANDO DI AVVIO
# Lanciamo l'applicazione tramite Uvicorn.
# Usiamo il flag -m per eseguire uvicorn come modulo, puntando correttamente
# all'app definita nel file frontend.py.
CMD ["python", "-m", "uvicorn", "frontend.src.frontend:app", "--host", "0.0.0.0", "--port", "8004"]