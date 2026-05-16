from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import httpx
import os

app = FastAPI(title="Frontend Esonero")

# ==============================================================
# CONFIGURAZIONI E PERCORSI (100% COMPLIANT CON LE SLIDE)
# ==============================================================

# RISPETTA LA SLIDE: Solo path relativi. 
# Dato che il Dockerfile imposta il WORKDIR su /progetto,
# il path relativo corretto per i template è esattamente questo:
templates = Jinja2Templates(directory="frontend/templates")

# Legge la variabile passata dal docker-compose.yaml
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8003")

# ==============================================================
# FUNZIONI DI SUPPORTO
# ==============================================================
async def fetch_gs_urls(client: httpx.AsyncClient) -> list:
    """Recupera tutti gli URL del Gold Standard dal backend per popolare la tendina."""
    gs_urls = []
    try:
        # 1. Chiediamo al backend la lista dei domini supportati
        dom_res = await client.get(f"{BACKEND_URL}/domains")
        if dom_res.status_code == 200:
            domains = dom_res.json().get("domains", [])
            
            # 2. Per ogni dominio, chiediamo i dati del Gold Standard
            for d in domains:
                gs_res = await client.get(f"{BACKEND_URL}/full_gold_standard", params={"domain": d})
                if gs_res.status_code == 200:
                    entries = gs_res.json().get("gold_standard", [])
                    for entry in entries:
                        gs_urls.append(entry.get("url"))
    except Exception as e:
        print(f"Errore recupero URL Gold Standard: {e}")
    
    return gs_urls

# ==============================================================
# ROTTE DELL'APPLICAZIONE
# ==============================================================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Carica la pagina iniziale e popola la tendina."""
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        gs_urls = await fetch_gs_urls(client)
        
    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={
            "request": request, 
            "gold_standard_urls": gs_urls
        }
    )

@app.post("/analizza", response_class=HTMLResponse)
async def analizza(request: Request, url: str = Form(...)):
    """Gestisce sia le query libere che i test sul Gold Standard."""
    risultato = {"url": url}
    
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        gs_urls = await fetch_gs_urls(client)
        is_gs = url in gs_urls
        
        try:
            if is_gs:
                # --- FLUSSO GOLD STANDARD ---
                gs_res = await client.get(f"{BACKEND_URL}/gold_standard", params={"url": url})
                if gs_res.status_code != 200:
                    raise Exception(gs_res.json().get("detail", "Errore recupero GS dal backend."))
                
                gs_data = gs_res.json()
                html_text = gs_data.get("html_text", "")
                gold_text = gs_data.get("gold_text", "")
                
                parse_payload = {"url": url, "html_text": html_text}
                parse_res = await client.post(f"{BACKEND_URL}/parse", json=parse_payload)
                if parse_res.status_code != 200:
                    raise Exception(parse_res.json().get("detail", "Errore durante il parsing del GS."))
                
                parsed_text = parse_res.json().get("parsed_text", "")
                
                eval_payload = {"parsed_text": parsed_text, "gold_text": gold_text}
                eval_res = await client.post(f"{BACKEND_URL}/evaluate", json=eval_payload)
                if eval_res.status_code != 200:
                    raise Exception(eval_res.json().get("detail", "Errore durante l'evaluate."))
                
                metrics = eval_res.json().get("token_level_eval", {})
                
                risultato.update({
                    "html_text": html_text,
                    "parsed_text": parsed_text,
                    "gold_text": gold_text,
                    "metrica": {
                        "precision": round(metrics.get("precision", 0.0), 4),
                        "recall": round(metrics.get("recall", 0.0), 4),
                        "f1": round(metrics.get("f1", 0.0), 4)
                    }
                })
                
            else:
                # --- FLUSSO URL LIBERO ---
                parse_res = await client.get(f"{BACKEND_URL}/parse", params={"url": url})
                if parse_res.status_code != 200:
                    raise Exception(parse_res.json().get("detail", "Errore di crawling o parsing."))
                
                parse_data = parse_res.json()
                
                risultato.update({
                    "html_text": parse_data.get("html_text", "HTML non disponibile per URL liberi."),
                    "parsed_text": parse_data.get("parsed_text", "")
                })

        except Exception as e:
            risultato["errore"] = str(e)

    return templates.TemplateResponse(
        request=request,
        name="index.html", 
        context={
            "request": request, 
            "gold_standard_urls": gs_urls,
            "risultato": risultato
        }
    )