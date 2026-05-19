"""
Backend Server (FastAPI).
Agisce come livello di orchestrazione per le API REST richieste dal progetto.
Riceve le richieste HTTP dal frontend (o da script di test), istanzia il parser corretto
in base al dominio, delega il crawling/parsing e gestisce la valutazione tramite evaluator.py.
"""

import json
import sys
import os
from pathlib import Path
from urllib.parse import urlparse

# Aggiunge la directory corrente al PYTHONPATH per consentire le importazioni relative
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# Rimosso BeautifulSoup: il server fa solo il server!
# Le importazioni dei moduli logici sviluppati per l'esonero
from parsers.wikipediaparser import WikipediaParser
from parsers.scaruffiparser import ScaruffiParser
from parsers.travelstategov import TravelStateGov
from parsers.spotifyparser import SpotifyParser 
from evaluator import token_level_eval

# Definizione dei percorsi assoluti per accedere in modo sicuro ai file statici
BASE_DIR = Path(__file__).resolve().parent.parent.parent
GS_DIR = BASE_DIR / "gs_data"
DOMAINS_FILE = BASE_DIR / "domains.json"

# ==========================================
# MODELLI DATI (Pydantic)
# Validazione automatica del body per le POST
# ==========================================
class ParseRequest(BaseModel):
    """Payload per l'endpoint POST /parse."""
    url: str
    html_text: str

class EvaluateRequest(BaseModel):
    """Payload per l'endpoint POST /evaluate."""
    parsed_text: str
    gold_text: str

