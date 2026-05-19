import re
import json
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse


from bs4 import BeautifulSoup, Tag
from crawl4ai import CrawlerRunConfig, CacheMode


from parsers.basewebparser import BaseWebParser




# =============================================================================
# Pattern di rumore (liste estensibili)
# =============================================================================


# Righe il cui contenuto coincide esattamente (case-insensitive, dopo strip)
# con uno di questi termini vengono eliminate dal testo finale.
_NOISE_EXACT: Set[str] = {
    # Lingue elencate nel footer di Spotify
    "italiano", "english", "english (uk)", "english (us)", "español",
    "español de méxico", "español de latinoamérica", "français", "français (canada)",
    "deutsch", "português", "português brasileiro", "polski", "nederlands",
    "türkçe", "русский", "العربية", "中文", "日本語", "한국어",
    "tiếng việt", "bahasa indonesia", "magyar", "čeština", "română",
    "ελληνικά", "svenska", "norsk", "dansk", "suomi",
    # Categorie/sezioni footer Spotify
    "aziende", "company", "about", "jobs", "for the record",
    "comunità", "communities", "per artisti", "for artists",
    "sviluppatori", "developers", "pubblicità", "advertising",
    "investitori", "investors", "fornitori", "vendors",
    "link utili", "useful links",
    "supporto", "support", "centro assistenza", "help center",
    "info su pubblicità libera", "free mobile app", "app mobile gratuita",
    # Sezioni legal/privacy
    "informazioni legali", "legal", "centro sulla sicurezza e la privacy",
    "centro privacy", "privacy", "informativa sulla privacy",
    "impostazioni dei cookie", "cookie", "cookies", "cookie settings",
    "informazioni sulla pubblicità", "informativa sui cookie",
    "accessibilità", "accessibility",
    # Auth e CTA
    "iscriviti", "iscriviti gratis", "iscriviti gratuitamente", "registrati",
    "accedi", "log in", "sign up", "sign in",
    "scarica", "scarica l'app", "apri l'app", "apri in app",
    "apri spotify", "use the web player", "usa il web player",
    "scarica l'app gratuita", "ascolta in app",
    # Brand / generici
    "spotify", "spotify free", "spotify premium", "premium",
    "anteprima", "preview", "play preview",
    # Bottoni player / azioni della pagina (sono parole isolate, mai contenuto del gold)
    "riproduci tutto", "play all",
    "riproduzione casuale", "shuffle", "shuffle play",
    "metti in pausa", "pause",
    "salva", "save",
    "segui", "follow", "seguito", "following", "non seguire più", "unfollow",
    "aggiungi alla coda", "add to queue",
    "aggiungi alla libreria", "add to your library",
    "rimuovi dalla libreria", "remove from your library",
    "condividi", "share", "copia link", "copy link",
    "mostra crediti", "show credits",
    "mostra di più", "mostra altro", "show more", "see more",
    "mostra meno", "show less", "see less",
    "carica altro", "load more",
    "più opzioni", "more options",
    "vai al brano", "go to song",
    "vai all'album", "go to album",
    "vai all'artista", "go to artist",
    "vai al podcast", "go to podcast",
    # Colonne tablist che NON appaiono nel gold di album/show
    # (NOTA: NON includere "titolo"/"title"/"album"/"durata" perché compaiono
    #  nel gold come header di sezione o come page type label.)
    "data di aggiunta", "date added",
    "riproduzioni", "plays", "streams",
    # Bottoni episodio/podcast (etichette button visibili)
    "play episode", "riproduci episodio",
    # Altri elementi UI di navigazione globale (sidebar/topbar)
    "esplora", "explore", "cerca", "search",
    "home", "la tua libreria", "your library",
    "crea playlist", "create playlist",
    "playlist creata da te", "made for you",
    "novità", "new releases",
    "tendenze", "trending",
    "sponsorizzato", "sponsored",
}


