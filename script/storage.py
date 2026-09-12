import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from script.domains import site


def fingerprint(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


class Store:
    """Local audit + opt-in reports. User reports never promote reviewed fingerprints."""

    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS audits(id TEXT PRIMARY KEY, created TEXT, site TEXT, path_hash TEXT, result TEXT);
                CREATE TABLE IF NOT EXISTS reports(site TEXT, fingerprint TEXT, reporter_hash TEXT,
                    PRIMARY KEY(site, fingerprint, reporter_hash));
                CREATE TABLE IF NOT EXISTS fingerprints(fingerprint TEXT PRIMARY KEY, campaign TEXT, reviewed INTEGER);
            """)
        Path(path).chmod(0o600)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, url: str, analysis: dict) -> str:
        id = uuid.uuid4().hex
        # Only generated evidence summaries: never save input URL, page text or network bodies.
        with self.connect() as db:
            db.execute(
                "INSERT INTO audits VALUES(?,?,?,?,?)",
                (
                    id,
                    datetime.now(UTC).isoformat(),
                    site(url),
                    fingerprint(urlsplit(url).path),
                    json.dumps(analysis, ensure_ascii=False),
                ),
            )
        return id

    def report(self, url: str, template: str, reporter_hash: str, *, consent: bool) -> None:
        if not consent:
            raise ValueError("explicit sharing consent is required")
        if len(reporter_hash) != 64 or any(c not in "0123456789abcdef" for c in reporter_hash):
            raise ValueError("expected server-issued SHA-256 pseudonym")
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO reports VALUES(?,?,?)",
                (site(url), fingerprint(template), reporter_hash),
            )

    def report_count(self, url: str) -> int:
        with self.connect() as db:
            return db.execute(
                "SELECT count(DISTINCT reporter_hash) FROM reports WHERE site=?", (site(url),)
            ).fetchone()[0]

    def add_reviewed_fingerprint(self, template: str, campaign: str):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO fingerprints VALUES(?,?,1)", (fingerprint(template), campaign))

    def query_fingerprint_db(self, template: str) -> dict:
        if not template.strip():
            return {"matched": False}
        with self.connect() as db:
            row = db.execute(
                "SELECT campaign FROM fingerprints WHERE fingerprint=? AND reviewed=1",
                (fingerprint(template),),
            ).fetchone()
        return {"matched": bool(row)}  # Campaign free text is not sent to LLM or automatic verdicts.

    def replay(self, audit_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT result FROM audits WHERE id=?", (audit_id,)).fetchone()
        if not row:
            raise KeyError(audit_id)
        return json.loads(row[0])
