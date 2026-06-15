#DOCKERFILE FRONTEND

#Immagine Python ufficiale in versione "slim"
FROM python:3.10-slim


#Directory di lavoro all'interno del container
WORKDIR /progetto

# Istruisce Python a considerare la root /progetto come punto di partenza
ENV PYTHONPATH=/progetto

#Istallazione dipendenze (Cache Optimized)
COPY frontend/requirements.txt ./frontend/
RUN pip install --no-cache-dir -r frontend/requirements.txt

#Copia frontend
COPY frontend/ ./frontend/

#Copia file condivisi
COPY domains.json .
COPY gs_data/ ./gs_data/

#Esposizione porta
EXPOSE 8004

#Comando di avvio
CMD ["python", "-m", "uvicorn", "frontend.src.frontend:app", "--host", "0.0.0.0", "--port", "8004"]