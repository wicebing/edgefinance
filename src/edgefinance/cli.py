from __future__ import annotations

import argparse
import gzip
import json
import shutil
import subprocess
import sys
import traceback
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import Project, dumps, jsonfile, lock, now, readjson, write


def parser():
    p = argparse.ArgumentParser(description="EdgeFinance · 每週公開證據研究")
    p.add_argument("--root", type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest="command", required=True)
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    for name in ["weekly", "collect", "analyze", "resume", "report"]:
        cmd = sub.add_parser(name)
        cmd.add_argument("--as-of", default=today)
        if name in {"weekly", "collect"}:
            cmd.add_argument("--sources", help="Comma-separated configured source IDs")
            cmd.add_argument("--limit", type=int, help="Per-source sample limit; coverage remains explicit")
        if name in {"weekly", "analyze", "resume"}:
            cmd.add_argument("--max-jobs", type=int)
        if name in {"weekly", "report"}:
            cmd.add_argument("--no-analysis", action="store_true", help="Publish only data status; never fabricate model findings")
    build = sub.add_parser("build-site")
    build.add_argument("--from-public", action="store_true")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--mongodb", action="store_true", help="Perform a read-only connection test")
    sub.add_parser("status")
    sub.add_parser("validate")
    sub.add_parser("sync-mongodb", help="Explicitly sync compact results to the separate project database")
    sub.add_parser("rebuild-index", help="Reconstruct local indexes from retained normalized files")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8765)
    imp = sub.add_parser("import-file")
    imp.add_argument("path", type=Path)
    imp.add_argument("--url", required=True)
    imp.add_argument("--published-at", required=True)
    imp.add_argument("--source-id", default="manual")
    imp.add_argument("--kind", choices=["article", "patent", "financial", "macro"], default="article")
    bulk = sub.add_parser("import-uspto", help="Import downloaded USPTO Red Book XML or ZIP; resumable")
    bulk.add_argument("path", type=Path)
    bulk.add_argument("--source-url", default="https://data.uspto.gov/bulkdata/datasets")
    bulk.add_argument("--max-records", type=int, default=500)
    bulk.add_argument("--topic-only", action="store_true")
    outcome = sub.add_parser("record-outcome")
    outcome.add_argument("--check-id", required=True)
    outcome.add_argument("--outcome", choices=["observed", "not_observed", "inconclusive"], required=True)
    outcome.add_argument("--source-url", required=True)
    outcome.add_argument("--note", required=True)
    return p


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parser().parse_args()
    project = Project(args.root)
    try:
        if hasattr(args, "as_of"):
            datetime.strptime(args.as_of, "%Y-%m-%d")
        if args.command == "serve":
            output = project.root / project.settings["site"]["output"]
            if not (output / "index.html").exists():
                raise ValueError("Build a site first")
            handler = partial(SimpleHTTPRequestHandler, directory=str(output))
            print(f"Preview http://127.0.0.1:{args.port}", flush=True)
            ThreadingHTTPServer(("127.0.0.1", args.port), handler).serve_forever()
            return
        if args.command == "doctor":
            from .mongo import ping
            executable = shutil.which("codex")
            mode = "missing"
            if executable:
                p = subprocess.run([executable, "login", "status"], capture_output=True, timeout=30)
                mode = "chatgpt" if "ChatGPT" in (p.stdout + p.stderr).decode("utf-8", "replace") else "not_subscription"
            credentials = {key for source in project.sources for key in ([source["credential"]] if source.get("credential") else source.get("credentials", []))}
            result = {"python": sys.version.split()[0], "codex": mode, "watchlist_companies": len(project.companies),
                "topics": len(project.topics), "source_keys": {key: bool(project.secrets.get(key)) for key in sorted(credentials)},
                "atlas_configured": bool(project.secrets.get("MONGODB_URI")), "automatic_paid_api_fallback": False}
            if args.mongodb:
                result["mongodb"] = ping(project)
            print(dumps(result))
            return
        with lock(project.data):
            from .analysis import analyze
            from .collectors import collect, html_text, parse_epo
            from .report import build_report, render_site, validate_report
            if args.command in {"weekly", "collect"}:
                source_ids = args.sources.split(",") if args.sources else None
                if source_ids and not set(source_ids) <= {s["id"] for s in project.sources}:
                    raise ValueError("Unknown source IDs")
                result = collect(project, args.as_of, source_ids, limit=args.limit)
                print(dumps({k: result[k] for k in ["id", "status", "new_document_ids"]}))
            if args.command in {"weekly", "analyze", "resume"} and not getattr(args, "no_analysis", False):
                print(dumps(analyze(project, args.as_of, args.max_jobs)))
            if args.command in {"weekly", "report", "resume"}:
                report = build_report(project, args.as_of, not getattr(args, "no_analysis", False))
                print(dumps({"report_id": report["id"], "status": report["status"], "coverage": report["coverage"]}))
                print(f"Website: {render_site(project)}")
            elif args.command == "build-site":
                print(render_site(project, from_public=args.from_public))
            elif args.command in {"status", "validate"}:
                store = project.store()
                reports = store.reports()
                if args.command == "validate":
                    for report in reports:
                        validate_report(report)
                    for doc in store.documents():
                        from .core import digest
                        if digest(gzip.decompress((project.data / doc["raw_path"]).read_bytes())) != doc["raw_sha256"]:
                            raise ValueError("Raw hash mismatch")
                print(dumps({"documents": len(store.documents()), "analyses": len(store.analyses()), "reports": len(reports),
                    "latest_report": reports[0]["id"] if reports else None, "validation": "passed" if args.command == "validate" else "not_requested"}))
                store.close()
            elif args.command == "sync-mongodb":
                from .mongo import sync
                print(dumps(sync(project)))
            elif args.command == "import-uspto":
                from .uspto import import_bulk
                print(dumps(import_bulk(project, args.path, args.source_url, args.max_records, args.topic_only, as_of=now()[:10])))
            elif args.command == "import-file":
                raw = args.path.read_bytes()
                if len(raw) > project.settings["collection"]["max_response_mb"] * 1024 * 1024:
                    raise ValueError("Import exceeds configured byte limit")
                if args.path.suffix.lower() == ".xml" and args.kind == "patent":
                    doc = parse_epo(raw, args.url, args.published_at)
                elif args.path.suffix.lower() == ".json":
                    value = json.loads(raw)
                    doc = {"title": value.get("title", args.path.stem), "text": value.get("text", dumps(value)), "metadata": value.get("metadata", {})}
                else:
                    title, text = html_text(raw)
                    doc = {"title": title, "text": text}
                doc.update(url=args.url, published_at=args.published_at, source_id=args.source_id, kind=args.kind,
                    topics=project.topic_ids(doc["text"]), coverage="imported_text")
                store = project.store()
                saved, new = store.add(doc, raw)
                store.close()
                print(dumps({"id": saved["id"], "new": new}))
            elif args.command == "rebuild-index":
                store = project.store()
                count = 0
                for path in (project.data / "normalized").glob("*.json"):
                    doc = readjson(path)
                    raw = gzip.decompress((project.data / doc["raw_path"]).read_bytes())
                    from .core import digest
                    if digest(raw) != doc["raw_sha256"]:
                        raise ValueError("Raw hash mismatch during recovery")
                    with store.db:
                        store.db.execute("INSERT OR IGNORE INTO documents VALUES (?,?,?,?,?,?,?)", (doc["id"], doc["document_id"],
                            doc["published_at"], doc["first_seen_at"], doc["source_id"], doc["content_hash"], dumps(doc)))
                    count += 1
                for path in (project.data / "analysis").glob("*.json"):
                    r = readjson(path)
                    with store.db:
                        store.db.execute("INSERT OR REPLACE INTO analyses VALUES (?,?,?,?,?,?)", (r["job_id"], r["document_version"], r["chunk_index"], r["status"], dumps(r["payload"]), r["updated_at"]))
                for table, folder in [("runs", "manifests"), ("reports", "reports"), ("outcomes", "outcomes")]:
                    for path in sorted((project.data / folder).glob("*.json"), key=lambda p: p.stat().st_mtime):
                        r = readjson(path)
                        with store.db:
                            if table == "reports":
                                store.db.execute("INSERT OR IGNORE INTO reports VALUES (?,?,?)", (r["id"], r["as_of"], dumps(r)))
                            else:
                                store.db.execute(f"INSERT OR IGNORE INTO {table} VALUES (?,?)", (r["id"], dumps(r)))
                store.close()
                print(dumps({"status": "rebuilt", "documents": count}))
            elif args.command == "record-outcome":
                from .core import public_url
                store = project.store()
                check = next((c for r in store.reports() for c in r["checks"] if c["id"] == args.check_id), None)
                if not check or check["due_at"] > now()[:10]:
                    raise ValueError("Check does not exist or is not due yet")
                result = {"id": args.check_id, "outcome": args.outcome, "source_url": public_url(args.source_url), "note": args.note, "evaluated_at": now()}
                if store.db.execute("SELECT 1 FROM outcomes WHERE id=?", (args.check_id,)).fetchone():
                    raise ValueError("Outcome already recorded; retain history instead of overwriting")
                jsonfile(project.data / "outcomes" / f"{args.check_id}.json", result)
                with store.db:
                    store.db.execute("INSERT INTO outcomes VALUES (?,?)", (args.check_id, dumps(result)))
                store.close()
                print(dumps(result))
    except KeyboardInterrupt:
        print("Interrupted. Completed documents and analyses are retained; use resume.")
        sys.exit(130)
    except Exception as e:
        write(project.data / "last-error.log", traceback.format_exc())
        if isinstance(e, RuntimeError) and str(e) == "Another EdgeFinance run is active":
            print("Another EdgeFinance run is active. Wait for it to finish before starting another pipeline command.", file=sys.stderr)
            sys.exit(1)
        print(f"{type(e).__name__}: operation failed. Details remain in data/last-error.log; credentials are never printed.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