# Pattern (regex) di riga: la riga viene scartata se matcha INTERAMENTE.
# NB: aria-label, alt e title non finiscono in get_text(), quindi i pattern
# qui sotto coprono solo casi in cui Spotify rende il testo come visibile.
_NOISE_PATTERNS: List[re.Pattern] = [
    re.compile(r'^\s*©\s*\d{4}.*$'),                              # "© 2024 Spotify AB"
    re.compile(r'^\s*\d{4}\s+Spotify(\s+AB)?\s*$', re.IGNORECASE),
    re.compile(r'^.{0,40}\bcookie\b.{0,80}$', re.IGNORECASE),     # qualunque riga corta che parla di cookie
    re.compile(r'^.{0,60}\b(privacy|legal)\b.{0,60}$', re.IGNORECASE),
    re.compile(r'^.{0,40}(scarica|download).*app.*$', re.IGNORECASE),
    re.compile(r'^.{0,40}(apri|open).*app.*$', re.IGNORECASE),
    re.compile(r'^(iscriviti|accedi|log in|sign up)\b.*$', re.IGNORECASE),
    re.compile(r'^.{0,50}(facebook|instagram|twitter|x\.com|tiktok|youtube)\b.*$', re.IGNORECASE),
    re.compile(r'^.{0,30}salta\s+al\s+contenuto.*$', re.IGNORECASE),
    re.compile(r'^skip\s+to\s+content.*$', re.IGNORECASE),
]


# Marker che indicano "da qui in giù è footer/legal/cookie/consigliati": tronchiamo lì.
# Match come PREFISSO della riga (case-insensitive). Tronchiamo tutto ciò che segue.
# IMPORTANTE: non includere "Informazioni" da solo, perché lo show gold la usa
# come header della sezione "About this podcast".
_FOOTER_CUTOFF: List[re.Pattern] = [
    # Footer Spotify
    re.compile(r'^\s*aziende\s*$', re.IGNORECASE),
    re.compile(r'^\s*company\s*$', re.IGNORECASE),
    re.compile(r'^\s*comunità\s*$', re.IGNORECASE),
    re.compile(r'^\s*communities\s*$', re.IGNORECASE),
    re.compile(r'^\s*link utili\s*$', re.IGNORECASE),
    re.compile(r'^\s*useful links\s*$', re.IGNORECASE),
    re.compile(r'^\s*informazioni legali\s*$', re.IGNORECASE),
    re.compile(r'^\s*legal\s*$', re.IGNORECASE),
    re.compile(r'^\s*©\s*\d{4}.*$'),
    # Sezioni "consigliati / più di / featured on" -- queste sono il vero killer
    # della precision. Spotify le mette SOTTO la tracklist o gli episodi.
    re.compile(r'^\s*più\s+di\s+.+', re.IGNORECASE),               # "Più di J-AX"
    re.compile(r'^\s*più\s+album\s+di\s+.+', re.IGNORECASE),       # "Più album di Fedez"
    re.compile(r'^\s*più\s+podcast\s+di\s+.+', re.IGNORECASE),     # "Più podcast di ..."
    re.compile(r'^\s*più\s+di\s+(?:questo|questi)\s+(?:artista|artisti|album|podcast)?\s*$', re.IGNORECASE),
    re.compile(r'^\s*riproduzione\s+consigliata\s*$', re.IGNORECASE),
    re.compile(r'^\s*hanno\s+apprezzato\s+anche\s*$', re.IGNORECASE),
    re.compile(r'^\s*altre\s+playlist\s*$', re.IGNORECASE),
    re.compile(r'^\s*episodi\s+simili\s*$', re.IGNORECASE),
    re.compile(r'^\s*ti\s+potrebbe\s+piacere\s*$', re.IGNORECASE),
    re.compile(r'^\s*discografia\s*$', re.IGNORECASE),
    # English equivalents (some accounts default to EN)
    re.compile(r'^\s*more\s+by\s+.+', re.IGNORECASE),
    re.compile(r'^\s*more\s+like\s+this\s*$', re.IGNORECASE),
    re.compile(r'^\s*you\s+might\s+also\s+like\s*$', re.IGNORECASE),
    re.compile(r'^\s*fans\s+(?:also\s+)?like\s*$', re.IGNORECASE),
    re.compile(r'^\s*also\s+by\s+.+', re.IGNORECASE),
    re.compile(r'^\s*featured\s+on\s*$', re.IGNORECASE),
    re.compile(r'^\s*discography\s*$', re.IGNORECASE),
    re.compile(r'^\s*similar\s+(?:shows|podcasts|playlists)?\s*$', re.IGNORECASE),
    re.compile(r'^\s*recommended\s+for\s+you\s*$', re.IGNORECASE),
]




