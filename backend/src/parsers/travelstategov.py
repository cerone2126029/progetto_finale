"""
Parser specifico per il dominio travel.state.gov.
Sfrutta le potenzialità di pre-processing di Crawl4AI (tramite CrawlerRunConfig)
per escludere a monte elementi UI, navigation-bar e componenti interattivi governativi,
riducendo al minimo la necessità di pulizia tramite espressioni regolari.
"""

import re
from crawl4ai import CrawlerRunConfig, CacheMode
from parsers.basewebparser import BaseWebParser
from urllib.parse import unquote
from typing import Optional

class TravelStateGov(BaseWebParser):
    """
    Estende BaseWebParser definendo selettori CSS di esclusione e 
    regex mirate per estrarre avvisi di viaggio puliti e contenuti informativi.
    """

    # Regole di pulizia post-crawling applicate al Markdown o al testo estratto
    _CLEANING_RULES = [
        (re.compile(r'\[([^\]]+)\]\([^\)]+\)'), r'\1'), # Sostituisce i link markdown preservando solo il testo cliccabile
        (re.compile(r'^.*Last Updated:.*$', flags=re.IGNORECASE | re.MULTILINE), ''), # Rimuove i metadati redazionali di aggiornamento pagina
        (re.compile(r'\[\]\(javascript:void\\?\(0\\?\);?[^\)]*\)'), '') # Rimuove bottoni o link JavaScript morti rimasti nel testo
    ]

    def __init__(self):
        super().__init__()
       
        # Lista di classi CSS che identificano elementi non informativi del sito:
        # bottoni, caroselli, sidebar laterali, didascalie e menu a tendina.
        excluded_selectors = [
            ".simplebutton",
            ".featurebox",
            ".SlideShow",
            ".fusion-builder-column-3",
            ".imageframe",
            ".fusion-button",
            ".wp-caption",
            ".tsg-rwd-accordion"
        ]

        # Configurazione mirata di Crawl4AI per il dominio governativo.
        # Esclude immagini, link social e punta direttamente al corpo centrale del testo.
        self.run_config = CrawlerRunConfig(
            magic=True,
            cache_mode=CacheMode.BYPASS,
            exclude_external_links=True,
            exclude_internal_links=True,
            exclude_all_images=True,
            exclude_social_media_links=True,
            css_selector=".tsg-rwd-main-copy-body-frame, .post-content", # Punta al contenitore principale del testo
            excluded_tags=["nav", "footer", "header", "img"], # Rimuove i tag strutturali di base
            excluded_selector=", ".join(excluded_selectors) if excluded_selectors else None # Applica i selettori CSS di esclusione
        )
    
    def extract_fallback_title(self, url: str) -> Optional[str]:
        """
        Metodo ereditato e sovrascritto. 
        Recupera il titolo dall'URL gestendo sia i link con .html sia quelli senza,
        formattandolo in un titolo leggibile.
        """
        if url:

            # 1. Rimuove l'eventuale slash finale (es: "travel-advisories/")
            clean_url = url.rstrip("/")
            
            # 2. Isola l'ultimo segmento dell'URL
            raw_title = clean_url.split("/")[-1]
            
            # 3. Rimuove le estensioni, decodifica caratteri speciali (%20) e sostituisce i trattini con spazi
            raw_title = unquote(raw_title).replace(".html", "").replace(".htm", "").replace("-", " ")

            # 4. Rende maiuscola l'iniziale di ogni parola
            return raw_title.title()
            
        return None

    def parse_offline_html(self, html_content: str) -> str:
        """
        Metodo per l'elaborazione offline (Gold Standard) delegato al parser.
        Utilizza BeautifulSoup per replicare fedelmente le esclusioni CSS e i filtri
        che Crawl4AI applicherebbe online tramite la run_config.
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Elimina i tag strutturali di navigazione e le immagini
        for tag in soup.find_all(['nav', 'footer', 'header', 'img']):
            tag.decompose()

        # Replica l'eliminazione dei selettori UI (bottoni, slideshow, ecc.) definiti nell'__init__
        excluded_selectors = [
            ".simplebutton",
            ".featurebox",
            ".SlideShow",
            ".fusion-builder-column-3",
            ".imageframe",
            ".fusion-button",
            ".wp-caption",
            ".tsg-rwd-accordion"
        ]
        for selector in excluded_selectors:
            for junk in soup.select(selector):
                junk.decompose()
        
        # Punta al contenitore del corpo testo (se esiste, altrimenti analizza l'intero documento rimasto)
        content = soup.select_one(".tsg-rwd-main-copy-body-frame, .post-content") or soup
        raw_text = content.get_text(separator="\n")
        
        # Passa il testo grezzo estratto alle regole di pulizia testuale
        return self.clean_markdown(raw_text)
    

    def clean_markdown(self, text: str) -> str:
        """
        Fase di pulizia testuale finale.
        Applica le espressioni regolari per pulire i residui di link e metadati dal testo.
        """
        if not text:
            return ""
        
        for pattern, replacement in self._CLEANING_RULES:
            text = pattern.sub(replacement, text)
       
        return text.strip()