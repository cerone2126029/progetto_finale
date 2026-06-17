"""
Modulo per la valutazione semantica tramite LLM-as-a-Judge.
Gestisce l'interazione asincrona con l'istanza locale di Ollama, 
l'ingegnerizzazione del prompt, la validazione strutturata dell'output (JSON)
e implementa un algoritmo di fallback euristico in caso di inattività del modello.
"""

import json
import os
import re
from typing import Dict, Optional
import httpx

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
MAX_TEXT_CHARS = int(os.getenv("JUDGE_MAX_CHARS", "1000"))
REQUEST_TIMEOUT = float(os.getenv("JUDGE_TIMEOUT", "120"))

SYSTEM_PROMPT = (
    "Sei un valutatore esperto di estrazione testuale da pagine web. "
    "Devi confrontare il testo prodotto da un parser con un Gold Standard "
    "(testo di riferimento corretto, costruito manualmente). "
    "Valuta la qualità del testo estratto considerando: contenuto principale "
    "presente, assenza di boilerplate/menu/navigazione, completezza, e fedeltà "
    "rispetto al gold."
)

USER_TEMPLATE = """Confronta i due testi seguenti.

### Testo estratto dal parser
{parsed}

### Testo di riferimento (Gold Standard)
{gold}

Rispondi SOLO con un oggetto JSON valido in questo formato esatto, senza testo aggiuntivo, senza markdown, senza backtick:
{{"score": <intero tra 1 e 5>, "feedback": "<breve descrizione in italiano, max 200 caratteri>"}}

Scala: 1 = pessimo (molto rumore o contenuto mancante), 3 = sufficiente (contenuto principale presente ma con difetti), 5 = ottimo (estrazione fedele al gold)."""


def _truncate(text: str, limit: int) -> str:
    """
    Tronca il testo in ingresso se supera il limite massimo di caratteri consentito,
    aggiungendo un marcatore testuale per avvisare l'LLM del taglio.
    Essenziale per prevenire il superamento della 'context window' del modello.
    """

    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[...troncato...]"


def _build_prompt(parsed_text: str, gold_text: str) -> str:
    """
    Costruisce il prompt utente definitivo iniettando i testi (preventivamente troncati)
    all'interno del template strutturato.
    """

    return USER_TEMPLATE.format(
        parsed=_truncate(parsed_text, MAX_TEXT_CHARS),
        gold=_truncate(gold_text, MAX_TEXT_CHARS),
    )


def _extract_json(raw: str) -> Optional[dict]:
    """
    Estrazione sicura e validazione del payload JSON dalla stringa grezza generata dall'LLM.
    Rimuove preventivamente delimitatori Markdown (es. ```json) spesso inseriti 
    dai modelli di piccola taglia prima di tentare il parsing.
    """

    if not raw: return None
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)
    
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(raw[start:end+1])
        except:
            return None
    return None


def _fallback(parsed_text: str, gold_text: str, reason: str) -> Dict[str, object]:
    """
    Algoritmo euristico di emergenza attivato in caso di timeout, irraggiungibilità 
    dell'LLM o parsing JSON fallito. Calcola uno pseudo-score da 1 a 5 basato sulla 
    copertura matematica dei token (Token Intersection) tra il parser e il Gold Standard.
    """

    if not gold_text:
        return {"score": 1, "feedback": f"Fallback: {reason}. Nessun gold disponibile."}
    parsed_tokens = set(re.findall(r"\w+", (parsed_text or "").lower()))
    gold_tokens = set(re.findall(r"\w+", gold_text.lower()))
    if not gold_tokens:
        return {"score": 1, "feedback": f"Fallback: {reason}."}
    coverage = len(parsed_tokens & gold_tokens) / len(gold_tokens)
    score = max(1, min(5, int(round(1 + coverage * 4))))
    return {"score": score, "feedback": f"Fallback: {reason}. Coverage stimata {coverage:.2f}"}


def ollama_health(host: Optional[str] = None) -> bool:
    """
    Esegue un health check (probing) rapido per verificare se il demone Ollama
    è attivo e pronto a ricevere richieste, interrogando l'endpoint /api/tags.
    """

    target = host or OLLAMA_HOST
    try:
        r = httpx.get(f"{target}/api/tags", timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


async def evaluate_with_judge(parsed_text: str, gold_text: str,
                              model: Optional[str] = None) -> Dict[str, object]:
    """
    Entry point asincrono principale per la valutazione.
    Invia la richiesta di valutazione al modello LLM tramite una chiamata HTTP asincrona 
    non bloccante. Applica parametri restrittivi (temperature 0.0, format JSON) e
    gestisce attivamente il routing verso il fallback in caso di fallimenti di rete o di formato.
    """
    
    model_name = model or OLLAMA_MODEL
    prompt = _build_prompt(parsed_text or "", gold_text or "")

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "system": SYSTEM_PROMPT,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 256},
                },
            )
    except Exception as e:
        result = _fallback(parsed_text, gold_text, f"Ollama irraggiungibile: {e}")
        return {"model_name": model_name, "judge_score": result["score"],
                "judge_feedback": result["feedback"]}

    if response.status_code != 200:
        result = _fallback(parsed_text, gold_text, f"HTTP {response.status_code}")
        return {"model_name": model_name, "judge_score": result["score"],
                "judge_feedback": result["feedback"]}

    raw = (response.json().get("response") or "").strip()
    data = _extract_json(raw)

    if not data or "score" not in data:
        result = _fallback(parsed_text, gold_text, "LLM non ha rispettato il formato JSON")
        return {"model_name": model_name, "judge_score": result["score"],
                "judge_feedback": result["feedback"]}

    try:
        score = int(data["score"])
    except (TypeError, ValueError):
        score = 1
    score = max(1, min(5, score))
    feedback = str(data.get("feedback") or "").strip()[:500]

    return {
        "model_name": model_name,
        "judge_score": score,
        "judge_feedback": feedback or "Nessun feedback fornito.",
    }