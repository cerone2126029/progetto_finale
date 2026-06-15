import re
from typing import List, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from crawl4ai import CrawlerRunConfig, CacheMode
from parsers.basewebparser import BaseWebParser

class SpotifyParser(BaseWebParser):    
    def __init__(self):
        """
        Inizializza il parser Spotify configurando le opzioni di crawling.
        Bypassa la cache, attende il caricamento della rete (networkidle)
        e ignora script, style, nav e immagini per alleggerire il DOM.
        """
        super().__init__()
        self.run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until="networkidle",
            delay_before_return_html=3.0,
            exclude_external_links=True,
            exclude_social_media_links=True,
            exclude_all_images=True,
            css_selector="main",
            excluded_tags=["nav", "footer", "header", "aside", "script", "style", "noscript", "form"],
        )

    def _extract_html_title(self, html: str) -> str:
        """
        Override del metodo della classe base per garantire l'estrazione
        del titolo corretto sia in modalità Live che in modalità Local dal DB.
        """

        if not html: 
            return "Spotify Content"
            
        soup = BeautifulSoup(html, "html.parser")
        
        title_tag = soup.find("title")
        if title_tag:
            raw_title = title_tag.get_text()
            cleaned_title = raw_title.split(" - ")[0].split(" | ")[0].strip()
            if cleaned_title and cleaned_title.lower() not in ["spotify", "spotify – web player", "spotify content"]:
                return cleaned_title
                
        h1_tag = soup.find("h1")
        if h1_tag:
            return h1_tag.get_text(strip=True)
            
        for t in soup(["script", "noscript", "style", "nav", "footer", "header"]):
            t.decompose()
        testo_grezzo = soup.get_text(separator="\n", strip=True).split('\n')
        non_empty = [l.strip() for l in testo_grezzo if l.strip()]
        
        fallback_title = self.extract_title_from_raw(non_empty)
        if fallback_title and fallback_title != "Spotify Content":
            return fallback_title
            
        return "Spotify Content"
    
    @staticmethod
    def fix_spacing(text: str) -> str:
        """
        Corregge gli errori tipografici di spaziatura generati dal join di elementi DOM.
        Separa CamelCase, Lettera-Numero e aggiunge spazi mancanti dopo parentesi chiuse.
        """

        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
        text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)
        text = re.sub(r'(\d{4})(\d{1,2}:\d{2})', r'\1 \2', text)
        text = re.sub(r'(\))([A-Za-z0-9])', r'\1 \2', text)
        return text

    @staticmethod
    def fix_concatenations(line: str) -> str:
        """
        Ripara le concatenazioni errate che si verificano prima di parentesi quadre
        (tipico nei tag estratti dalla cache) preservando eventuali link Markdown.
        """

        line = re.sub(r'([a-zA-Z])\[', r'\1 [', line)
        parts = re.split(r'(\[[^\]]+\]\([^)]+\))', line)
        for i in range(len(parts)):
            if not parts[i]: continue
            if not parts[i].startswith('['):
                parts[i] = SpotifyParser.fix_spacing(parts[i])
            else:
                match = re.match(r'\[([^\]]+)\](\([^)]+\))', parts[i])
                if match:
                    testo_pulito = SpotifyParser.fix_spacing(match.group(1))
                    parts[i] = f"[{testo_pulito}]{match.group(2)}"
        return "".join(parts)

    @staticmethod
    def strip_links(text: str) -> str:
        """
        Rimuove la formattazione dei link Markdown `[testo](url)` lasciando solo il testo.
        Rimuove completamente eventuali link vuoti `[](url)`.
        """

        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1 ', text)
        text = re.sub(r'\[\]\([^)]+\)', '', text)
        return text

    @staticmethod
    def detect_spotify_type(text: str) -> str:
        """
        Analizza semanticamente il testo grezzo per inferire la tipologia 
        di contenuto musicale della pagina (Album, Brano, Playlist, Podcast).
        """

        t = text.lower()
        if "playlist pubblica" in t or "public playlist" in t: return "Playlist pubblica"
        if "brano" in t or "lyrics" in t or "song" in t: return "Brano"
        if "episodio" in t or "podcast" in t or "episode" in t: return "Episodi podcast"
        return "Album"

    @staticmethod
    def extract_title_from_raw(lines: List[str]) -> str:
        """
        Estrazione euristica del titolo ricercando la prima riga utile (lunghezza > 3)
        nelle prime 15 righe del documento, saltando le parole chiave di cache e cookie.
        """

        for line in lines[:15]:
            if len(line) > 3 and not any(noise in line.lower() for noise in ["spotify", "web player", "google", "cache", "cookie"]):
                return line.strip()
        return "Spotify Content"

    @staticmethod
    def clean(text: str) -> str:
        """
        Esegue una pulizia aggressiva finale del testo (soprattutto per fallback).
        Filtra parole chiave note di UI, contatori, durate e rimuove righe vuote duplicate.
        """

        if not text: return ""
        text = SpotifyParser.strip_links(text)
        lines = text.split('\n')
        
        header = SpotifyParser.detect_spotify_type(text)
        
        non_empty = [l.strip() for l in lines if l.strip()]
        title = SpotifyParser.extract_title_from_raw(non_empty)
        
        cleaned_lines = [header, "", title, ""]
        
        noise = [
            "vai al contenuto", "skip to", "accedi", "iscriviti", "cookie", "©", "℗", "mostra altro",
            "scegli una lingua", "choose a language", "data di aggiunta", "date added", 
            "riproduzioni", "ascoltatori mensili", "monthly listeners", "carica altro", "load more",
            "riproduci", "salva", "condividi", "altre opzioni", "more options"
        ]
        
        prev_line = None
        for line in lines:
            line = line.strip()
            
            if not line:
                if cleaned_lines and cleaned_lines[-1] != "":
                    cleaned_lines.append("")
                continue
                
            if line.lower() == header.lower() or line == title: continue
            if any(n in line.lower() for n in noise): continue
            
            if line.lower() in ["e", "esplicito", "explicit", "anteprima", "preview", "testo", "lyrics"]: continue
            
            if bool(re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', line)): continue
            if bool(re.match(r'^\d+\s+(brani|songs),?.*$', line.lower())): continue
            
            line = SpotifyParser.fix_concatenations(line)
            
            if line and line != prev_line:
                cleaned_lines.append(line)
                prev_line = line
            
        return "\n".join(cleaned_lines).strip()

    def extract_data(self, result):
        """
        Entry point principale del parser per i dati estratti dal crawler (Live).
        Prepara il dizionario con l'URL, il dominio, il titolo e l'output Markdown.
        """

        html = getattr(result, "html", "") or ""
        soup = BeautifulSoup(html, "html.parser")
        extracted_title = "Spotify Content"
    
        title_tag = soup.find("title")
        if title_tag:
           raw_title = title_tag.get_text()
           cleaned_title = raw_title.split(" - ")[0].split(" | ")[0].strip()
           if cleaned_title and cleaned_title.lower() not in ["spotify", "spotify – web player"]:
               extracted_title = cleaned_title
        else:
           h1_tag = soup.find("h1")
           if h1_tag:
               extracted_title = h1_tag.get_text(strip=True)
            
        return {
           "url": getattr(result, "url", ""),
           "domain": "open.spotify.com",
           "title": self._extract_html_title(html),
           "html_text": html,
           "parsed_text": self._orchestrate_extraction(html)
        }

    def parse_offline_html(self, html_content: str) -> str:
        """
        Entry point secondario del parser per i dati provenienti dal Database (Local=True).
        Invia direttamente l'HTML archiviato all'orchestratore.
        """

        return self._orchestrate_extraction(html_content)

    @staticmethod
    def extract_main_artist(lines: List[str], title: str) -> List[str]:
        """
        Ricerca e identifica il nome dell'artista o del creatore principale,
        solitamente posizionato subito sotto la riga del titolo dell'album/brano.
        """

        for i, line in enumerate(lines):
            if line == title and i + 1 < len(lines):
                candidate = lines[i+1].split('•')[0].strip()
                if candidate and len(candidate) > 2 and candidate.lower() not in ["album", "singolo", "ep"]:
                    return [candidate]
        return []

    def _orchestrate_extraction(self, html: str) -> str:
        """
        Motore centrale del parser. Decostruisce il DOM HTML, smaltisce le interfacce
        note (UI, banner, cache tag) e indirizza il flusso semantico verso
        il modulo specializzato corrispondente (Live DOM, Playlist, Podcast, Brano, Album).
        """

        if not html: return ""
        
        html = re.sub(r'<div[^>]*id="bN015htcoyT__google-cache-hdr"[^>]*>.*?</div>', '', html, flags=re.DOTALL|re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL|re.IGNORECASE)

        soup = BeautifulSoup(html, "html.parser")
        
        ui_selectors = [
            "#onetrust-consent-sdk", "[data-testid='cookie-banner']", 
            "[data-testid='topbar']", "[data-testid='page-footer']",
            "[data-testid='login-button']", "[data-testid='signup-button']",
            "[data-testid='action-bar-row']", "nav", "footer", "header", "aside"
        ]
        for selector in ui_selectors:
            for tag in soup.select(selector):
                tag.decompose()

        for t in soup(["script", "noscript", "form", "svg", "button", "img"]): 
            t.decompose()
            
        main_root = soup.find("main")
        if not main_root or len(main_root.get_text(strip=True)) < 50:
             main_root = soup.body or soup
             
        full_text = main_root.get_text(separator="\n", strip=True)
        header = SpotifyParser.detect_spotify_type(full_text)
        
        if header in ["Album", "Playlist pubblica"]:
            track_rows = main_root.select("[data-testid='tracklist-row']")
            if track_rows and len(track_rows) > 0:
                lines = []
                title_tag = main_root.select_one("h1")
                title = title_tag.get_text(strip=True) if title_tag else "Spotify Content"
                lines.append(f"{header}\n\n{title}\n")
                
                for row in track_rows:
                    text_elements = row.select("div[data-encore-id='text']")
                    for el in text_elements:
                        txt = el.get_text(strip=True)
                        if txt and not bool(re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', txt)): 
                            lines.append(txt)
                return "\n".join(lines).strip()

        lines = full_text.split('\n')
        non_empty = [l.strip() for l in lines if l.strip()]
        title = SpotifyParser.extract_title_from_raw(non_empty)

        if header == "Playlist pubblica":
            ext_lines = [header, "", title, ""]
            start_idx = 0
            for i, line in enumerate(non_empty):
                if line == title:
                    start_idx = i + 1
                    break
            
            for line in non_empty[start_idx:start_idx+15]:
                 if "brani" in line.lower() or "salvataggi" in line.lower() or "ha vinto il festival" in line.lower():
                     ext_lines.append(line)
            
            ext_lines.append("")
            
            for i, line in enumerate(non_empty):
                if line.lower() == "aggiunto il giorno" or line.lower() == "date added":
                    start_idx = i + 1
                    ext_lines.append("#Titolo Album Aggiunto il giorno\n")
                    break
            
            prev_line = None
            track_counter = 1
            for line in non_empty[start_idx:]:
                low = line.lower()
                if any(end in low for end in ["©", "℗", "ti potrebbe", "more by", "ascoltatori", "fans also like"]): break
                if low in ["e", "esplicito", "explicit", "anteprima", "preview", "riproduci", "salva"]: continue
                
                line = SpotifyParser.fix_concatenations(line)
                if line and line != prev_line:
                    if prev_line and bool(re.match(r'^\d{1,2}:\d{2}$', prev_line)):
                         ext_lines.append("")
                         ext_lines.append(str(track_counter))
                         track_counter += 1
                    elif track_counter == 1 and line == non_empty[start_idx]:
                         ext_lines.append(str(track_counter))
                         track_counter += 1
                         
                    ext_lines.append(line)
                    prev_line = line
            
            return "\n".join(ext_lines).strip()
            
        if header == "Episodi podcast":
            month_map = {
                "Jan": "gen", "Feb": "feb", "Mar": "mar", "Apr": "apr",
                "May": "mag", "Jun": "giu", "Jul": "lug", "Aug": "ago",
                "Sep": "set", "Oct": "ott", "Nov": "nov", "Dec": "dic"
            }
            ext_lines = [header, "", title, ""]
            start_idx = 0
            for i, line in enumerate(non_empty):
                if line == title:
                    start_idx = i + 1
                    break
                    
            pending_date = None
            prev_line = None
            
            for line in non_empty[start_idx:]:
                low = line.lower()
                
                if low in ["e", "esplicito", "explicit", "riproduci", "salva", "see all episodes", "show all", "podcast episode", "episodi podcast", "all episodes"]: continue
                
                if low == "more episodes like this" or low == "more podcasts like this": line = "Altri episodi simili"
                elif low == "episode description": line = "Descrizione dell'episodio"
                elif low == "about": line = "Informazioni"
                    
                line = SpotifyParser.fix_concatenations(line)
                
                date_match = re.match(r'^([A-Z][a-z]{2})\s+(\d{1,2})(,\s*\d{4})?$', line)
                if date_match:
                    m_eng = date_match.group(1)
                    d = date_match.group(2)
                    y = date_match.group(3).replace(",", "") if date_match.group(3) else ""
                    m_ita = month_map.get(m_eng, m_eng.lower())
                    line = f"{d} {m_ita}{y}"
                
                low_check = line.lower()
                if "sec" in low_check and not low_check.endswith("sec."): line = line.replace("sec", "sec.")
                line = re.sub(r'\bhr\b', 'ora', line)
                line = re.sub(r'\bhrs\b', 'ore', line)
                
                is_date = bool(re.match(r'^\d{1,2}\s+[a-z]{3}(\s+\d{4})?$', line.lower()))
                is_duration = ("min" in line.lower() or "sec" in line.lower() or "ora" in line.lower() or "ore" in line.lower())
                
                if is_date:
                    pending_date = line
                    continue
                    
                if is_duration and pending_date:
                    line = f"{pending_date} • {line}"
                    pending_date = None
                elif pending_date:
                    if pending_date != ext_lines[-1] if ext_lines else "": ext_lines.append(pending_date)
                    pending_date = None

                if line == "•" and ext_lines:
                    ext_lines[-1] = ext_lines[-1] + " •"
                    continue
                if ext_lines and ext_lines[-1].endswith(" •"):
                    ext_lines[-1] = ext_lines[-1] + " " + line
                    continue
                    
                if line and line != prev_line:
                    ext_lines.append(line)
                    prev_line = line
                    
            if pending_date: ext_lines.append(pending_date)
            return "\n".join(ext_lines).strip()

        if header == "Brano":
            ext_lines = [header, "", title, ""]
            start_idx = 0
            for i, line in enumerate(non_empty):
                if line == title:
                    start_idx = i + 1
                    break
                    
            prev_line = None
            for line in non_empty[start_idx:]:
                low = line.lower()
                
                if any(end in low for end in ["©", "℗", "scegli una lingua", "choose a language", "distributed by"]): break
                
                if low in ["e", "esplicito", "explicit", "anteprima", "preview", "riproduci", "salva", "sign in to see lyrics and listen to the full track", "show all"]: continue
                
                if low == "artist": line = "Artista"
                elif low == "recommended": line = "Consigliati"
                elif low == "based on this song": line = "In base a questo brano"
                elif low == "popular tracks by": line = "Brani popolari di"
                elif low.startswith("popular releases by"): line = line.replace("Popular Releases by", "Uscite popolari di")
                elif low.startswith("popular albums by"): line = line.replace("Popular Albums by", "Album popolari di")
                elif low.startswith("popular singles and eps by"): line = line.replace("Popular Singles and EPs by", "Singoli ed EP popolari di")
                elif low == "popular releases": line = "Uscite popolari"
                elif low == "recommended releases": line = "Uscite consigliate"
                elif low == "fans also like": line = "I fan apprezzano anche"
                elif low == "from the single": line = "Dal singolo"
                elif low == "album": line = "Album"
                elif low == "single": line = "Singolo"
                
                line = SpotifyParser.fix_concatenations(line)
                
                if re.match(r'^\d{1,3}(,\d{3})+$', line):
                    line = line.replace(",", ".")
                
                if line == "•" and ext_lines:
                    ext_lines[-1] = ext_lines[-1] + " •"
                    continue
                if ext_lines and ext_lines[-1].endswith(" •"):
                    ext_lines[-1] = ext_lines[-1] + " " + line
                    continue
                
                month_map_full = {
                    "january": "gennaio", "february": "febbraio", "march": "marzo", "april": "aprile",
                    "may": "maggio", "june": "giugno", "july": "luglio", "august": "agosto",
                    "september": "settembre", "october": "ottobre", "november": "novembre", "december": "dicembre"
                }
                date_match = re.match(r'^([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})$', line, re.IGNORECASE)
                if date_match:
                    m_eng = date_match.group(1).lower()
                    d = date_match.group(2)
                    y = date_match.group(3)
                    m_ita = month_map_full.get(m_eng, m_eng)
                    line = f"{d} {m_ita} {y}"
                
                if line and line != prev_line:
                    ext_lines.append(line)
                    prev_line = line
                    
            return "\n".join(ext_lines).strip()

        artists = SpotifyParser.extract_main_artist(non_empty, title)
        
        extracted_lines = [header, "", title]
        if artists:
            extracted_lines.append(artists[0])
        extracted_lines.append("")
        
        start_idx = 0
        for i, line in enumerate(non_empty):
            if "brani," in line.lower() or "songs," in line.lower() or line == title:
                start_idx = i + 1
                break
                
        prev_line = None
        for line in non_empty[start_idx:]:
            low = line.lower()
            
            if any(end in low for end in ["data di aggiunta", "date added", "©", "℗", "ti potrebbe", "more by", "ascoltatori", "fans also like"]):
                break
                
            if bool(re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', line)): continue 
            if bool(re.match(r'^\d+\s+(brani|songs),?.*$', low)): continue 
            if low in ["e", "esplicito", "explicit", "anteprima", "preview", "testo", "lyrics", "riproduci", "salva"]: continue
            
            if bool(re.match(r'^(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4}$', low)): continue
            if bool(re.match(r'^\d{4}$', line)): continue

            line = SpotifyParser.fix_concatenations(line)
            
            if header == "Album":
                skip_line = False
                for a in artists:
                    for sub_a in a.split(","):
                        if sub_a.strip().lower() == line.lower():
                            skip_line = True
                            break
                if skip_line: continue
                
            if line and line != prev_line:
                 extracted_lines.append(line)
                 prev_line = line

        pre_cleaned_text = "\n".join(extracted_lines)
        return self.clean(pre_cleaned_text)