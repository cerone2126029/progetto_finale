import urllib.request
from urllib.error import URLError
import json

def scarica_html_in_json(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    req = urllib.request.Request(url, headers=headers)

    try:
        print(f"⏳ Scaricando l'HTML da: {url} ...")
        with urllib.request.urlopen(req) as response:
            # 1. Leggiamo i byte grezzi senza decodificarli subito
            raw_bytes = response.read()
            
            # 2. Tentativo di decodifica flessibile
            try:
                # Proviamo prima lo standard moderno
                html_content = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # Se fallisce (come su Scaruffi), passiamo al formato "vecchia scuola"
                html_content = raw_bytes.decode('latin-1', errors='replace')
            
            # Prepariamo la struttura del dizionario (JSON)
            dati_json = {
                "url": url,
                "html": html_content
            }
            
            # Salviamo direttamente in un file .json
            nome_file = "html_output.json"
            with open(nome_file, "w", encoding="utf-8") as f:
                json.dump(dati_json, f, indent=4, ensure_ascii=False)
                
            print(f"✅ File JSON generato con successo! Lo trovi in '{nome_file}'.")
            
    except URLError as e:
        print(f"❌ Errore durante il download: {e.reason}")
    except Exception as e:
        print(f"❌ Si è verificato un errore imprevisto: {e}")

# Sostituisci questo link con l'URL che vuoi scaricare
mio_url = "https://www.scaruffi.com/vol5/firehose.html"

scarica_html_in_json(mio_url)