# ==========================================
# FUNZIONI DI CONFIGURAZIONE E SUPPORTO
# ==========================================
def load_supported_domains():
    """
    Carica la lista dei domini supportati dal file domains.json.
    Fornisce un array di fallback se il file non è reperibile.
    """
    if DOMAINS_FILE.exists():
        with open(DOMAINS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return ["en.wikipedia.org", "it.wikipedia.org", "www.scaruffi.com"]

SUPPORTED_DOMAINS = load_supported_domains()

def get_domain_config(url_or_domain: str, is_url: bool = True):
    """
    Analizza un URL o un nome di dominio e lo mappa al tipo di parser necessario
    e al rispettivo nome del file JSON del Gold Standard.
    """
    domain = urlparse(url_or_domain).netloc.lower() if is_url else url_or_domain.lower()
    
    if "wikipedia.org" in domain:
        return "wikipedia", "dominio_wikipedia_gs.json"
    elif "scaruffi.com" in domain:
        return "scaruffi", "dominio_scaruffi_gs.json"
    elif "travel.state.gov" in domain:
        return "travelstategov", "dominio_travelstategov_gs.json"
    elif "spotify" in domain or "googleusercontent" in domain:
        return "spotify", "dominio_spotify_gs.json"
    return None, None

app = FastAPI(
    title="Web Scraper & Evaluator API",
    description="API ufficiale per l'esonero di Laboratorio di Ingegneria Informatica",
    version="1.0.0"
)

def get_parser_instance(domain_type: str):
    """Factory helper per instanziare il parser corretto"""
    if domain_type == "wikipedia": return WikipediaParser()
    if domain_type == "scaruffi": return ScaruffiParser()
    if domain_type == "travelstategov": return TravelStateGov()
    if domain_type == "spotify": return SpotifyParser()
    raise HTTPException(status_code=400, detail="Parser non implementato per questo dominio.")

# ==========================================
# ENDPOINT API REST
# ==========================================

@app.get("/domains")
def get_domains():
    """Restituisce la lista dei domini su cui il sistema può operare."""
    return {"domains": SUPPORTED_DOMAINS}

@app.get("/parse")
async def get_parse(url: str = Query(..., description="URL da analizzare")):
    """
    Esegue il crawling e il parsing di un URL in tempo reale.
    Risolve il dominio, avvia il crawler e restituisce i dati estratti.
    """
    domain_type, _ = get_domain_config(url)
    if not domain_type: raise HTTPException(status_code=400, detail="Dominio non supportato.")
    
    parser = get_parser_instance(domain_type)
    
    try:
        # Delega il lavoro asincrono al metodo di batching del parser
        results = await parser.parse_batch(urls=[url])
        if not results: raise HTTPException(status_code=404, detail="Impossibile recuperare l'URL.")
        
        data = results[0]
        # Controllo errori propagati dal parser
        if "ERRORE:" in str(data.get("parsed_text", "")):
            raise HTTPException(status_code=400, detail=data["parsed_text"])

        return {
            "url": data.get("url", url),
            "domain": urlparse(url).netloc,
            "title": data.get("title", ""),
            "html_text": data.get("html_text", ""),
            "parsed_text": data.get("parsed_text", "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/parse")
async def post_parse(request: ParseRequest):
    """
    Parsing offline: riceve un URL e il suo codice HTML grezzo e ne estrae il testo pulito.
    Simula il crawling bypassando il download effettivo della pagina.
    """
    domain_type, _ = get_domain_config(request.url)
    if not domain_type: raise HTTPException(status_code=400, detail="Dominio non supportato.")

    parser = get_parser_instance(domain_type)
    
    # Crea un prefisso 'raw:' per forzare l'HTML nel crawler invece di fare una GET HTTP
    fake_url_for_crawler = f"raw:{request.html_text}"

    try:
        results = await parser.parse_batch(urls=[fake_url_for_crawler])
        if not results: raise HTTPException(status_code=500, detail="Il crawler ha fallito l'estrazione raw.")
            
        data = results[0]
        titolo = data.get("title", "")
        # Tenta il fallback in caso manchi il tag title nell'HTML
        if not titolo and hasattr(parser, "extract_fallback_title"):
            titolo = parser.extract_fallback_title(request.url) or ""

        return {
            "url": request.url, 
            "domain": urlparse(request.url).netloc,
            "title": titolo,
            "html_text": request.html_text,
            "parsed_text": data.get("parsed_text", "")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/gold_standard")
def get_gs_entry(url: str = Query(..., description="URL di cui cercare il GS")):
    """
    Cerca nel file JSON del Gold Standard la specifica entry associata a un URL
    e ne restituisce i dettagli (testo originale e testo di riferimento).
    """
    _, gs_file = get_domain_config(url)
    if not gs_file: raise HTTPException(status_code=400, detail="Dominio non supportato.")
    
    path = GS_DIR / gs_file
    if not path.exists(): raise HTTPException(status_code=404, detail="File GS non trovato.")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    for entry in data:
        if entry["url"] == url:
            return {
                "url": entry["url"],
                "domain": urlparse(url).netloc,
                "title": entry.get("title", ""),
                "html_text": entry.get("html_text", ""),
                "gold_text": entry.get("gold_text", "")
            }
    raise HTTPException(status_code=404, detail="URL non presente nel Gold Standard.")

@app.get("/full_gold_standard")
def get_full_gs(domain: str = Query(..., description="Dominio completo")):
    """
    Restituisce in un'unica chiamata l'intero database del Gold Standard
    per un determinato dominio (usato per popolare la tendina del frontend).
    """
    _, gs_file = get_domain_config(domain, is_url=False)
    if not gs_file: raise HTTPException(status_code=400, detail="Dominio non supportato.")

    path = GS_DIR / gs_file
    with open(path, "r", encoding="utf-8") as f: gs_entries = json.load(f)

    return {"gold_standard": [{"url": e["url"], "domain": domain, "title": e.get("title", ""), "html_text": e.get("html_text", ""), "gold_text": e.get("gold_text", "")} for e in gs_entries]}

@app.post("/evaluate")
def evaluate(request: EvaluateRequest):
    """
    Riceve un testo estratto e un testo Gold Standard e calcola le metriche (F1, P, R).
    Il campo 'x_eval' vuoto serve per mantenere la compatibilità con eventuali estensioni LLM.
    """
    metrics = token_level_eval(request.parsed_text, request.gold_text)
    return {"token_level_eval": metrics, "x_eval": {}}

@app.get("/full_gs_eval")
def full_gs_eval(domain: str = Query(..., description="Dominio per evaluation totale")):
    """
    Endpoint per la valutazione massiva: esegue il parsing e la valutazione 
    su tutte le pagine HTML salvate nel Gold Standard per un dato dominio,
    restituendo la media matematica delle metriche finali.
    """
    domain_type, gs_file = get_domain_config(domain, is_url=False)
    if not domain_type: raise HTTPException(status_code=400, detail="Dominio non supportato.")

    path = GS_DIR / gs_file
    with open(path, "r", encoding="utf-8") as f: gs_entries = json.load(f)

    parser = get_parser_instance(domain_type)
    total_metrics = {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    count = 0

    for entry in gs_entries:
        html = entry.get("html_text", "")
        gold = entry.get("gold_text", "")
        # Ignora le voci vuote o non ancora compilate
        if not html or html == "INSERISCI_QUI_L_HTML_DA_CRAWL4AI" or not gold: continue

        # ECCO LA MAGIA: Il server delega il parsing dell'HTML al parser corretto
        parsed = parser.parse_offline_html(html)
            
        m = token_level_eval(parsed, gold)
        for k in total_metrics: total_metrics[k] += m[k]
        count += 1

    if count == 0: return {"token_level_eval": {"precision": 0, "recall": 0, "f1": 0}, "x_eval": {}}
    
    return {
        "token_level_eval": {k: round(v/count, 4) for k, v in total_metrics.items()},
        "x_eval": {}
    }

if __name__ == "__main__":
    print("Server in ascolto sulla porta 8003...")
    uvicorn.run("server:app", host="0.0.0.0", port=8003, reload=True)