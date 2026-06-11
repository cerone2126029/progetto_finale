import re
from typing import List, Optional
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from crawl4ai import CrawlerRunConfig, CacheMode
from parsers.basewebparser import BaseWebParser

class SpotifyParser(BaseWebParser):
    def __init__(self):
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

    @staticmethod
    def fix_spacing(text: str) -> str:
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', text)
        text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', text)
        text = re.sub(r'(\d{4})(\d{1,2}:\d{2})', r'\1 \2', text)
        text = re.sub(r'(\))([A-Za-z0-9])', r'\1 \2', text)
        return text

    @staticmethod
    def fix_concatenations(line: str) -> str:
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
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1 ', text)
        text = re.sub(r'\[\]\([^)]+\)', '', text)
        return text

    @staticmethod
    def detect_spotify_type(text: str) -> str:
        t = text.lower()
        if "playlist pubblica" in t or "public playlist" in t: return "Playlist pubblica"
        if "brano" in t or "lyrics" in t or "song" in t: return "Brano"
        if "episodio" in t or "podcast" in t or "episode" in t: return "Episodi podcast"
        return "Album"

    @staticmethod
    def extract_title_from_raw(lines: List[str]) -> str:
        for line in lines[:15]:
            if len(line) > 3 and not any(noise in line.lower() for noise in ["spotify", "web player", "google", "cache", "cookie"]):
                return line.strip()
        return "Spotify Content"

    @staticmethod
    def extract_main_artist(lines: List[str], title: str) -> List[str]:
        # Cerca l'artista subito sotto il titolo
        for i, line in enumerate(lines):
            if line == title and i + 1 < len(lines):
                # Molto spesso la riga sotto il titolo è "Nome Artista • Anno • N brani"
                candidate = lines[i+1].split('•')[0].strip()
                if candidate and len(candidate) > 2 and candidate.lower() not in ["album", "singolo", "ep"]:
                    return [candidate]
        return []

    @staticmethod
    def clean(text: str) -> str:
        if not text: return ""
        text = SpotifyParser.strip_links(text)
        lines = text.split('\n')
        
        header = SpotifyParser.detect_spotify_type(text)
        
        non_empty = [l.strip() for l in lines if l.strip()]
        title = SpotifyParser.extract_title_from_raw(non_empty)
        artists = SpotifyParser.extract_main_artist(non_empty, title)
        
        cleaned_lines = [header, "", title, ""]
        if artists:
            cleaned_lines.extend([artists[0], ""])
        
        noise = [
            "vai al contenuto", "skip to", "accedi", "iscriviti", "cookie", "©", "℗", "mostra altro",
            "scegli una lingua", "choose a language", "data di aggiunta", "date added", 
            "riproduzioni", "ascoltatori mensili", "monthly listeners", "carica altro", "load more",
            "riproduci", "salva", "condividi", "altre opzioni", "more options", "fans also like"
        ]
        
        prev_line = None
        for line in lines:
            line = line.strip()
            
            if not line: continue
                
            low = line.lower()
            if low == header.lower() or line == title: continue
            if any(n in low for n in noise): continue
            
            # --- AGGIUNTA CHIRURGICA: Rimozione marker espliciti e anteprime ---
            if low in ["e", "esplicito", "explicit", "anteprima", "preview", "testo", "lyrics"]: continue
            
            if bool(re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', line)): continue
            if bool(re.match(r'^\d+\s+(brani|songs),?.*$', low)): continue
            if bool(re.match(r'^\d+$', line)): continue
            if bool(re.match(r'^\d{4}$', line)): continue
            
            # Rimozione ripetizioni dell'artista
            skip_artist = False
            for a in artists:
                if a.lower() == low: skip_artist = True
            if skip_artist: continue
            
            line = SpotifyParser.fix_concatenations(line)
            
            # --- AGGIUNTA CHIRURGICA: Deduplicazione consecutiva ---
            if line and line != prev_line:
                cleaned_lines.append(line)
                prev_line = line
            
        return "\n".join(cleaned_lines).strip()

    def extract_data(self, result):
        html = getattr(result, "html", "") or ""
        return {
            "url": getattr(result, "url", ""),
            "domain": "open.spotify.com",
            "title": self._extract_html_title(html) or "Spotify",
            "html_text": html,
            "parsed_text": self._orchestrate_extraction(html)
        }

    def parse_offline_html(self, html_content: str) -> str:
        return self._orchestrate_extraction(html_content)

    def _orchestrate_extraction(self, html: str) -> str:
        if not html: return ""
        
        # 1. Rimuoviamo la Google Cache e gli stili iniettati
        html = re.sub(r'<div[^>]*id="bN015htcoyT__google-cache-hdr"[^>]*>.*?</div>', '', html, flags=re.DOTALL|re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL|re.IGNORECASE)

        soup = BeautifulSoup(html, "html.parser")
        
        # 2. Rimuoviamo gli elementi UI noti
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
        
        # 3. Logica PRIMARIA: Data-TestId (Ottima per il Live)
        if header in ["Album", "Playlist pubblica"]:
            track_rows = main_root.select("[data-testid='tracklist-row']")
            # --- AGGIUNTA CHIRURGICA: Abbassato il limite per includere gli EP ---
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

        # 4. Logica FALLBACK (Per Offline): "Il Distillatore"
        lines = full_text.split('\n')
        non_empty = [l.strip() for l in lines if l.strip()]
        title = SpotifyParser.extract_title_from_raw(non_empty)
        
        # Tenta di capire l'artista principale per poi rimuoverlo dalle righe dei brani
        artists = SpotifyParser.extract_main_artist(non_empty, title)
        
        # Generiamo il blocco iniziale richiesto dai Gold Standard
        extracted_lines = [header, "", title]
        
        # Aggiungiamo l'artista se trovato
        if artists:
            extracted_lines.append(artists[0])
            
        extracted_lines.append("") # Riga vuota prima delle tracce
        
        start_idx = 0
        # Troviamo dove iniziano effettivamente le tracce
        for i, line in enumerate(non_empty):
            if "brani," in line.lower() or "songs," in line.lower() or line == title:
                start_idx = i + 1
                break
                
        for line in non_empty[start_idx:]:
            low = line.lower()
            
            # Condizioni di arresto per non leggere il footer
            if any(end in low for end in ["data di aggiunta", "date added", "©", "℗", "ti potrebbe", "more by", "ascoltatori", "fans also like"]):
                break
                
            # Filtri di rumore base e numeri
            if bool(re.match(r'^\d+$', line)): continue 
            if bool(re.match(r'^\d{1,2}:\d{2}(:\d{2})?$', line)): continue 
            if bool(re.match(r'^\d+\s+(brani|songs),?.*$', low)): continue 
            if low in ["e", "esplicito", "explicit", "anteprima", "preview", "testo", "lyrics", "riproduci", "salva"]: continue
            
            # Ignora mesi o anni isolati
            if bool(re.match(r'^(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s+\d{4}$', low)): continue
            if bool(re.match(r'^\d{4}$', line)): continue

            line = SpotifyParser.fix_concatenations(line)
            
            # --- LA SOTTRAZIONE DELL'ARTISTA ---
            if header == "Album":
                skip_line = False
                for a in artists:
                    if a.lower() == line.lower():
                        skip_line = True
                        break
                if skip_line: continue
                
            if line:
                 extracted_lines.append(line)

        # Usiamo la clean() come ultimo check ma uniamo con \n
        pre_cleaned_text = "\n".join(extracted_lines)
        return self.clean(pre_cleaned_text)