import re
from typing import List, Optional
from urllib.parse import unquote
from bs4 import BeautifulSoup
from crawl4ai import CrawlerRunConfig, CacheMode
from parsers.basewebparser import BaseWebParser

class TravelStateGov(BaseWebParser):
    
    def __init__(self):
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
        return "Travel Advisory | Travel.State.gov"

    def clean_markdown(self, text: str) -> str:
        if not text: return ""
        
        # Pulizia metadati orfani e intestazioni
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
            
            # Filtro per i simboli dell'interfaccia degli accordion
            if ln in ["+", "-", "V", ">", "<", "•"]: continue
            
            prev = ln
            lines.append(ln)

        res = "\n".join(lines).strip()
        return re.sub(r'\n{3,}', '\n\n', res)

    def _extract_semantic_blocks(self, html: str) -> str:
        if not html: return ""
        soup = BeautifulSoup(html, "html.parser")

        # Rimuoviamo il rumore di navigazione (incluso select per la lista nazioni)
        for tag in soup.select('nav, footer, header, script, style, noscript, svg, button, form, iframe, .usa-banner, .usa-footer, .megamenu, select'):
            tag.decompose()

        # PIANO A: I mattoncini AEM per i Country Information Pages
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

        # PIANO B: Il Fallback per le pagine generiche (Visti, Passaporti, Info)
        # Se l'array è vuoto, significa che nessuno dei selettori nazione ha matchato.
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
                    break # Appena trova un macro-contenitore valido, si ferma.

            # Fallback estremo se persino il main fallisce
            if not extracted_pieces and soup.body:
                extracted_pieces.append(soup.body.get_text(separator="\n", strip=True))

        raw_text = "\n\n".join(extracted_pieces)
        return self.clean_markdown(raw_text)

    # =================================================================
    # UNIFICAZIONE: Entrambi i test (Live e Offline) ora usano il motore blindato
    # =================================================================
    def extract_data(self, result):
        html = getattr(result, "html", "") or ""
        return {
            "url": getattr(result, "url", ""),
            "domain": "travel.state.gov",
            "title": self.extract_fallback_title(getattr(result, "url", "")),
            "html_text": html,
            "parsed_text": self._extract_semantic_blocks(html)
        }

    def parse_offline_html(self, html_content: str) -> str:
        return self._extract_semantic_blocks(html_content)

    def extract_and_clean_text(self, result) -> str:
        return self._extract_semantic_blocks(getattr(result, "html", "") or "")