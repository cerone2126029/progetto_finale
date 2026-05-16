import urllib.request
from urllib.error import URLError
import json

def scarica_html_in_json(url: str):
    # User-Agent fittizio per evitare blocchi dai firewall dei siti
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    req = urllib.request.Request(url, headers=headers)

    try:
        print(f"⏳ Scaricando l'HTML da: {url} ...")
        with urllib.request.urlopen(req) as response:
            html_content = response.read().decode('utf-8')
            
            # Prepariamo la struttura del dizionario (JSON)
            dati_json = {
                "url": url,
                "html": html_content
            }
            
            # Salviamo direttamente in un file .json
            # indent=4 lo rende leggibile, ensure_ascii=False mantiene i caratteri accentati corretti
            nome_file = "html_output.json"
            with open(nome_file, "w", encoding="utf-8") as f:
                json.dump(dati_json, f, indent=4, ensure_ascii=False)
                
            print(f"✅ File JSON generato con successo! Lo trovi in '{nome_file}'.")
            print("💡 Puoi copiare direttamente il blocco della stringa 'html' nel tuo Gold Standard.")
            
    except URLError as e:
        print(f"❌ Errore durante il download: {e.reason}")

# Sostituisci questo link con l'URL che vuoi scaricare
mio_url = "https://en.wikipedia.org/wiki/Humid_Chaco"

scarica_html_in_json(mio_url)