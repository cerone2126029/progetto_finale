"""
Script di inizializzazione del database.

  1. Attende che il container MariaDB sia pronto
  2. Crea le tabelle se non esistono
  3. Carica i Gold Standard da gs_data/*.json popolando web_resources + gold_standard

"""

import json
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from db import db

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GS_DIR = BASE_DIR / "gs_data"

def _iter_gs_files(gs_dir: Path) -> Iterable[Path]:
    if not gs_dir.exists():
        return []
    return sorted(gs_dir.glob("*.json"))

def _load_json_array(path: Path) -> list:
    """Carica un file JSON di Gold Standard, tollerante alle entry vuote/malformate."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[init_db] Skip {path.name}: {e}")
        return []
    return data if isinstance(data, list) else []

def populate_from_gs_data() -> dict:
    """
    Popola le tabelle a partire dai JSON in gs_data/.
    Restituisce statistiche su quanti record sono stati caricati.
    """
    stats = {"files": 0, "web_resources": 0, "gold_standard": 0, "skipped": 0}

    for path in _iter_gs_files(GS_DIR):
        entries = _load_json_array(path)
        if not entries:
            continue
        stats["files"] += 1

        for entry in entries:
            if not isinstance(entry, dict):
                stats["skipped"] += 1
                continue
            url = entry.get("url")
            if not url:
                stats["skipped"] += 1
                continue

            domain = entry.get("domain") or urlparse(url).netloc
            title = entry.get("title") or ""
            html_text = entry.get("html_text") or ""
            gold_text = entry.get("gold_text") or ""

            db.upsert_web_resource(url, domain, title, html_text)
            stats["web_resources"] += 1

            if gold_text:
                db.upsert_gold_standard(url, gold_text)
                stats["gold_standard"] += 1
    return stats

def main() -> None:
    print("[init_db] In attesa di MariaDB...")
    db.wait_until_ready(timeout=120)
    print("[init_db] MariaDB pronto. Inizializzo lo schema...")
    db.init_schema()
    print("[init_db] Schema OK. Carico i Gold Standard da gs_data/...")
    stats = populate_from_gs_data()
    print(f"[init_db] Caricamento completato: {stats}")

if __name__ == "__main__":
    main()



