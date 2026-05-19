import os
import time
import json
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple


import mariadb




# -----------------------------------------------------------------------------
# CONFIGURAZIONE
# -----------------------------------------------------------------------------
DB_HOST = os.getenv("DB_HOST", "database")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "esonero")
DB_PASSWORD = os.getenv("DB_PASSWORD", "esonero_pwd")
DB_NAME = os.getenv("DB_NAME", "esonero")




# -----------------------------------------------------------------------------
# SCHEMA (DDL)
# -----------------------------------------------------------------------------
SCHEMA_DDL = [
    """
    CREATE TABLE IF NOT EXISTS web_resources (
        url        VARCHAR(191) NOT NULL,
        domain     VARCHAR(191) NOT NULL,
        title      VARCHAR(255) NOT NULL DEFAULT '',
        html_text  LONGTEXT      NOT NULL,
        created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (url)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS gold_standard (
        url        VARCHAR(191) NOT NULL,
        gold_text  LONGTEXT      NOT NULL,
        created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (url),
        CONSTRAINT fk_gs_url FOREIGN KEY (url)
            REFERENCES web_resources(url) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS evaluations (
        url        VARCHAR(191) NOT NULL,
        metrics    LONGTEXT      NOT NULL,
        created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (url),
        CONSTRAINT fk_eval_url FOREIGN KEY (url)
            REFERENCES web_resources(url) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS judge_evaluations (
        url            VARCHAR(191)  NOT NULL,
        model_name     VARCHAR(191)  NOT NULL,
        judge_score    INT           NOT NULL,
        judge_feedback TEXT          NOT NULL,
        created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (url, model_name),
        CONSTRAINT fk_judge_url FOREIGN KEY (url)
            REFERENCES web_resources(url) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]




class Database:
    """Wrapper sottile su MariaDB Connector/Python con metodi specifici del progetto."""


    def __init__(self) -> None:
        self._conn_kwargs = dict(
            host=DB_HOST, port=DB_PORT,
            user=DB_USER, password=DB_PASSWORD,
            database=DB_NAME, autocommit=True,
        )


    # ------------------------------------------------------------------
    # Connection / health
    # ------------------------------------------------------------------
    def _connect(self) -> mariadb.Connection:
        return mariadb.connect(**self._conn_kwargs)


    @contextmanager
    def cursor(self, dictionary: bool = False):
        """Context manager che apre/chiude la connessione e il cursore."""
        conn = self._connect()
        try:
            cur = conn.cursor(dictionary=dictionary)
            try:
                yield cur
            finally:
                cur.close()
        finally:
            conn.close()


    def ping(self) -> bool:
        """Verifica se il DB è raggiungibile. Usato da /status."""
        try:
            with self.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        except Exception:
            return False


    def wait_until_ready(self, timeout: int = 60) -> None:
        """Attende che il container MariaDB sia pronto (usato all'avvio)."""
        deadline = time.time() + timeout
        last_err: Optional[Exception] = None
        while time.time() < deadline:
            try:
                with self.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                return
            except Exception as e:
                last_err = e
                time.sleep(2)
        raise RuntimeError(f"Database non raggiungibile entro {timeout}s: {last_err}")


    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------
    def init_schema(self) -> None:
        """Crea le tabelle obbligatorie + ausiliarie se non esistono."""
        with self.cursor() as cur:
            for stmt in SCHEMA_DDL:
                cur.execute(stmt)


    # ------------------------------------------------------------------
    # web_resources
    # ------------------------------------------------------------------
    def upsert_web_resource(self, url: str, domain: str, title: str, html_text: str) -> None:
        """Inserisce o aggiorna una risorsa web (idempotente)."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO web_resources (url, domain, title, html_text)
                VALUES (?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    domain = VALUES(domain),
                    title = VALUES(title),
                    html_text = VALUES(html_text)
                """,
                (url, domain, title or "", html_text or ""),
            )


    def get_web_resource(self, url: str) -> Optional[Dict[str, Any]]:
        with self.cursor(dictionary=True) as cur:
            cur.execute("SELECT * FROM web_resources WHERE url = ?", (url,))
            return cur.fetchone()


    def delete_web_resource(self, url: str) -> bool:
        with self.cursor() as cur:
            cur.execute("DELETE FROM web_resources WHERE url = ?", (url,))
            return cur.rowcount > 0


    def count_web_resources_by_domain(self) -> Dict[str, int]:
        with self.cursor() as cur:
            cur.execute("SELECT domain, COUNT(*) FROM web_resources GROUP BY domain")
            return {row[0]: int(row[1]) for row in cur.fetchall()}


    # ------------------------------------------------------------------
    # gold_standard
    # ------------------------------------------------------------------
    def upsert_gold_standard(self, url: str, gold_text: str) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO gold_standard (url, gold_text)
                VALUES (?, ?)
                ON DUPLICATE KEY UPDATE gold_text = VALUES(gold_text)
                """,
                (url, gold_text or ""),
            )


    def get_gold_standard(self, url: str) -> Optional[Dict[str, Any]]:
        """Join con web_resources per restituire anche domain/title/html_text."""
        with self.cursor(dictionary=True) as cur:
            cur.execute(
                """
                SELECT w.url, w.domain, w.title, w.html_text, g.gold_text
                FROM gold_standard g
                JOIN web_resources w ON w.url = g.url
                WHERE g.url = ?
                """,
                (url,),
            )
            return cur.fetchone()


    def delete_gold_standard(self, url: str) -> bool:
        with self.cursor() as cur:
            cur.execute("DELETE FROM gold_standard WHERE url = ?", (url,))
            return cur.rowcount > 0


    def list_gs_urls_by_domain(self, domain: str) -> List[str]:
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT g.url FROM gold_standard g
                JOIN web_resources w ON w.url = g.url
                WHERE w.domain = ?
                ORDER BY g.url
                """,
                (domain,),
            )
            return [row[0] for row in cur.fetchall()]


    def list_gs_entries_by_domain(self, domain: str) -> List[Dict[str, Any]]:
        with self.cursor(dictionary=True) as cur:
            cur.execute(
                """
                SELECT w.url, w.domain, w.title, w.html_text, g.gold_text
                FROM gold_standard g
                JOIN web_resources w ON w.url = g.url
                WHERE w.domain = ?
                ORDER BY g.url
                """,
                (domain,),
            )
            return cur.fetchall()


    def count_gs_by_domain(self) -> Dict[str, int]:
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT w.domain, COUNT(*) FROM gold_standard g
                JOIN web_resources w ON w.url = g.url
                GROUP BY w.domain
                """
            )
            return {row[0]: int(row[1]) for row in cur.fetchall()}


    # ------------------------------------------------------------------
    # evaluations  /  judge_evaluations
    # ------------------------------------------------------------------
    def save_evaluation(self, url: str, metrics: Dict[str, Any]) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluations (url, metrics)
                VALUES (?, ?)
                ON DUPLICATE KEY UPDATE metrics = VALUES(metrics)
                """,
                (url, json.dumps(metrics)),
            )


    def save_judge_evaluation(self, url: str, model_name: str,
                              judge_score: int, judge_feedback: str) -> None:
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO judge_evaluations (url, model_name, judge_score, judge_feedback)
                VALUES (?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    judge_score = VALUES(judge_score),
                    judge_feedback = VALUES(judge_feedback)
                """,
                (url, model_name, int(judge_score), judge_feedback or ""),
            )


    def avg_metrics_by_domain(self) -> Dict[str, Dict[str, float]]:
        """Restituisce la media F1/precision/recall per dominio dalle valutazioni salvate."""
        with self.cursor(dictionary=True) as cur:
            cur.execute(
                """
                SELECT w.domain, e.metrics
                FROM evaluations e
                JOIN web_resources w ON w.url = e.url
                """
            )
            rows = cur.fetchall()


        agg: Dict[str, List[Tuple[float, float, float]]] = {}
        for row in rows:
            try:
                m = json.loads(row["metrics"])
                token = m.get("token_level_eval") or m
                agg.setdefault(row["domain"], []).append((
                    float(token.get("precision", 0.0)),
                    float(token.get("recall", 0.0)),
                    float(token.get("f1", 0.0)),
                ))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        out: Dict[str, Dict[str, float]] = {}
        for domain, lst in agg.items():
            n = len(lst) or 1
            out[domain] = {
                "precision": round(sum(p for p, _, _ in lst) / n, 4),
                "recall":    round(sum(r for _, r, _ in lst) / n, 4),
                "f1":        round(sum(f for _, _, f in lst) / n, 4),
            }
        return out


    def avg_judge_by_domain(self) -> Dict[str, float]:
        with self.cursor(dictionary=True) as cur:
            cur.execute(
                """
                SELECT w.domain, AVG(j.judge_score) AS avg_score
                FROM judge_evaluations j
                JOIN web_resources w ON w.url = j.url
                GROUP BY w.domain
                """
            )
            return {row["domain"]: round(float(row["avg_score"] or 0.0), 4)
                    for row in cur.fetchall()}


    # ------------------------------------------------------------------
    # Introspezione schema (per /db_schema)
    # ------------------------------------------------------------------
    def describe_schema(self) -> Dict[str, Dict[str, str]]:
        """Costruisce dinamicamente la descrizione richiesta da /db_schema."""
        result: Dict[str, Dict[str, str]] = {}
        with self.cursor(dictionary=True) as cur:
            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_KEY
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = ?
                ORDER BY TABLE_NAME, ORDINAL_POSITION
                """,
                (DB_NAME,),
            )
            cols = cur.fetchall()


            cur.execute(
                """
                SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = ? AND REFERENCED_TABLE_NAME IS NOT NULL
                """,
                (DB_NAME,),
            )
            fk_map = {
                (row["TABLE_NAME"], row["COLUMN_NAME"]):
                f'FK({row["REFERENCED_TABLE_NAME"]}.{row["REFERENCED_COLUMN_NAME"]})'
                for row in cur.fetchall()
            }


        for row in cols:
            tbl, col = row["TABLE_NAME"], row["COLUMN_NAME"]
            descriptors = [row["COLUMN_TYPE"]]
            if row["COLUMN_KEY"] == "PRI":
                descriptors.append("PK")
            fk = fk_map.get((tbl, col))
            if fk:
                descriptors.append(fk)
            result.setdefault(tbl, {})[col] = ", ".join(descriptors)
        return result




# Singleton riusato da server.py e init_db.py
db = Database()

