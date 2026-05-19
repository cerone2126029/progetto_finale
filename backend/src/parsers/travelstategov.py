import re
from typing import List, Optional


from bs4 import BeautifulSoup, Tag
from crawl4ai import CrawlerRunConfig, CacheMode
from urllib.parse import unquote


from parsers.basewebparser import BaseWebParser




# =============================================================================
# Cascata di selettori (ordine di priorità: più specifico prima)
# =============================================================================
# Ciascuno individua il contenitore del CONTENUTO INFORMATIVO della pagina.
# La cascata si ferma al primo selettore che produce un nodo non vuoto.
CONTENT_SELECTORS_CASCADE: List[str] = [
    ".tsg-rwd-main-copy-body-frame",        # Template A
    "#tsg_right_section_main_container",    # Template C (destra = contenuto)
    "#tsg_main_content_container",          # Template B (più ampio: include
                                            # titolo + intro fuori da #tsg-grid-bottom,
                                            # essenziali per le pagine country)
    "#tsg-grid-bottom",                     # Fallback se main_content mancasse
    ".post-content",                        # back-compat / pagine vecchie
]


# Selettori di "chrome" UI che vanno rimossi PRIMA dell'estrazione di testo.
# IMPORTANTE: NON includere #tsg_middle_section_main_container perché in alcuni
# template (C) contiene come figlio anche #tsg_right_section_main_container che
# è il vero contenuto. La cascata di selettori si occuperà di scegliere il nodo
# giusto; qui dobbiamo solo rimuovere chrome/navigazione globale.
NOISE_SELECTORS: List[str] = [
    "nav",
    "footer",
    "header",
    ".megamenu",
    ".megamenu-main__container",
    "#tsg_header_container",
    ".tsg-rwd-nav-main-site-menu-frame",
    ".usa-footer",
    ".usa-banner",
    ".usa-skipnav",
    ".tsg-submit_feedback",                  # form feedback in fondo alle pagine nuove
    ".simplebutton",
    ".featurebox",
    ".SlideShow",
    ".fusion-builder-column-3",
    ".imageframe",
    ".fusion-button",
    ".wp-caption",
    ".tsg-rwd-accordion",
    "[role='banner']",
    "[role='dialog']",
    "[aria-label*='cookie' i]",
    "script", "style", "noscript", "form", "iframe",
]




