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




# -----------------------------------------------------------------------------
# Helper: piccoli wrapper attorno a httpx per centralizzare timeout/host
# -----------------------------------------------------------------------------
async def _get_json(client: httpx.AsyncClient, path: str,
                    params: Optional[Dict[str, Any]] = None,
                    default: Any = None) -> Any:
    """GET tollerante: in caso di errore restituisce `default` invece di sollevare."""
    try:
        r = await client.get(f"{BACKEND_URL}{path}", params=params or {})
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return default




async def _post_json(client: httpx.AsyncClient, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST che restituisce sempre un dict (con eventuale chiave 'error')."""
    try:
        r = await client.post(f"{BACKEND_URL}{path}", json=payload)
        if r.status_code == 200:
            return r.json()
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        return {"error": f"HTTP {r.status_code}: {detail}"}
    except Exception as e:
        return {"error": str(e)}




async def _delete_json(client: httpx.AsyncClient, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        r = await client.request("DELETE", f"{BACKEND_URL}{path}", json=payload)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}




async def _fetch_all_gs_urls(client: httpx.AsyncClient, domains: List[str]) -> List[str]:
    """Raccoglie tutti gli URL del GS scorrendo dominio per dominio."""
    out: List[str] = []
    for d in domains:
        data = await _get_json(client, "/gold_standard_urls", params={"domain": d}, default={})
        out.extend(data.get("gold_standard_urls", []) or [])
    return out




# -----------------------------------------------------------------------------
# HOME
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        status = await _get_json(client, "/status",
                                 default={"backend": "error", "database": "error", "ollama": "error"})
        domains_payload = await _get_json(client, "/domains", default={"domains": []})


    return templates.TemplateResponse("home.html", {
        "request": request,
        "active_page": "home",
        "status": status,
        "domains": domains_payload.get("domains", []),
    })




# -----------------------------------------------------------------------------
# PARSER & EVALUATION
# -----------------------------------------------------------------------------
@app.get("/parser", response_class=HTMLResponse)
async def parser_form(request: Request):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        domains_payload = await _get_json(client, "/domains", default={"domains": []})
        gs_urls = await _fetch_all_gs_urls(client, domains_payload.get("domains", []))


    return templates.TemplateResponse("parser.html", {
        "request": request,
        "active_page": "parser",
        "gs_urls": gs_urls,
        "submitted_url": "",
        "mode": "live",
        "result": None,
        "metrics": None,
        "judge": None,
        "error": None,
    })




@app.post("/parser", response_class=HTMLResponse)
async def parser_submit(request: Request,
                        url: str = Form(...),
                        mode: str = Form("live")):
    local = (mode == "local")
    result: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    judge: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        domains_payload = await _get_json(client, "/domains", default={"domains": []})
        gs_urls = await _fetch_all_gs_urls(client, domains_payload.get("domains", []))


        # 1) parse
        parse_resp = await _post_json(client, "/parse", {"url": url, "local": local})
        if "error" in parse_resp:
            error = parse_resp["error"]
        else:
            result = parse_resp


            # 2) Se l'URL è nel Gold Standard, recupera il gold e calcola metriche + judge
            if url in gs_urls:
                gs_resp = await _get_json(client, "/gold_standard", params={"url": url}, default={})
                gold_text = gs_resp.get("gold_text", "")
                if gold_text:
                    result["gold_text"] = gold_text
                    eval_resp = await _post_json(client, "/evaluate", {
                        "parsed_text": result.get("parsed_text", ""),
                        "gold_text": gold_text,
                    })
                    if "error" not in eval_resp:
                        metrics = eval_resp.get("token_level_eval")
                    judge_resp = await _post_json(client, "/evaluate_judge", {
                        "parsed_text": result.get("parsed_text", ""),
                        "gold_text": gold_text,
                    })
                    if "error" not in judge_resp:
                        judge = judge_resp


    return templates.TemplateResponse("parser.html", {
        "request": request,
        "active_page": "parser",
        "gs_urls": gs_urls,
        "submitted_url": url,
        "mode": mode,
        "result": result,
        "metrics": metrics,
        "judge": judge,
        "error": error,
    })




# -----------------------------------------------------------------------------
# GOLD STANDARD BUILDER
# -----------------------------------------------------------------------------
async def _gs_context(client: httpx.AsyncClient, selected_domain: Optional[str]) -> Dict[str, Any]:
    """Contesto comune (lista domini + URL del dominio selezionato)."""
    domains_payload = await _get_json(client, "/domains", default={"domains": []})
    domains = domains_payload.get("domains", [])
    if not selected_domain and domains:
        selected_domain = domains[0]
    gs_entries: List[str] = []
    if selected_domain:
        data = await _get_json(client, "/gold_standard_urls",
                               params={"domain": selected_domain}, default={})
        gs_entries = data.get("gold_standard_urls", []) or []
    return {"domains": domains, "selected_domain": selected_domain, "gs_entries": gs_entries}




@app.get("/gs_builder", response_class=HTMLResponse)
async def gs_builder_get(request: Request, domain: Optional[str] = None):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        ctx = await _gs_context(client, domain)


    return templates.TemplateResponse("gs_builder.html", {
        "request": request,
        "active_page": "gs_builder",
        **ctx,
        "submitted_url": "",
        "html_text": "",
        "flash": None,
    })




@app.post("/gs_builder/fetch", response_class=HTMLResponse)
async def gs_builder_fetch(request: Request,
                           domain: str = Form(...),
                           url: str = Form(...)):
    """Scarica l'HTML chiedendo al backend di fare un parse live."""
    html_text = ""
    flash = None


    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        parse_resp = await _post_json(client, "/parse", {"url": url, "local": False})
        if "error" in parse_resp:
            flash = {"kind": "error", "message": f"Download fallito: {parse_resp['error']}"}
        else:
            html_text = parse_resp.get("html_text", "")
            if not html_text:
                flash = {"kind": "warn", "message": "Il backend non ha restituito HTML."}
            else:
                # Salva subito la risorsa nel DB così è disponibile per il save successivo
                add_resp = await _post_json(client, "/add_web_resource",
                                            {"url": url, "html_text": html_text})
                if add_resp.get("status", "").startswith("error"):
                    flash = {"kind": "warn",
                             "message": f"HTML scaricato ma non salvato: {add_resp.get('status')}"}


        ctx = await _gs_context(client, domain)


    return templates.TemplateResponse("gs_builder.html", {
        "request": request,
        "active_page": "gs_builder",
        **ctx,
        "submitted_url": url,
        "html_text": html_text,
        "flash": flash,
    })




@app.post("/gs_builder/save", response_class=HTMLResponse)
async def gs_builder_save(request: Request,
                          url: str = Form(...),
                          domain: str = Form(...),
                          html_text: str = Form(""),
                          gold_text: str = Form(...)):
    """Salva web_resource + gold_standard nel DB tramite gli endpoint dedicati."""
    flash = None
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        # Assicura che la web_resource sia presente (upsert lato backend)
        if html_text:
            await _post_json(client, "/add_web_resource",
                             {"url": url, "html_text": html_text})
        gs_resp = await _post_json(client, "/add_gold_standard",
                                   {"url": url, "gold_text": gold_text})
        if gs_resp.get("status") == "ok":
            flash = {"kind": "ok", "message": f"Salvato nel database: {url}"}
        else:
            flash = {"kind": "error",
                     "message": f"Salvataggio fallito: {gs_resp.get('status') or gs_resp.get('error')}"}


        ctx = await _gs_context(client, domain)


    return templates.TemplateResponse("gs_builder.html", {
        "request": request,
        "active_page": "gs_builder",
        **ctx,
        "submitted_url": "",
        "html_text": "",
        "flash": flash,
    })




@app.post("/gs_builder/delete")
async def gs_builder_delete(url: str = Form(...), domain: str = Form("")):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        await _delete_json(client, "/gold_standard", {"url": url})
    # Redirect verso la pagina del dominio per evitare ri-submit al refresh
    suffix = f"?domain={domain}" if domain else ""
    return RedirectResponse(url=f"/gs_builder{suffix}", status_code=303)




# -----------------------------------------------------------------------------
# STATS
# -----------------------------------------------------------------------------
@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    rows: List[Dict[str, Any]] = []
    totals = {"web_resources": 0, "gold_standard": 0, "domains": 0, "avg_f1": None}
    error: Optional[str] = None
    schema: Dict[str, Any] = {}


    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, trust_env=False) as client:
        stats = await _get_json(client, "/db_stats", default=None)
        schema = await _get_json(client, "/db_schema", default={}) or {}


    if stats is None:
        error = "Impossibile recuperare /db_stats dal backend."
    else:
        web_res = stats.get("web_resources", {}) or {}
        gs = stats.get("gold_standard", {}) or {}
        avg_eval = stats.get("avg_eval", {}) or {}
        avg_judge = stats.get("avg_eval_judge", {}) or {}


        all_domains = set(web_res) | set(gs) | set(avg_eval) | set(avg_judge)
        f1_values: List[float] = []
        for d in sorted(all_domains):
            tle = (avg_eval.get(d) or {}).get("token_level_eval") or {}
            judge = (avg_judge.get(d) or {}).get("judge_score")
            f1 = tle.get("f1")
            if isinstance(f1, (int, float)):
                f1_values.append(float(f1))
            rows.append({
                "domain": d,
                "web_resources": web_res.get(d, 0),
                "gold_standard": gs.get(d, 0),
                "precision": tle.get("precision"),
                "recall": tle.get("recall"),
                "f1": f1,
                "judge_score": judge,
            })


        totals["web_resources"] = sum(web_res.values()) if web_res else 0
        totals["gold_standard"] = sum(gs.values()) if gs else 0
        totals["domains"] = len(all_domains)
        if f1_values:
            totals["avg_f1"] = sum(f1_values) / len(f1_values)


    return templates.TemplateResponse("stats.html", {
        "request": request,
        "active_page": "stats",
        "rows": rows,
        "totals": totals,
        "schema": schema,
        "error": error,
    })



