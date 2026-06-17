import re
from typing import List, Optional
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup
from crawl4ai import CrawlerRunConfig, CacheMode
from parsers.basewebparser import BaseWebParser

class TravelStateGov(BaseWebParser):

    def __init__(self):
        """
        Inizializza il parser per travel.state.gov configurando le opzioni di crawling.
        Abilita la modalità 'magic' di Crawl4AI per gestire render complessi, bypassa la cache 
        e ignora preventivamente elementi non semantici come link esterni, interni, 
        immagini e social media per alleggerire il DOM in fase di analisi.
        """
        super().__init__()
        self.run_config = CrawlerRunConfig(
            magic=True,
            cache_mode=CacheMode.BYPASS,
            exclude_external_links=True,
            exclude_internal_links=True,
            exclude_all_images=True,
            exclude_social_media_links=True
        )

    def extract_fallback_title(self, url: str) -> Optional[str]:
        """
        Estrae dinamicamente il titolo dell'avviso o della pagina informativa 
        dall'URL fornito, evitando valori fissi (hardcoded) ed eliminando 
        estensioni o caratteri di formattazione del percorso.
        """
        if not url:
            return "Travel Advisory | Travel.State.gov"
        try:
            # Analizza l'URL (es. /content/.../italy-travel-advisory.html)
            path = urlparse(unquote(url)).path
            if not path or path == '/':
                return "Travel Advisory | Travel.State.gov"
                
            # Prende l'ultima parte dell'URL
            slug = path.split('/')[-1]
            if not slug and len(path.split('/')) > 1:
                slug = path.split('/')[-2]
                
            # Rimuove .html e sostituisce i trattini con gli spazi
            slug = re.sub(r'\.html?$', '', slug, flags=re.IGNORECASE)
            clean_name = slug.replace('-', ' ').replace('_', ' ').strip()
            
            # Capitalizza le prime lettere (es. "italy travel advisory" -> "Italy Travel Advisory")
            title_case = clean_name.title()
            
            if not title_case:
                return "Travel Advisory | Travel.State.gov"
                
            if "Travel Advisory" in title_case:
                return f"{title_case} | Travel.State.gov"
            return f"{title_case} - Travel Information | Travel.State.gov"
            
        except Exception:
            return "Travel Advisory | Travel.State.gov"

    def clean_markdown(self, text: str) -> str:
        """
        Esegue una pulizia aggressiva del testo estratto tramite espressioni regolari.
        Rimuove metadati orfani (es. "Last Updated"), stringhe di accessibilità per
        screen reader (es. "Skip to main content"), form di feedback e simboli 
        isolati tipici delle interfacce ad accordion (+, -, V, >, <).
        """
        if not text: return ""
        
        text = re.compile(r'^.*Last Updated:.*$', flags=re.IGNORECASE | re.MULTILINE).sub('', text)
        text = re.compile(r'^\s*Skip to (?:main )?content.*$', re.IGNORECASE | re.MULTILINE).sub('', text)
        text = re.compile(r'^\s*Was this page helpful\?.*$', re.IGNORECASE | re.MULTILINE).sub('', text)
        
        lines = []
        prev = None
        for raw in text.split('\n'):
            ln = re.sub(r"[ \t]+", " ", raw).strip()
            if not ln:
                if lines and lines[-1] != "":
                    lines.append("")
                continue
            if ln == prev: continue
            
            if ln in ["+", "-", "V", ">", "<", "•"]: continue
            
            prev = ln
            lines.append(ln)

        res = "\n".join(lines).strip()
        return re.sub(r'\n{3,}', '\n\n', res)

    def _extract_semantic_blocks(self, html: str) -> str:
        """
        Motore centrale di estrazione semantica per il dominio travel.state.gov.
        Pulisce preventivamente il DOM dal boilerplate (navigazione, footer, 
        menu a tendina delle nazioni) e tenta l'estrazione in due fasi:
        1. Piano A: Ricerca selettori di componenti specifici AEM (es. alert, requisiti, ambasciate).
        2. Piano B: Fallback sui macro-contenitori generici del sito se il Piano A non produce risultati.
        """
        if not html: return ""
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.select('nav, footer, header, script, style, noscript, svg, button, form, iframe, .usa-banner, .usa-footer, .megamenu, select'):
            tag.decompose()

        component_selectors = [
            '.hero-standard',
            '.cmp-traveladvisory',
            '.destination-about',
            '.destination-requirements',
            '.destination-tips',
            '.embassycontactcallout',
            '.consulatedisplay'
        ]

        extracted_pieces = []
        for selector in component_selectors:
            for container in soup.select(selector):
                text = container.get_text(separator="\n", strip=True)
                if text:
                    extracted_pieces.append(text)

        if not extracted_pieces:
            fallback_selectors = [
                ".tsg-rwd-main-copy-body-frame",
                "#tsg_main_content_container",
                "#tsg-grid-bottom",
                "main"
            ]
            for selector in fallback_selectors:
                container = soup.select_one(selector)
                if container and container.get_text(strip=True):
                    text = container.get_text(separator="\n", strip=True)
                    extracted_pieces.append(text)
                    break 

            if not extracted_pieces and soup.body:
                extracted_pieces.append(soup.body.get_text(separator="\n", strip=True))

        raw_text = "\n\n".join(extracted_pieces)
        return self.clean_markdown(raw_text)

    def extract_data(self, result):
        """
        Entry point principale del parser per i dati estratti dinamicamente dal crawler (Live).
        Prepara e restituisce il dizionario strutturato con i metadati e il testo processato.
        """
        html = getattr(result, "html", "") or ""
        return {
            "url": getattr(result, "url", ""),
            "domain": "travel.state.gov",
            "title": self.extract_fallback_title(getattr(result, "url", "")),
            "html_text": html,
            "parsed_text": self._extract_semantic_blocks(html)
        }

    def parse_offline_html(self, html_content: str) -> str:
        """
        Entry point secondario del parser per i dati provenienti dal Database (Modalità Local).
        Invia direttamente l'HTML archiviato all'orchestratore semantico bypassando la rete.
        """
        return self._extract_semantic_blocks(html_content)

    def extract_and_clean_text(self, result) -> str:
        """
        Metodo wrapper di utilità per richiamare direttamente l'estrazione semantica 
        passando l'oggetto risultato del crawler.
        """
        return self._extract_semantic_blocks(getattr(result, "html", "") or "")