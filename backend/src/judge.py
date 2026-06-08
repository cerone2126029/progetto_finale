import json
import os
import re
from typing import Dict, Optional


import httpx




OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


# Limita la lunghezza dei testi nel prompt per non saturare la context window
# dei modelli piccoli (3-4B) e velocizzare l'inferenza su CPU.
MAX_TEXT_CHARS = int(os.getenv("JUDGE_MAX_CHARS", "4000"))
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
    """Tronca aggiungendo un marcatore se serve, per non bucare la context window."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[...troncato...]"




def _build_prompt(parsed_text: str, gold_text: str) -> str:
    return USER_TEMPLATE.format(
        parsed=_truncate(parsed_text, MAX_TEXT_CHARS),
        gold=_truncate(gold_text, MAX_TEXT_CHARS),
    )




def _extract_json(raw: str) -> Optional[dict]:
    if not raw: return None
    # Pulisci da eventuali markdown (spesso i modelli nuovi mettono ```json)
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)
    
    # Cerca la prima { e l'ultima }
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
    Score euristico calcolato sulla copertura dei token, usato solo se l'LLM
    non risponde o restituisce un formato non recuperabile.
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
    """Probe rapido per /status: l'endpoint /api/tags risponde se Ollama è up."""
    target = host or OLLAMA_HOST
    try:
        r = httpx.get(f"{target}/api/tags", timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False




def evaluate_with_judge(parsed_text: str, gold_text: str,
                        model: Optional[str] = None) -> Dict[str, object]:
    """
    Esegue la valutazione LLM-as-Judge.


    Returns: dict con campi obbligatori dalla spec:
        - model_name: nome modello utilizzato
        - judge_score: intero 1..5
        - judge_feedback: stringa
    """
    model_name = model or OLLAMA_MODEL
    prompt = _build_prompt(parsed_text or "", gold_text or "")


    try:
        response = httpx.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "system": SYSTEM_PROMPT,
                # Output deterministico e in formato JSON (Ollama supporta `format: "json"`
                # per forzare il modello a produrre solo JSON valido).
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 256},
            },
            timeout=REQUEST_TIMEOUT,
        )
    except Exception as e:
        result = _fallback(parsed_text, gold_text, f"Ollama irraggiungibile: {e}")
        return {"model_name": model_name, **result}


    if response.status_code != 200:
        result = _fallback(parsed_text, gold_text,
                           f"HTTP {response.status_code} da Ollama")
        return {"model_name": model_name, **result}


    raw = (response.json().get("response") or "").strip()
    data = _extract_json(raw)


    if not data or "score" not in data:
        result = _fallback(parsed_text, gold_text,
                           "LLM non ha rispettato il formato JSON richiesto")
        return {"model_name": model_name, **result}


    # Normalizzazione: score deve essere int 1..5
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