# Selettori CSS da rimuovere prima dell'estrazione del testo.
# Coprono cookie banner, login wall, share box, "Apri in app" e simili,
# più (e questo è il bonus chiave) le sezioni di RECOMMENDED / FEATURED ON
# che Spotify renderizza sotto il contenuto principale.
_EXCLUDED_SELECTORS: List[str] = [
    "footer",
    "nav",
    "header",
    "aside",
    # Cookie banner Spotify (OneTrust)
    "#onetrust-consent-sdk",
    "#onetrust-banner-sdk",
    "[data-testid='cookie-banner']",
    # Auth / download / topbar
    "[data-testid='login-button']",
    "[data-testid='signup-button']",
    "[data-testid='download-link']",
    "[data-testid='spotify-logo']",
    "[data-testid='topbar']",
    "[data-testid='top-bar']",
    "[data-testid='top-bar-info']",
    "[data-testid='top-bar-button']",
    "[data-testid='page-footer']",
    "[data-testid='footer']",
    "[data-testid='language-selector']",
    "[data-testid='upgrade-button']",
    "[data-testid='install-app-button']",
    # Sezioni di RACCOMANDAZIONI sotto il contenuto principale
    # (i selettori veri li nomina Spotify con prefissi tipo "discography",
    # "fans-also-like", "related", "featured-on", "more-by", ecc.)
    "[data-testid='discography']",
    "[data-testid*='more-by']",
    "[data-testid*='fans-also-like']",
    "[data-testid*='featured-on']",
    "[data-testid*='related']",
    "[data-testid*='recommend']",
    "[data-testid*='similar']",
    "[data-testid*='discograph']",
    "[aria-label*='cookie' i]",
    "[aria-label*='lingua' i]",
    "[aria-label*='language' i]",
    "[role='dialog']",
    "[role='banner']",
]