class TravelStateGov(BaseWebParser):
    """
    Parser robusto a 3 template diversi del sito travel.state.gov.
    Sfrutta una cascata di selettori CSS per individuare il contenitore del
    contenuto informativo, indipendentemente da quale template usi la pagina.
    """


    # Regole di pulizia post-estrazione (applicate al testo, sia online che offline)
    _CLEANING_RULES = [
        (re.compile(r'\[([^\]]+)\]\([^\)]+\)'), r'\1'),                        # link [testo](url) -> testo
        (re.compile(r'!\[[^\]]*\]\([^\)]+\)'), ''),                            # immagini ![alt](url)
        (re.compile(r'^.*Last Updated:.*$', flags=re.IGNORECASE | re.MULTILINE), ''),
        (re.compile(r'\[\]\(javascript:void\\?\(0\\?\);?[^\)]*\)'), ''),       # bottoni js morti
        (re.compile(r'^\s*Skip to (?:main )?content.*$', re.IGNORECASE | re.MULTILINE), ''),
        (re.compile(r'^\s*Was this page helpful\?.*$', re.IGNORECASE | re.MULTILINE), ''),
        (re.compile(r'\n{3,}'), '\n\n'),                                       # normalizza newline
    ]


    def __init__(self):
        super().__init__()


        # css_selector è la UNIONE dei selettori della cascata:
        # Crawl4AI restituisce solo il nodo che matcha. Per template B sia
        # #tsg-grid-bottom che #tsg_main_content_container matchano: prendiamo
        # il PRIMO con un descendant combinator non specificato, Crawl4AI di
        # solito li concatena entrambi. Per gestirlo, in extract_and_clean_text
        # facciamo comunque un ulteriore passaggio DOM-based.
        css_selector_union = ", ".join(CONTENT_SELECTORS_CASCADE)


        self.run_config = CrawlerRunConfig(
            magic=True,
            cache_mode=CacheMode.BYPASS,
            exclude_external_links=True,
            exclude_internal_links=True,
            exclude_all_images=True,
            exclude_social_media_links=True,
            css_selector=css_selector_union,
            excluded_tags=["nav", "footer", "header", "img", "form", "iframe", "script", "style"],
            excluded_selector=", ".join(NOISE_SELECTORS),
        )


    # ------------------------------------------------------------------
    # FALLBACK TITLE
    # ------------------------------------------------------------------
    def extract_fallback_title(self, url: str) -> Optional[str]:
        """Ricava un titolo dall'ultimo segmento dell'URL."""
        if not url:
            return None
        clean_url = url.rstrip("/")
        raw = clean_url.split("/")[-1]
        raw = unquote(raw).replace(".html", "").replace(".htm", "").replace("-", " ")
        return raw.title() or None


    # ------------------------------------------------------------------
    # ESTRAZIONE LIVE (override per fare cascata DOM anche sul risultato Crawl4AI)
    # ------------------------------------------------------------------
    def extract_and_clean_text(self, result) -> str:
        """
        Pipeline:
          1. Se Crawl4AI ha già prodotto un markdown abbastanza sostanzioso,
             lo puliamo e lo restituiamo (caso template A — il selettore singolo
             matcha solo il contenitore corretto).
          2. Se il markdown è vuoto/scarno, ricadiamo sull'HTML usando la
             cascata di selettori DOM (caso template B/C, in cui css_selector
             ha potenzialmente concatenato più container).
        """
        raw_markdown = ""
        if hasattr(result, 'markdown') and result.markdown:
            raw_markdown = str(result.markdown).strip()


        if len(raw_markdown) >= 200:
            cleaned = self.clean_markdown(raw_markdown)
            if cleaned and len(cleaned) >= 100:
                return cleaned


        # Fallback DOM-based su HTML grezzo (più affidabile per template B/C)
        html = getattr(result, "html", "") or ""
        return self._extract_from_html(html)


    # ------------------------------------------------------------------
    # OFFLINE PARSING (per /full_gs_eval e local=true)
    # ------------------------------------------------------------------
    def parse_offline_html(self, html_content: str) -> str:
        return self._extract_from_html(html_content)


    # ------------------------------------------------------------------
    # CORE: estrazione dal DOM con cascata
    # ------------------------------------------------------------------
    def _extract_from_html(self, html: str) -> str:
        if not html:
            return ""


        soup = BeautifulSoup(html, "html.parser")


        # 1) Rimuovi a monte tutti i selettori di rumore (nav, header, footer,
        #    megamenu, banner, ecc.) — qualunque sia il container scelto dopo.
        for selector in NOISE_SELECTORS:
            for tag in soup.select(selector):
                tag.decompose()


        # 2) Cascata: prendi il PRIMO selettore che produce un nodo non banale
        content_node: Optional[Tag] = None
        for selector in CONTENT_SELECTORS_CASCADE:
            candidate = soup.select_one(selector)
            if candidate is None:
                continue
            # Se il candidato è veramente vuoto, passa al prossimo
            if not candidate.get_text(strip=True):
                continue
            content_node = candidate
            break


        # 3) Fallback ultimo: <main> o body
        if content_node is None:
            content_node = soup.find("main") or soup.body or soup


        # 4) Estrazione testuale + pulizia
        raw_text = content_node.get_text(separator="\n")
        return self.clean_markdown(raw_text)


    # ------------------------------------------------------------------
    # CLEAN MARKDOWN / TEXT
    # ------------------------------------------------------------------
    def clean_markdown(self, text: str) -> str:
        if not text:
            return ""
        for pattern, replacement in self._CLEANING_RULES:
            text = pattern.sub(replacement, text)


        # Pulizia line-based: rimuove righe duplicate consecutive e righe
        # composte solo da simboli o estremamente corte (residui di icone).
        lines: List[str] = []
        prev: Optional[str] = None
        for raw in text.splitlines():
            ln = re.sub(r"[ \t]+", " ", raw).strip()
            if not ln:
                if lines and lines[-1] != "":
                    lines.append("")
                continue
            if ln == prev:
                continue
            # Riga di soli simboli/punteggiatura (residuo di icone o separatori)
            if len(ln) <= 2 and not ln.isalnum():
                continue
            prev = ln
            lines.append(ln)


        # Trim trailing blank lines
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines).strip()


