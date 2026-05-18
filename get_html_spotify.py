import urllib.request
from urllib.error import URLError
import json

def scarica_html_in_json(url: str, nome_file_output: str = "html_output_spotify.json"):
    # Intestazioni fittizie avanzate per simulare perfettamente un browser Mac reale
    # e ingannare i blocchi anti-bot di Google Cache e altri domini.
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3"
    }

    req = urllib.request.Request(url, headers=headers)

    try:
        print(f"⏳ Scaricando l'HTML da: {url} ...")
        with urllib.request.urlopen(req) as response:
            # 1. Leggiamo i byte grezzi
            raw_bytes = response.read()
            
            # 2. Decodifica flessibile a prova di crash (UTF-8 prima, Latin-1 poi)
            try:
                html_content = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                html_content = raw_bytes.decode('latin-1', errors='replace')
            
            # 3. Prepariamo la struttura del dizionario (JSON)
            dati_json = {
                "url": url,
                "html": html_content
            }
            
            # 4. Salviamo direttamente in un file .json
            with open(nome_file_output, "w", encoding="utf-8") as f:
                json.dump(dati_json, f, indent=4, ensure_ascii=False)
                
            print(f"✅ File JSON generato con successo! Lo trovi in '{nome_file_output}'.")
            
    except URLError as e:
        print(f"❌ Errore durante il download: {e.reason}")
    except Exception as e:
        print(f"❌ Si è verificato un errore imprevisto: {e}")

# L'URL di Spotify tramite Google Cache fornito per il progetto
mio_url = "https://open.spotify.com/episode/1JjRqVGuRkzkS9nexDxiLh"

scarica_html_in_json(mio_url)