class SpotifyParser(BaseWebParser):
    """Parser per album, podcast, episodi, artisti, playlist di open.spotify.com."""


    def __init__(self):
        super().__init__()


        # Configurazione Crawl4AI:
        #  * Attendiamo network-idle e diamo 3s di delay per la idratazione React
        #  * css_selector="main" limita a ciò che React renderizza come contenuto
        #  * exclude_* riduce link esterni/social a monte
        #  * excluded_tags toglie tag strutturali non semantici
        #  * excluded_selector è la lista mirata di componenti di "chrome" UI
        self.run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until="networkidle",
            delay_before_return_html=3,
            page_timeout=30000,
            exclude_external_links=True,
            exclude_social_media_links=True,
            exclude_all_images=True,
            css_selector="main",
            excluded_tags=["nav", "footer", "header", "aside",
                           "script", "style", "noscript", "form"],
            excluded_selector=", ".join(_EXCLUDED_SELECTORS),
        )


    # ------------------------------------------------------------------
    # FALLBACK TITLE
    # ------------------------------------------------------------------
    def extract_fallback_title(self, url: str) -> Optional[str]:
        """Costruisce un titolo leggibile dalla path: '/album/<id>' -> 'Album <id> | Spotify'."""
        if not url:
            return None
        parsed = urlparse(url)
        # Rimuove segmenti tipo "intl-it" usati per la localizzazione
        parts = [p for p in parsed.path.split("/")
                 if p and not p.startswith("intl-")]
        if not parts:
            return None
        if len(parts) >= 2:
            return f"{parts[0].capitalize()} {parts[1]} | Spotify"
        return f"{parts[0]} | Spotify"


    # ------------------------------------------------------------------
    # ESTRAZIONE LIVE (override del comportamento base)
    # ------------------------------------------------------------------
    def extract_and_clean_text(self, result) -> str:
        """
        Strategia:
          * Se l'HTML renderizzato è disponibile, lavoriamo direttamente sul DOM
            del <main> (più affidabile del markdown nativo di Crawl4AI, che ogni
            tanto include link/menu esterni al main).
          * Altrimenti, se Crawl4AI ha prodotto un markdown sostanzioso, lo
            puliamo con clean_markdown.
          * Ultima spiaggia: estrazione dai metadati Open Graph / Twitter / JSON-LD.
        """
        html = getattr(result, "html", "") or ""
        if html:
            text = self._extract_from_main_dom(html)
            if text and len(text) > 200:
                return text


        raw_markdown = ""
        if hasattr(result, "markdown") and result.markdown:
            raw_markdown = str(result.markdown).strip()
        if len(raw_markdown) > 500:
            return self.clean_markdown(raw_markdown)


        return self._extract_from_metadata(html)


    # ------------------------------------------------------------------
    # ESTRAZIONE OFFLINE (per /full_gs_eval e local=true)
    # ------------------------------------------------------------------
    def parse_offline_html(self, html_content: str) -> str:
        """
        Parsing offline: usiamo la stessa pipeline DOM-based dell'online.
        Se l'HTML è solo lo shell SPA senza contenuto, ricadiamo sui metadati.
        """
        if not html_content:
            return ""
        text = self._extract_from_main_dom(html_content)
        if text and len(text) > 200:
            return text
        return self._extract_from_metadata(html_content)


    # ------------------------------------------------------------------
    # CORE: estrazione dal <main> con pulizia chirurgica
    # ------------------------------------------------------------------
    def _extract_from_main_dom(self, html: str) -> str:
        """
        Pipeline DOM:
          1. Parse HTML
          2. Rimuove tutti i selettori di rumore (cookie banner, footer, ecc.)
             ANCHE se sono nel main (es. cookie banner inniettato come overlay)
          3. Restringe al <main> se presente, altrimenti al body
          4. Estrae il testo riga per riga
          5. Tronca alla prima ancora di footer residua
          6. Filtra le righe rumorose
        """
        soup = BeautifulSoup(html, "html.parser")


        # 1) Eliminiamo a monte i selettori di rumore
        for selector in _EXCLUDED_SELECTORS:
            for tag in soup.select(selector):
                tag.decompose()


        # 2) Eliminiamo tag globalmente non semantici
        for tag in soup(["script", "style", "noscript", "form", "svg", "iframe"]):
            tag.decompose()


        # 3) Restringiamo a <main>, altrimenti al body
        root: Optional[Tag] = soup.find("main")
        if root is None:
            root = soup.body or soup


        # 4) Estrazione testuale: ogni elemento diventa una riga
        raw_text = root.get_text(separator="\n")


        # 5+6) Pulizia line-based
        return self._clean_lines(raw_text)


    # ------------------------------------------------------------------
    # PULIZIA TESTUALE (line-based filter)
    # ------------------------------------------------------------------
    def _clean_lines(self, text: str) -> str:
        """
        Pulizia riga per riga:
          * normalizza ogni riga (collapse di spazi multipli)
          * scarta righe vuote, troppo corte, simboli isolati
          * scarta righe che matchano i pattern di rumore noto
          * tronca alla prima ancora di footer
          * deduplica righe identiche consecutive (Spotify ripete spesso il titolo)
        """
        if not text:
            return ""


        out: List[str] = []
        prev_norm: Optional[str] = None
        # Contatore di skip consecutivi: se troppi di seguito, siamo entrati
        # nel footer/menu — interrompiamo per evitare di catturare righe-cuscinetto.
        consecutive_skips = 0
        MAX_CONSECUTIVE_SKIPS = 4


        for raw_line in text.split("\n"):
            # Normalizzazione: collapse spazi/tab
            line = re.sub(r"[ \t]+", " ", raw_line).strip()
            if not line:
                if out and out[-1] != "":
                    out.append("")
                continue


            # 5) Tronchiamo se incontriamo un'ancora di footer
            if any(p.match(line) for p in _FOOTER_CUTOFF):
                break


            low = line.lower()
            skip = False


            # Match esatto con lista noise
            if low in _NOISE_EXACT:
                skip = True
            # Match pattern noise
            elif any(p.match(line) for p in _NOISE_PATTERNS):
                skip = True
            # Righe troppo corte (1-2 char) o solo punteggiatura
            elif len(line) <= 2 and not line.isalnum():
                skip = True


            if skip:
                consecutive_skips += 1
                if consecutive_skips >= MAX_CONSECUTIVE_SKIPS:
                    # Footer / menu denso: stop completamente
                    break
                continue
            consecutive_skips = 0


            # Dedup consecutivo
            if line == prev_norm:
                continue
            prev_norm = line


            out.append(line)


        # Collassa più righe vuote consecutive
        cleaned: List[str] = []
        for ln in out:
            if ln == "" and (not cleaned or cleaned[-1] == ""):
                continue
            cleaned.append(ln)


        # Rimuove righe vuote in coda
        while cleaned and cleaned[-1] == "":
            cleaned.pop()


        return "\n".join(cleaned).strip()


    # ------------------------------------------------------------------
    # CLEAN MARKDOWN (path alternativo, solo se _extract_from_main_dom non basta)
    # ------------------------------------------------------------------
    def clean_markdown(self, text: str) -> str:
        if not text:
            return ""
        # Toglie link [testo](url) e immagini ![alt](url)
        text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)
        text = re.sub(r'(?<!\!)\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # Riusa la pulizia line-based
        return self._clean_lines(text)


    # ------------------------------------------------------------------
    # FALLBACK: estrazione da meta tag + JSON-LD
    # ------------------------------------------------------------------
    def _extract_from_metadata(self, html: str) -> str:
        """Usato quando l'HTML è solo lo shell SPA: leggiamo og:, twitter:, JSON-LD."""
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        pieces: List[str] = []


        title_tag = soup.find("title")
        if title_tag and title_tag.get_text(strip=True):
            pieces.append(title_tag.get_text(strip=True))


        meta_map: Dict[str, str] = {}
        for meta in soup.find_all("meta"):
            key = (meta.get("property") or meta.get("name") or "").lower()
            content = (meta.get("content") or "").strip()
            if key and content:
                meta_map[key] = content


        for k in ("og:title", "twitter:title",
                  "og:description", "twitter:description", "description",
                  "music:musician", "music:album", "music:song",
                  "og:audio", "og:type"):
            v = meta_map.get(k)
            if v:
                pieces.append(v)


        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            pieces.extend(self._flatten_jsonld(data))


        result_lines: List[str] = []
        seen = set()
        for p in pieces:
            p = re.sub(r"\s+", " ", p).strip()
            if p and p not in seen:
                seen.add(p)
                result_lines.append(p)
        return "\n\n".join(result_lines)


    def _flatten_jsonld(self, node: Any) -> List[str]:
        out: List[str] = []
        if isinstance(node, dict):
            for key in ("name", "headline", "description", "datePublished"):
                v = node.get(key)
                if isinstance(v, str):
                    out.append(v)
                elif isinstance(v, dict) and isinstance(v.get("name"), str):
                    out.append(v["name"])
            by = node.get("byArtist") or node.get("author")
            if isinstance(by, dict) and isinstance(by.get("name"), str):
                out.append(by["name"])
            elif isinstance(by, list):
                for b in by:
                    if isinstance(b, dict) and isinstance(b.get("name"), str):
                        out.append(b["name"])
            for coll in ("track", "episode", "hasPart", "itemListElement"):
                items = node.get(coll)
                if isinstance(items, list):
                    for it in items:
                        out.extend(self._flatten_jsonld(it))
        elif isinstance(node, list):
            for it in node:
                out.extend(self._flatten_jsonld(it))
        return out

