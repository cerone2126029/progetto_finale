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
        
    # Converte il Markdown in un albero HTML per una destrutturazione sicura
    html = mistune.html(md)
    soup = BeautifulSoup(html, "html.parser")
    
    # get_text() estrae automaticamente tutto il testo eliminando i tag.
    # Usiamo lo spazio come separatore per evitare che parole adiacenti a tag 
    # HTML rimossi si fondano erroneamente tra loro (es. "parola1</b>parola2").
    text = soup.get_text(separator=' ')
    
    # Collassa eventuali spazi multipli o nuove linee in un singolo spazio
    # per garantire una tokenizzazione pulita nel passaggio successivo.
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


def tokenize(text: str) -> list:
    """
    Normalizza il testo e lo trasforma in una LISTA di token.
    ATTENZIONE: Restituisce una lista e non un set per mantenere le ripetizioni,
    requisito essenziale per il calcolo corretto tramite logica a multiset.
    """
    if not text:
        return []
    
    # Crea una tabella di traduzione altamente ottimizzata per rimuovere 
    # tutta la punteggiatura standard definita nel modulo 'string'.
    translator = str.maketrans('', '', string.punctuation)
    
    # Mette in minuscolo per una valutazione case-insensitive,
    # applica la rimozione della punteggiatura e divide la stringa in singole parole.
    clean_text = text.lower().translate(translator)
    
    return clean_text.split()


def token_level_eval(parsed_text: str, gold_text: str) -> dict:
    """
    Calcola Precision, Recall e F1-Score a livello di token tra il testo
    generato dal parser (ipotesi) e il testo di riferimento (Gold Standard).
    """
    
    # 1. Pulizia obbligatoria del Markdown (come richiesto dall'esonero)
    # Entrambi i testi vengono ridotti a stringhe di testo puro.
    parsed_clean = remove_markdown(parsed_text)
    gold_clean = remove_markdown(gold_text)

    # 2. Tokenizzazione
    # Estrae i vettori di parole dai testi puliti.
    parsed_tokens = tokenize(parsed_clean)
    gold_tokens = tokenize(gold_clean)

    # 3. Gestione dei casi limite (testi vuoti)
    # Evita errori matematici come la divisione per zero.
    if not parsed_tokens and not gold_tokens:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not parsed_tokens or not gold_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    # 4. Calcolo dei True Positives tramite Counter (Multiset Intersection)
    # Esempio: se "gatto" compare 3 volte nel parser e 2 volte nel gold, il Counter
    # capisce che i match corretti per "gatto" sono 2 (prende il minimo).
    parsed_counts = Counter(parsed_tokens)
    gold_counts = Counter(gold_tokens)
    
    # L'operatore '&' tra oggetti Counter calcola l'intersezione tra multiset,
    # restituendo un nuovo Counter con le frequenze minime per le chiavi comuni.
    common_counts = parsed_counts & gold_counts
    tp = sum(common_counts.values())

    # 5. Calcolo delle Metriche Finali
    # Precision: percentuale di parole del parser che sono corrette rispetto al Gold.
    precision = tp / len(parsed_tokens)
    # Recall: percentuale di parole del Gold che il parser è riuscito a catturare.
    recall = tp / len(gold_tokens)

    # Media armonica tra Precision e Recall (F1-Score)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * (precision * recall) / (precision + recall)

    # Restituisce i risultati arrotondati a 4 cifre decimali per migliore leggibilità
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4)
    }
