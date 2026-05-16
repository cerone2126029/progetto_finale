"""
Modulo base per l'estrazione e il parsing dei contenuti web.
Definisce l'interfaccia astratta e le configurazioni di default di Crawl4AI
che verranno ereditate dai parser dei domini specifici.
"""

from urllib.parse import urlparse
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode


class BaseWebParser:
    """
    Classe base da cui ereditano tutti i parser di dominio (Wikipedia, Scaruffi, ecc.).
    Fornisce i metodi comuni per avviare il crawler, estrarre il titolo e restituire i dati.
    """
    def __init__(self):
        # Configurazione del browser virtuale (headless per non aprire finestre visibili)
        self.browser_config = BrowserConfig(
            headless=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"      
        )

        # Configurazione di default per il crawling (ignora la cache e non segue link esterni)
        self.run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            exclude_external_links=True,
        )

    async def parse_single(self, url: str) -> Dict[str, Any]:
        """
        FASE FINALE: Metodo usato dall'endpoint FastAPI per analizzare un solo URL in tempo reale.
        Avvia il crawler per una singola pagina e restituisce il dizionario.
        """
        # Il context manager (async with) assicura che il crawler venga chiuso correttamente
        async with AsyncWebCrawler(config=self.browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=self.run_config
            )
            return self.extract_data(result)

    async def parse_batch(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        FASE DI TESTING: Metodo usato dallo script locale per analizzare liste di URL
        (utile per estrarre dati massivamente o confrontare con il Gold Standard).
        """
        results_list = []
        async with AsyncWebCrawler(config=self.browser_config) as crawler:
            for url in urls:
                result = await crawler.arun(
                    url=url,
                    config=self.run_config
                )
                results_list.append(self.extract_data(result))
        return results_list

    def extract_data(self, result) -> Dict[str, Any]:
        """
        Aggrega i dati estratti dal crawler (titolo, HTML grezzo, testo pulito)
        in un dizionario standardizzato. Include una logica di fallback per il titolo.
        """
        domain = urlparse(result.url).netloc

        # --- CATENA DI FALLBACK PER IL TITOLO ---
        # 1° tentativo: cerca nei metadati estratti nativamente da Crawl4AI
        title = result.metadata.get('title') if result.metadata else None

        # 2° tentativo di estrazione del titolo dal tag HTML
        if not title and result.html:
            title = self._extract_html_title(result.html)

        # 3° tentativo di estrazione del titolo (CORRETTO - fallback basato su URL)
        if not title:
            title = self.extract_fallback_title(result.url)

        # Estrazione del Markdown nativo generato da Crawl4AI o del testo processato
        cleaned_text = self.extract_and_clean_text(result)

        return {
            "url": result.url,
            "domain": domain,
            "title": title,
            "html_text": result.html or "",
            "parsed_text": cleaned_text
        }
    
    def extract_and_clean_text(self, result) -> str:
        """
        Di base: usa il Markdown di Crawl4AI e chiama clean_markdown.
        (TravelState e Wikipedia useranno questo comportamento di base, Scaruffi lo sovrascriverà).
        """
        raw_markdown = result.markdown if hasattr(result, 'markdown') and result.markdown else ""
        return self.clean_markdown(raw_markdown.strip())
    
    def clean_markdown(self, text: str) -> str:
        """
        Pulizia del testo.
        Di base restituisce il testo intatto. Le classi figlie devono 
        sovrascriverlo per applicare le loro Regex di pulizia.
        """
        return text
    
    def extract_fallback_title(self, url: str) -> Optional[str]:
        """
        Emergenza finale: Estrazione dall'URL. 
        Di base restituisce None. Le classi figlie lo implementeranno in modo specifico.
        """
        return None

    def _extract_html_title(self, html: str) -> Optional[str]:
        """Funzione di supporto per cercare il tag <title> con BeautifulSoup."""
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        return title_tag.get_text(strip=True) if title_tag else None