"""
Modulo di routing e rendering per il Frontend dell'applicazione.
Espone le interfacce utente sviluppate in HTML/Jinja2 e funge da API Gateway,
orchestrando le chiamate asincrone verso il backend per recuperare i dati, 
lanciare i parser e gestire il database (CRUD del Gold Standard e statistiche).
"""

import os
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8003")
HTTP_TIMEOUT = float(os.getenv("FRONTEND_HTTP_TIMEOUT", "180"))

app = FastAPI(title="Frontend Progetto Finale")
templates = Jinja2Templates(directory="frontend/templates")

async def _get_json(client: httpx.AsyncClient, path: str, params: Optional[Dict[str, Any]] = None, default: Any = None) -> Any:
    """
    Esegue una richiesta HTTP GET asincrona verso il backend.
    """

    try:
        r = await client.get(f"{BACKEND_URL}{path}", params=params or {})
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return default


async def _post_json(client: httpx.AsyncClient, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Esegue una richiesta HTTP POST asincrona verso il backend.
    """

    try:
        r = await client.post(f"{BACKEND_URL}{path}", json=payload)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


async def _delete_json(client: httpx.AsyncClient, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Esegue una richiesta HTTP DELETE asincrona verso il backend con annesso payload JSON.
    """

    try:
        r = await client.request("DELETE", f"{BACKEND_URL}{path}", json=payload)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


async def _fetch_all_gs_urls(client: httpx.AsyncClient, domains: List[str]) -> List[str]:
    """
    Recupera la lista completa di tutti gli URL Gold Standard disponibili
    nel database per un insieme di domini specificati.
    """

    out: List[str] = []
    for d in domains:
        data = await _get_json(client, "/gold_standard_urls", params={"domain": d}, default={})
        out.extend(data.get("gold_standard_urls", []) or [])
    return out

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Gestisce la rotta principale (Home) dell'interfaccia utente.
    Esegue un health check verso le componenti del backend e recupera
    la lista dei domini supportati per visualizzarli nella dashboard.
    """

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        status = await _get_json(client, "/status", default={"backend": "error", "database": "error", "ollama": "error"})
        domains_payload = await _get_json(client, "/domains", default={"domains": []})

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "active_page": "home",
            "status": status,
            "domains": domains_payload.get("domains", [])
        }
    )

@app.get("/parser", response_class=HTMLResponse)
async def parser_form(request: Request):
    """
    Renderizza l'interfaccia della sezione Parser & Evaluation in stato inziale (GET).
    Recupera gli URL Gold Standard per popolare eventuali menu a tendina.
    """
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        domains = (await _get_json(client, "/domains", default={"domains": []})).get("domains", [])
        gs_urls = await _fetch_all_gs_urls(client, domains)
       
    return templates.TemplateResponse(
        request=request,
        name="parser.html",
        context={
            "active_page": "parser", "gs_urls": gs_urls,
            "submitted_url": "", "mode": "live", "result": None,
            "metrics": None, "judge": None, "error": None
        }
    )


@app.post("/parser", response_class=HTMLResponse)
async def parser_submit(request: Request, url: str = Form(...), mode: str = Form("live")):
    """
    Elabora la sottomissione del form per il parsing e la valutazione di un URL (POST).
    Determina la modalità operativa (Live vs Local), invoca l'endpoint del backend e,
    se l'URL è presente nei Gold Standard, orchestra la valutazione incrociata
    (sia tramite metriche deterministiche F1, sia tramite l'LLM Judge).
    """

    local = (mode == "local")
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        domains = (await _get_json(client, "/domains", default={"domains": []})).get("domains", [])
        gs_urls = await _fetch_all_gs_urls(client, domains)
        result, metrics, judge, error = None, None, None, None
       
        parse_resp = await _post_json(client, "/parse", {"url": url, "local": local})
        if "error" in parse_resp:
            error = parse_resp["error"]
        else:
            result = parse_resp
            if url in gs_urls:
                gs_resp = await _get_json(client, "/gold_standard", params={"url": url}, default={})
                gold_text = gs_resp.get("gold_text", "")
                if gold_text:
                    result["gold_text"] = gold_text
                    metrics = (await _post_json(client, "/evaluate", {"parsed_text": result.get("parsed_text", ""), "gold_text": gold_text})).get("token_level_eval")
                    judge = await _post_json(client, "/evaluate_judge", {"parsed_text": result.get("parsed_text", ""), "gold_text": gold_text})
   
    return templates.TemplateResponse(
        request=request,
        name="parser.html",
        context={
            "active_page": "parser", "gs_urls": gs_urls,
            "submitted_url": url, "mode": mode, "result": result,
            "metrics": metrics, "judge": judge, "error": error
        }
    )

@app.get("/gs_builder", response_class=HTMLResponse)
async def gs_builder_get(request: Request, domain: Optional[str] = None):
    """
    Visualizza la schermata dedicata alla gestione CRUD dei Gold Standard (GET).
    Mostra i domini supportati e la lista delle entry già archiviate nel database.
    """

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        domains = (await _get_json(client, "/domains", default={"domains": []})).get("domains", [])
        sel = domain or (domains[0] if domains else "")
        gs_entries = (await _get_json(client, "/gold_standard_urls", params={"domain": sel}, default={})).get("gold_standard_urls", []) or []
       
    return templates.TemplateResponse(
        request=request,
        name="gs_builder.html",
        context={
            "active_page": "gs_builder", "domains": domains,
            "selected_domain": sel, "gs_entries": gs_entries,
            "submitted_url": "", "html_text": "", "flash": None
        }
    )


@app.post("/gs_builder/fetch", response_class=HTMLResponse)
async def gs_builder_fetch(request: Request, domain: str = Form(...), url: str = Form(...)):
    """
    Scarica il DOM HTML in tempo reale per un URL specifico e lo restituisce al frontend,
    preparando l'interfaccia per la compilazione manuale del Gold Standard da parte dell'utente.
    """

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        parse_resp = await _post_json(client, "/parse", {"url": url, "local": False})
        html_text = parse_resp.get("html_text", "") if "error" not in parse_resp else ""
        flash = {"kind": "error", "message": parse_resp["error"]} if "error" in parse_resp else None
       
        domains = (await _get_json(client, "/domains", default={"domains": []})).get("domains", [])
        gs_entries = (await _get_json(client, "/gold_standard_urls", params={"domain": domain}, default={})).get("gold_standard_urls", []) or []
       
    return templates.TemplateResponse(
        request=request,
        name="gs_builder.html",
        context={
            "active_page": "gs_builder", "domains": domains, "selected_domain": domain,
            "gs_entries": gs_entries, "submitted_url": url, "html_text": html_text, "flash": flash
        }
    )


@app.post("/gs_builder/save", response_class=HTMLResponse)
async def gs_builder_save(request: Request, url: str = Form(...), domain: str = Form(...), html_text: str = Form(""), gold_text: str = Form(...)):
    """
    Persiste nel database sia la risorsa web (HTML grezzo) sia il testo di riferimento
    (Gold Standard) scritto dall'utente, consolidando le basi per le valutazioni offline.
    """

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        if html_text: await _post_json(client, "/add_web_resource", {"url": url, "html_text": html_text})
        gs_resp = await _post_json(client, "/add_gold_standard", {"url": url, "gold_text": gold_text})
        flash = {"kind": "ok", "message": f"Salvato: {url}"} if gs_resp.get("status") == "ok" else {"kind": "error", "message": "Salvataggio fallito"}
        domains = (await _get_json(client, "/domains", default={"domains": []})).get("domains", [])
        gs_entries = (await _get_json(client, "/gold_standard_urls", params={"domain": domain}, default={})).get("gold_standard_urls", []) or []
       
    return templates.TemplateResponse(
        request=request,
        name="gs_builder.html",
        context={
            "active_page": "gs_builder", "domains": domains, "selected_domain": domain,
            "gs_entries": gs_entries, "submitted_url": "", "html_text": "", "flash": flash
        }
    )


@app.post("/gs_builder/delete")
async def gs_builder_delete(url: str = Form(...), domain: str = Form("")):
    """
    Rimuove un Gold Standard archiviato nel database effettuando una 
    richiesta DELETE verso il backend.
    """

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        await _delete_json(client, "/gold_standard", {"url": url})
    return RedirectResponse(url=f"/gs_builder?domain={domain}", status_code=303)

@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    """
    Recupera i metadati globali e lo schema del database dal backend, 
    aggrega i punteggi (F1-Score e LLM Judge) suddivisi per dominio e renderizza 
    la dashboard visiva delle statistiche.
    """

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        stats = await _get_json(client, "/db_stats", default={})
        schema = await _get_json(client, "/db_schema", default={})
   
    rows = []
    web_res = stats.get("web_resources", {}) or {}
    gs = stats.get("gold_standard", {}) or {}
    avg_eval = stats.get("avg_eval", {}) or {}
    avg_judge = stats.get("avg_eval_judge", {}) or {}
    all_domains = sorted(set(web_res) | set(gs) | set(avg_eval) | set(avg_judge))
   
    for d in all_domains:
        tle = (avg_eval.get(d) or {}).get("token_level_eval") or {}
        rows.append({
            "domain": d, "web_resources": web_res.get(d, 0), "gold_standard": gs.get(d, 0),
            "precision": tle.get("precision"), "recall": tle.get("recall"), "f1": tle.get("f1"),
            "judge_score": (avg_judge.get(d) or {}).get("judge_score")
        })

    f1_values = [r["f1"] for r in rows if r["f1"] is not None]
    avg_f1 = round(sum(f1_values) / len(f1_values), 4) if f1_values else None

    return templates.TemplateResponse(
        request=request,
        name="stats.html",
        context={
            "active_page": "stats", "rows": rows,
            "totals": {
                "web_resources": sum(web_res.values()),
                "gold_standard": sum(gs.values()),
                "domains": len(all_domains),
                "avg_f1": avg_f1,
            },
            "schema": schema, "error": None
        }
    )