from __future__ import annotations

from urllib.parse import urlsplit

from pymongo import MongoClient

from .core import Project, dumps, now


def client(project: Project):
    uri = project.secrets.get("MONGODB_URI") or ""
    if not uri.startswith(("mongodb://", "mongodb+srv://")) or any(x in uri for x in ["<", ">", "replace_with_"]):
        raise ValueError("Configure MONGODB_URI in atlas-credentials.env")
    kwargs = {"serverSelectionTimeoutMS": 10000, "connectTimeoutMS": 10000, "appname": "EdgeFinance-MVP"}
    if not urlsplit(uri).username:
        if project.secrets.get("MONGODB_USERNAME"):
            kwargs.update(username=project.secrets["MONGODB_USERNAME"], password=project.secrets.get("MONGODB_PASSWORD"))
    return MongoClient(uri, **kwargs)


def ping(project: Project):
    try:
        with client(project) as conn:
            conn.admin.command("ping")
        return {"status": "connected", "operation": "read-only ping", "tier": "not_verified"}
    except Exception as e:
        return {"status": "unavailable", "reason": type(e).__name__, "detail": "Check local credentials, database user permissions and Atlas network access; URI is not logged"}


def sync(project: Project):
    """Single-writer local authority; safe to repeat after an interrupted remote write."""
    store = project.store()
    database = project.settings["mongodb"]["database"]
    if database in {"admin", "local", "config", "webNews"}:
        raise ValueError("Use a separate project database")
    count = 0
    try:
        with client(project) as conn:
            conn.admin.command("ping")
            db = conn[database]
            for report in reversed(store.reports()):
                records = [("report_versions", {k: report[k] for k in ["id", "as_of", "status", "summary", "coverage"]})]
                records += [("thesis_versions", {**t, "id": report["id"] + ":" + t["id"], "report_id": report["id"]}) for t in report["theses"]]
                records += [("evidence", e) for e in report["evidence"]]
                for collection, record in records:
                    key = collection + ":" + record["id"]
                    if store.db.execute("SELECT 1 FROM sync_state WHERE id=?", (key,)).fetchone():
                        continue
                    if count >= project.settings["mongodb"]["max_documents"]:
                        return {"status": "partial", "synced": count, "reason": "Configured record budget reached"}
                    if len(dumps(record).encode()) > 128000:
                        raise ValueError("Sync record exceeds 128 KB budget")
                    db[collection].replace_one({"_id": record["id"]}, {"_id": record["id"], **record}, upsert=True)
                    with store.db:
                        store.db.execute("INSERT OR REPLACE INTO sync_state VALUES (?,?)", (key, now()))
                    count += 1
        return {"status": "complete", "synced": count}
    except Exception as e:
        return {"status": "partial", "synced": count, "reason": type(e).__name__}
    finally:
        store.close()
