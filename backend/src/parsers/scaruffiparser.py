"""
Parser specifico per il dominio scaruffi.com.
A causa dell'architettura "old-web" del sito (layout a tabelle, assenza di tag semantici moderni, 
uso di tag deprecati come <font>), questo parser bypassa la generazione automatica di Markdown
e manipola direttamente l'albero HTML (DOM) tramite BeautifulSoup.
"""

import re
from bs4 import BeautifulSoup
from typing import Optional
from crawl4ai import CrawlerRunConfig, CacheMode
from parsers.basewebparser import BaseWebParser

class ScaruffiParser(BaseWebParser):
    """
    Implementazione del parser per il sito di Piero Scaruffi. 
    Applica pulizie strutturali, euristiche sulla densità dei link ed espressioni 
    regolari custom per estrarre solo il testo enciclopedico/informativo.
    """

    # Blacklist di espressioni regolari per rimuovere il boilerplate ricorrente:
    # copyright, crediti, inviti a navigare, titoli di menu fissi e note dell'autore.
    _SPAZZATURA = [
        r'TM[\s\S]*?Copyright[\s\S]*?All\s+rights\s+reserved\.?',
        r'Copyright[\s\S]*?(?:Piero|Paolo|P\.)?\s*Scaruffi[\s\S]*?All\s+rights\s+reserved\.?',
        r'All\s+photographs\s+are\s+property\s+of[\s\S]*?provided\s+them',
        r'^[ \t]*(?:by[ \t]+)?(?:Piero|Paolo|P\.)?[ \t]*Scaruffi[ \t]*$',
        r'^[ \t]*(?:and|the|by)[ \t]*$',
        r'^[ \t]*[\|\.,\(\)\-][ \t]*$',
        r'^[ \t]*""?[ \t]*$',
        r'What\s+is\s+unique\s+about\s+this\s+music\s+database\??',    
        r'Terms\s+of\s+use',
        r'A\s+history\s+of\s+Jazz\s+Music',
        r'See\s+also\s+the',
        r'The\s+History\s+of\s+Rock\s+Music',
        r'The\s+History\s+of\s+Pop\s+Music',
        r'Main\s+jazz\s+page',
        r'Jazz\s+musicians?',
        r'To\s+purchase\s+the\s+book',
        r'\(?These\s+are\s+excerpts\s+from\s+my\s+book\)?',
        r'"?A\s+History\s+of\s+Jazz\s+Music"?',
        r'Next\s+chapter',
        r'Back\s+to\s+the\s+Index',
        r'Back\s+to\s+the\s+[A-Za-z\s]+',
        r'Links\s+to\s+other\s+sites',
        r'\(\s*(?:[Cc]lick|[Cc]licca|Translation|Translated|Tradotto)[^)]+\)',
        r'\(\s*Copyright[^)]+\)',
    ]

    def __init__(self):
        super().__init__()

        # Configurazione specifica di Crawl4AI per Scaruffi.
        # Viene aggiunto un piccolo delay per assicurarsi che la pagina carichi interamente,
        # e si disabilita la rimozione degli overlay che potrebbe corrompere l'HTML legacy.
        self.run_config = CrawlerRunConfig(
            delay_before_return_html=2,
            remove_overlay_elements=False,
            cache_mode=CacheMode.BYPASS,
            exclude_external_links=True
        )


    def extract_fallback_title(self, url: str) -> Optional[str]:
        """
        Emergenza finale per Scaruffi in caso di assenza del tag <title>.
        Ricava il titolo decodificando e formattando l'ultimo segmento dell'URL.
        """
        if url:
            # Prende l'ultimo pezzo dell'URL (es. "beatles.html" o "cpt12.html")
            raw_title = url.split("/")[-1]
            
            # Toglie l'estensione e sostituisce eventuali trattini/underscore con spazi
            clean_title = raw_title.replace(".html", "").replace(".htm", "").replace("_", " ").replace("-", " ")
            
            # Formatta il titolo con le iniziali maiuscole (es. "beatles" -> "Beatles")
            return clean_title.title()
            
        return None

    def parse_offline_html(self, html_content: str) -> str:
        """
        Metodo per l'elaborazione offline (utile per la valutazione del Gold Standard).
        Crea una classe fittizia (MockResult) per simulare la risposta di Crawl4AI
        e poter riutilizzare la complessa logica di extract_and_clean_text.
        """
        class MockResult:
            def __init__(self, html):
                self.html = html
                self.success = True
        
        return self.extract_and_clean_text(MockResult(html_content))


    def extract_and_clean_text(self, result) -> str:
        """
        Sovrascrive il metodo base. Ignora il parser Markdown integrato in Crawl4AI
        e lavora direttamente sull'HTML grezzo estraendo e filtrando i nodi con BeautifulSoup.
        """
        if not result.success or not result.html:
            return ""

        soup = BeautifulSoup(result.html, "html.parser")
        body = soup.find('body')
        
        if not body:
            return "Nessun tag <body> trovato."

        # 1. ELIMINAZIONE DEL RUMORE INVISIBILE E STRUTTURALE
        # Rimuove script, stili, moduli e i rari tag di navigazione semantica
        for tag in body.find_all(['script', 'style', 'nav', 'iframe', 'form']):
            tag.decompose()
            
        # Rimuove i titoli enormi e i tag font obsoleti (spesso usati per intestazioni/banner su questo sito)
        for tag in body.find_all(['h1', 'h2']):
            tag.decompose()
        for tag in body.find_all('font', size=lambda value: value in ['5', '6', '7']):
            tag.decompose()

        # 2. EURISTICA DELLA DENSITÀ DEI LINK
        # Poiché il sito impagina i menu dentro tabelle o liste, eliminiamo
        # i contenitori in cui il testo cliccabile supera il 40% del testo totale.
        for container in body.find_all(['table', 'ul']):
            links = container.find_all('a')
            if not links:
                continue
            
            # Calcola quanti caratteri appartengono a dei link rispetto al totale del blocco
            text_in_links = sum(len(a.get_text(strip=True)) for a in links)
            total_text = len(container.get_text(strip=True))
            
            if total_text > 0 and (text_in_links / total_text) > 0.40:
                container.decompose()

        # 3. ESTRAZIONE DEL TESTO GREZZO
        raw_text = body.get_text(separator="\n", strip=True)

        # 4. APPLICAZIONE DELLA BLACKLIST (Boilerplate removal)
        # Passa tutte le regex di _SPAZZATURA per cancellare diciture ripetitive
        for pattern in self._SPAZZATURA:
            raw_text = re.sub(pattern, '', raw_text, flags=re.IGNORECASE)

        # 5. PULIZIA FINALE E FORMATTAZIONE
        # Rimuove le righe vuote e i caratteri isolati come le pipe "|"
        clean_lines = []
        for line in raw_text.split('\n'):
            line = line.strip()
            if line and line != "|":
                clean_lines.append(line)

        # Unisce le righe con doppio a capo per simulare paragrafi puliti
        return "\n\n".join(clean_lines)