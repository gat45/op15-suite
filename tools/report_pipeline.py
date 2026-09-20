"""Pipeline autonome de gestion des rapports : RAG + UPIA + JARVIX en une commande.

Usage:
    py -3.12 tools/report_pipeline.py <rapport.md> [--upia-init] [--skip-rag] [--skip-upia] [--skip-jarvix]

Ce que fait le pipeline pour UN rapport :
  1. RAG     : ingere le dossier du rapport dans le RAG op15-forensics
               (run.py --learn --local .. , dedup SHA-256 integree).
  2. UPIA    : ingestion du projet D:\\oneplus (init au 1er passage, update ensuite,
               idempotent) en tache DETACHEE (log : reports/upia_ingest.log).
  3. JARVIX  : ajoute un souvenir semantic dense (verdicts + source=fichier) et
               un evenement episodique.

Convention rapports (AGENTS.md, REFLEXE N5) : tout rapport .md de session/verdict
passe par ce pipeline immediatement apres ecriture.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent          # D:\oneplus
HARNESS = Path(r"E:\oneplus\geniex_harness")
RAG_DIR = PROJECT / "op15-forensics"
MEMOIRE_DB = PROJECT / "memoire" / "jarvix_memory.db"
UPIA_LOG = PROJECT / "reports" / "upia_ingest.log"
UPIA_STORE_KEY = "D_oneplus"
UPIA_DEFAULT_STORE = Path.home() / ".upia" / "store" / UPIA_STORE_KEY


def ingest_rag(report: Path) -> str:
    cmd = [sys.executable, "run.py", "--learn", "--local", str(PROJECT)]
    p = subprocess.run(cmd, cwd=RAG_DIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=300)
    tail = (p.stdout or p.stderr or "").strip().splitlines()
    return " | ".join(tail[-3:]) if tail else "(RAG: aucune sortie)"


def launch_upia(update_only: bool) -> str:
    UPIA_LOG.parent.mkdir(exist_ok=True)
    sub = "update" if update_only else "init"
    args = ["--commits", "50"] if sub == "init" else []
    cmd = [sys.executable, "-m", "governor.upia.upia.cli", sub,
           str(PROJECT), *args]
    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
    DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    with open(UPIA_LOG, "ab") as log:
        subprocess.Popen(cmd, cwd=str(HARNESS), env=env, stdout=log, stderr=log,
                         stdin=subprocess.DEVNULL, creationflags=DETACHED,
                         close_fds=True)
    mode = "update (incremental)" if update_only else "init (1er passage)"
    return f"UPIA {mode} lance en tache detachee -> {UPIA_LOG.name}"


def ingest_jarvix(report: Path) -> str:
    sys.path.insert(0, str(PROJECT / "memoire" / "src"))
    from jarvix_memory.router import MemoryRouter
    from jarvix_memory.core.models import Memory

    text = report.read_text(encoding="utf-8", errors="replace")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = next((l.lstrip("# ") for l in lines if l.startswith("# ")), report.stem)
    verdicts = [l for l in lines if l.startswith("- **") or l.startswith("## Verdict")][:12]
    summary = (title + "\n" + "\n".join(verdicts))[:1400]

    r = MemoryRouter(db_path=str(MEMOIRE_DB))
    r.db.insert_memory(Memory(type="semantic", content=summary, confidence=0.9,
                              source=str(report.relative_to(PROJECT))))
    r.db.insert_memory(Memory(type="episodic",
                              content=f"Action: rapport pipeline (RAG+UPIA+JARVIX)\nResult: {report.name} ingere",
                              confidence=1.0, source="tools/report_pipeline.py"))
    import sqlite3
    db = sqlite3.connect(str(MEMOIRE_DB))
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    n = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    return f"JARVIX OK (total {n} souvenirs)"


def main() -> int:
    ap = argparse.ArgumentParser(description="Pipeline rapports : RAG + UPIA + JARVIX")
    ap.add_argument("report", help="chemin du rapport .md")
    ap.add_argument("--upia-init", action="store_true",
                    help="force upia init (1er passage) au lieu d'update")
    ap.add_argument("--skip-rag", action="store_true")
    ap.add_argument("--skip-upia", action="store_true")
    ap.add_argument("--skip-jarvix", action="store_true")
    args = ap.parse_args()

    report = Path(args.report)
    if not report.is_absolute():
        report = PROJECT / report
    if not report.exists():
        print(f"ERREUR: rapport introuvable: {report}")
        return 2

    print(f"[{datetime.now():%H:%M:%S}] pipeline -> {report.name}")
    results = {}
    if not args.skip_rag:
        try:
            results["RAG"] = ingest_rag(report)
        except Exception as e:
            results["RAG"] = f"ERREUR: {e}"
        print("  RAG    :", results["RAG"])
    if not args.skip_upia:
        try:
            update_only = (not args.upia_init) and UPIA_DEFAULT_STORE.exists()
            results["UPIA"] = launch_upia(update_only)
        except Exception as e:
            results["UPIA"] = f"ERREUR: {e}"
        print("  UPIA   :", results["UPIA"])
    if not args.skip_jarvix:
        try:
            results["JARVIX"] = ingest_jarvix(report)
        except Exception as e:
            results["JARVIX"] = f"ERREUR: {e}"
        print("  JARVIX :", results["JARVIX"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
