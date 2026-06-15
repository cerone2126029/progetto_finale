"""
Modulo per la valutazione automatica del testo estratto rispetto al Gold Standard.
Implementa le metriche token-level (Precision, Recall, F1-Score) richieste
dalle direttive del progetto per misurare l'efficacia dei parser.
"""

import re
import string
import mistune
from bs4 import BeautifulSoup
from collections import Counter

def remove_markdown(md: str) -> str:
    """
    Rimuove i costrutti Markdown da una stringa, restituendo solo il testo puro.
    Questa operazione è fondamentale prima della valutazione per evitare che la
    sintassi di formattazione (es. asterischi, link) alteri il conteggio dei token.
    """
    if not md: 
        return ""
        
    html = mistune.html(md)
    soup = BeautifulSoup(html, "html.parser")
    
    text = soup.get_text(separator=' ')
    
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def tokenize(text: str) -> list:
    """
    Normalizza il testo e lo trasforma in una LISTA di token.
    """
    if not text:
        return []
    
    translator = str.maketrans('', '', string.punctuation)
    clean_text = text.lower().translate(translator)
    
    return clean_text.split()


def token_level_eval(parsed_text: str, gold_text: str) -> dict:
    """
    Calcola Precision, Recall e F1-Score a livello di token tra il testo
    generato dal parser (ipotesi) e il testo di riferimento (Gold Standard).
    """

    parsed_clean = remove_markdown(parsed_text)
    gold_clean = remove_markdown(gold_text)

    parsed_tokens = tokenize(parsed_clean)
    gold_tokens = tokenize(gold_clean)

    if not parsed_tokens and not gold_tokens:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not parsed_tokens or not gold_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    parsed_counts = Counter(parsed_tokens)
    gold_counts = Counter(gold_tokens)

    common_counts = parsed_counts & gold_counts
    tp = sum(common_counts.values())

    precision = tp / len(parsed_tokens)
    recall = tp / len(gold_tokens)

    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * (precision * recall) / (precision + recall)

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4)
    }
