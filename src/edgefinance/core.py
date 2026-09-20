from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import tomllib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

UTC = timezone.utc
PACKAGE = Path(__file__).parent


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def digest(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def write(path: Path, value: str | bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value.encode("utf-8") if isinstance(value, str) else value
    fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def jsonfile(path: Path, value):
    write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def readjson(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def public_url(url: str) -> str:
    p = urlsplit(url)
    if p.scheme not in {"https", "http"} or not p.hostname or p.username or p.password:
        raise ValueError("Invalid public source URL")
    if re.search(r"(?:api_key|apikey|token|password|secret)=", p.query, re.I):
        raise ValueError("Credential-bearing URL cannot be public")
    return url


def date_only(value: str) -> str:
    datetime.strptime(value[:10], "%Y-%m-%d")
    return value[:10]


class Project:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.settings = tomllib.loads((self.root / "config/settings.toml").read_text(encoding="utf-8"))
        self.sources = readjson(self.root / "config/sources.json")
        self.companies = readjson(self.root / "config/companies.json")
        economies = self.root / "config/economies.json"
        self.economies = readjson(economies) if economies.exists() else []
        self.topics = readjson(self.root / "config/topics.json")
        self.secrets = {**dotenv_values(self.root / ".env"), **dotenv_values(self.root / "atlas-credentials.env"), **os.environ}
        self.data = self.root / "data"
        self.data.mkdir(exist_ok=True)

    def store(self):
        return Store(self.data)

    def topic_ids(self, text: str) -> list[str]:
        lower = text.lower()
        return [t["id"] for t in self.topics if any(k.lower() in lower for k in t["keywords"])]


class Store:
    def __init__(self, data: Path):
        self.data = data
        data.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(data / "research.sqlite3", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, document_id TEXT NOT NULL, published_at TEXT NOT NULL,
          first_seen_at TEXT NOT NULL, source_id TEXT NOT NULL, content_hash TEXT NOT NULL,
          payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS doc_time ON documents(published_at);
        CREATE INDEX IF NOT EXISTS doc_source ON documents(source_id);
        CREATE TABLE IF NOT EXISTS analyses (job_id TEXT PRIMARY KEY, document_version TEXT NOT NULL,
          chunk_index INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, as_of TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outcomes (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_state (id TEXT PRIMARY KEY, synced_at TEXT NOT NULL);
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def blob(self, data: bytes) -> str:
        sha = digest(data)
        path = self.data / "raw" / sha[:2] / f"{sha}.gz"
        if not path.exists():
            write(path, gzip.compress(data, mtime=0))
        return str(path.relative_to(self.data)).replace("\\", "/")

    def add(self, document: dict, raw: bytes) -> tuple[dict, bool]:
        doc = dict(document)
        public_url(doc["url"])
        date_only(doc["published_at"])
        if not doc.get("text", "").strip():
            raise ValueError("Empty source content")
        doc.setdefault("metadata", {})
        doc.setdefault("entities", [])
        doc.setdefault("topics", [])
        doc.setdefault("coverage", "full_text")
        doc.setdefault("origin", doc["source_id"])
        doc.setdefault("kind", "article")
        doc.setdefault("rights", "link_only")
        doc["document_id"] = digest(doc["source_id"] + "|" + doc.get("stable_id", doc["url"]))[:24]
        identity = {k: doc[k] for k in ["text", "title", "published_at", "coverage"]}
        identity["metadata"] = {k: v for k, v in doc["metadata"].items() if k not in {"retrieved_vintage", "vintage", "archive_sha256", "archive_record"}}
        doc["content_hash"] = digest(dumps(identity))
        doc["id"] = digest(doc["document_id"] + doc["content_hash"])[:24]
        old = self.db.execute("SELECT payload FROM documents WHERE id=?", (doc["id"],)).fetchone()
        if old:
            return json.loads(old[0]), False
        doc["first_seen_at"] = now()
        doc["raw_path"] = self.blob(raw)
        doc["raw_sha256"] = digest(raw)
        jsonfile(self.data / "normalized" / f"{doc['id']}.json", doc)
        with self.db:
            self.db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?,?)", (
                doc["id"], doc["document_id"], doc["published_at"], doc["first_seen_at"],
                doc["source_id"], doc["content_hash"], dumps(doc)))
        return doc, True

    def documents(self, as_of: str | None = None, latest_only=False):
        rows = self.db.execute("SELECT payload FROM documents ORDER BY rowid").fetchall()
        docs = [json.loads(r[0]) for r in rows]
        if as_of:
            docs = [d for d in docs if d["published_at"][:10] <= as_of]
        if latest_only:
            docs = list({d["document_id"]: d for d in docs}.values())
        return sorted(docs, key=lambda d: (d["published_at"], d["id"]))

    def save_analysis(self, job: str, doc_id: str, chunk: int, status: str, payload: dict):
        record = dict(job_id=job, document_version=doc_id, chunk_index=chunk, status=status, payload=payload, updated_at=now())
        jsonfile(self.data / "analysis" / f"{job}.json", record)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO analyses VALUES (?,?,?,?,?,?)", (
                job, doc_id, chunk, status, dumps(payload), record["updated_at"]))

    def analyses(self):
        return {r["job_id"]: {**dict(r), "payload": json.loads(r["payload"])} for r in self.db.execute("SELECT * FROM analyses")}

    def save_run(self, run: dict):
        jsonfile(self.data / "manifests" / f"{run['id']}.json", run)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO runs VALUES (?,?)", (run["id"], dumps(run)))

    def latest_run(self):
        row = self.db.execute("SELECT payload FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
        return json.loads(row[0]) if row else None

    def save_report(self, report: dict):
        jsonfile(self.data / "reports" / f"{report['id']}.json", report)
        with self.db:
            self.db.execute("INSERT INTO reports VALUES (?,?,?)", (report["id"], report["as_of"], dumps(report)))

    def reports(self):
        return [json.loads(r[0]) for r in self.db.execute("SELECT payload FROM reports ORDER BY rowid DESC")]


@contextmanager
def lock(data: Path):
    """OS lock released on crash; the lock file itself is harmless and persistent."""
    path = data / ".pipeline.lock"
    with open(path, "a+b") as f:
        f.seek(0)
        if os.name == "nt":
            import msvcrt
            f.write(b"0")
            f.flush()
            f.seek(0)
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError("Another EdgeFinance run is active") from None
        else:
            import fcntl
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError("Another EdgeFinance run is active") from None
        try:
            yield
        finally:
            if os.name == "nt":
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
