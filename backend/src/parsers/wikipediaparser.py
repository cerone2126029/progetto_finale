"""
Parser specifico per i domini Wikipedia (en.wikipedia.org, it.wikipedia.org).
Implementa configurazioni e regole euristiche per ignorare tabelle, infobox,
riferimenti bibliografici e note, garantendo l'estrazione del solo testo enciclopedico pulito.
"""

import re
from urllib.parse import unquote
from typing import Optional
from crawl4ai import CrawlerRunConfig, CacheMode
from parsers.basewebparser import BaseWebParser

class WikipediaParser(BaseWebParser):
    """
    Estende BaseWebParser per adattarlo alla struttura DOM e testuale di Wikipedia.
    """
    
    # Pattern per individuare l'inizio delle sezioni di appendice.
    # Tutto il testo che si trova dopo queste intestazioni verrà scartato per la valutazione.
    _STOP_PATTERN = re.compile(
        r'^#+\s*(References?|Notes?|See also|External links?|Further reading|Bibliography|Citations?).*$',
        flags=re.IGNORECASE | re.MULTILINE
    )

    # Regole di pulizia Regex applicate iterativamente al Markdown generato.
    _CLEANING_RULES = [
        (re.compile(r'\[[^\]]*\]\s*\([^\)]*#cite_note[^\)]*\)', flags=re.IGNORECASE), ''), # Rimuove i link alle note a piè di pagina
        (re.compile(r'\[\s*\]\([^\)]+\)'), ''), # Rimuove i link testuali vuoti
        (re.compile(r'_?\[citation needed\]_?', flags=re.IGNORECASE), ''), # Rimuove i tag "[citation needed]"
        (re.compile(r'\[Italian language\]', flags=re.IGNORECASE), ''), # Rimuove indicazioni di lingua specifiche
        (re.compile(r'(?<!\!)\[\d+\]'), ''), # Rimuove i rimandi numerici (es. [1], [2]) senza toccare la sintassi delle immagini
        (re.compile(r'(?<!\!)\[\s*[a-z]\s*\]', flags=re.IGNORECASE), ''), # Rimuove i rimandi alfabetici (es. [a], [b])
        (re.compile(r'\(\s*\)'), ''), # Elimina le parentesi rimaste vuote a causa delle pulizie precedenti
        (re.compile(r'^!.*$', flags=re.MULTILINE), ''), # Rimuove residui di immagini in formato Markdown
        (re.compile(r'<sup[^>]*>.*?</sup>', flags=re.IGNORECASE | re.DOTALL), ''), # Rimuove il contenuto in apice (tipicamente riferimenti)
        (re.compile(r'\{\{\s*.*?\}\}', flags=re.DOTALL), ''), # Rimuove eventuali residui sintattici di template MediaWiki
        (re.compile(r'^\s*This article (is|needs|may).*?\.$', flags=re.MULTILINE | re.IGNORECASE), ''), # Rimuove avvisi redazionali a inizio pagina
        (re.compile(r'^\s*This page (is|was).*?Wikipedia\.', flags=re.MULTILINE | re.IGNORECASE), ''), # Rimuove i metadati redazionali
        (re.compile(r'Coordinates?:\s*.*$', flags=re.MULTILINE | re.IGNORECASE), ''), # Rimuove i blocchi di coordinate geografiche
        (re.compile(r'(?<!\!)\[([^\]]+)\]\([^\)]+\)'), r'\1'), # Converte i restanti link utili in testo semplice (rimuovendo l'URL)
        (re.compile(r'\n{3,}'), '\n\n'), # Normalizza l'impaginazione comprimendo i ritorni a capo eccessivi
        (re.compile(r'^\s*[-*+]\s*$', flags=re.MULTILINE), '') # Rimuove elementi di liste rimasti vuoti
    ]

    def __init__(self):
        super().__init__()
       
        # Selettori CSS (classi e ID) da escludere a monte durante il crawling.
        # Rimuove infobox, menu laterali, indici (TOC), miniature di immagini e note.
        excluded_selectors = [
            ".infobox", ".infobox_v2", ".mw-editsection", ".navbox", "#toc", 
            ".ambox", ".hatnote", ".thumb", ".thumbinner", ".gallery", 
            ".shortdescription", ".tright", ".tleft", ".mw-halign-right", 
            ".mw-halign-left", ".mw-halign-center", ".reference"
        ]

        # Configurazione mirata di Crawl4AI per Wikipedia
        self.run_config = CrawlerRunConfig(
            magic=True,
            cache_mode=CacheMode.BYPASS,
            exclude_external_links=True,
            css_selector="#mw-content-text", # Estrae solo il blocco principale contenente l'articolo
            excluded_tags=["nav", "footer", "header", "aside", "figure"], # Ignora tag strutturali irrilevanti
            excluded_selector=", ".join(excluded_selectors)
        )


    def extract_fallback_title(self, url: str) -> Optional[str]:
        """
        Recupera il titolo della pagina analizzando e decodificando l'URL in caso
        di fallimento del parser principale. Garantisce il suffisso standard ' - Wikipedia'.
        """
        if url and "/wiki/" in url:
            raw_title = url.split("/wiki/")[-1]
            title = unquote(raw_title).replace("_", " ")
            
            if " - Wikipedia" not in title:
                title = f"{title} - Wikipedia"
                
            return title
            
        return None
    

    def clean_markdown(self, text: str) -> str:
        """
        Fase di pulizia testuale. Tronca il documento per rimuovere la bibliografia
        e applica le espressioni regolari per pulire il rumore di fondo all'interno del testo.
        """
        if not text:
            return ""

        # Tronca il testo non appena trova l'intestazione di una sezione "Stop"
        match = self._STOP_PATTERN.search(text)
        if match:
            text = text[:match.start()]

        # Applica in sequenza tutte le regex definite in _CLEANING_RULES
        for pattern, replacement in self._CLEANING_RULES:
            text = pattern.sub(replacement, text)
       
        return text.strip()
    
    def parse_offline_html(self, html_content: str) -> str:
        """
        Metodo per l'elaborazione offline (necessario per generare i risultati sul Gold Standard).
        Usa BeautifulSoup per simulare localmente il pre-processing che Crawl4AI 
        esegue tramite configurazioni quando naviga online.
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. Rimuove i tag strutturali irrilevanti
        for tag in soup.find_all(['nav', 'footer', 'header', 'aside', 'figure']): 
            tag.decompose()
            
        # 2. Replica l'esclusione delle classi e degli ID CSS che Crawl4AI ignorerebbe online
        for junk in soup.select(".infobox, .infobox_v2, .mw-editsection, .navbox, #toc, .ambox, .hatnote, .thumb, .thumbinner, .gallery, .shortdescription, .tright, .tleft, .mw-halign-right, .mw-halign-left, .mw-halign-center, .reference"): 
            junk.decompose()
            
        # 3. Preserva semanticamente le intestazioni principali convertendole nei tag Markdown corrispondenti
        for h2 in soup.find_all('h2'): h2.insert(0, "## ")
        for h3 in soup.find_all('h3'): h3.insert(0, "### ")
        
        # Punta direttamente al contenitore del contenuto testuale (se presente), estrae il testo e lo pulisce
        content = soup.select_one("#mw-content-text") or soup
        return self.clean_markdown(content.get_text(separator="\n"))