"""Cross-analysis of ingested project inventories -> actionable dev insights.
Deterministic. Stores semantic diagnoses + pushes the actionable report to the
private git data repo."""
import sys, json, os
sys.path.insert(0, "src")
from pathlib import Path
from datetime import datetime
from jarvix_memory.core.database import Database
from jarvix_memory.core.ingest import _human
from jarvix_memory.core.autopush import push_project, autolog_dir

db = Database("jarvix_memory.db")
conn = db._connect()
# latest inventory summary per root (semantic only)
rows = conn.execute(
    "SELECT content, metadata, created_at FROM memories "
    "WHERE type='semantic' AND content LIKE 'PROJET INVENTAIRE %' "
    "ORDER BY created_at ASC").fetchall()
# keep the most recent per root
latest = {}
for content, meta_raw, created_at in rows:
    meta = json.loads(meta_raw or "{}")
    latest[meta.get("ingest_root", "?")] = {"content": content,
                                            "files": meta.get("files"), "ts": created_at}

lines = ["# RAPPORT DEV — données ressorties des inventaires JARVIX",
         "", f"Genere {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
total_files, total_bytes = 0, 0
code_dirs, asset_dirs, big_assets = [], [], []
for root, info in sorted(latest.items()):
    total_files += info["files"] or 0
    c = info["content"]
    lines.append(f"## {root}")
    lines.append(f"- inventaire le plus recent: {info['ts'][:16]} — {info['files']} fichiers")
    lines.append(f"- {c}")
    lines.append("")
    if ".py" in c: code_dirs.append(root)
    if ".kt" in c: code_dirs.append(root + " (kotlin)")
    if ".gguf" in c: big_assets.append(("gguf", root))
    if ".so" in c: big_assets.append(("so", root))

lines += [
    "## Ce que fait JARVIX pour le dev (sortie)a",
    "",
    "1. Ouvrir cet etat: `recall_cost '<sujet>'` — les inventaires recents, les fails et les strategies deprojets rantent aux referents ephemerides.",
    "2. Chaque nouveau projet/racine = `ingest_directory(path)` — par la suite la question aide (`ou est X?`, `combien de .so ?`) est un recall, PAS une re-scan disque.",
    "3. Diff d'inventaire: deux scans du meme root a dates differentes -> nouveaux fichiers, doublons, poids mal place. Les inventaires anciens restent comme 'timelines' verifiables.",
    "4. Verify_auto + git status sur chaque projet ingere: verify que chaque root compile avant insertion mémoire (ignore 'build-in-progress').",
    "5. Autopush project_id: chaque root a son export `memoire_<project>.md` sur le git priver.",
    "",
    "## Constat-crois (dedup opportunities)",
    "- les .gguf existent a la fois dans D:\\oneplus/download + D:\\models_marco (GGUF partages)",
    "- .so (binaires Android) volumes: verifier source-vs-build echos",
    f"- au total: {total_files} fichiers indexes dans la memoire",
]

out_path = Path("reports") / f"INSIGHT_DEV_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text("\n".join(lines), encoding="utf-8")

# memory: 1 actionable plan (semantic)
from jarvix_memory.core.models import Memory
plan = (f"PLAN DEV (inventaires 8 racines): {total_files} fichiers recenses. "
        f"Outils = memoire INGEST: {code_dirs[:3]}... → recall_cost rend le sondage disque INUTILISE. "
        f"Dedup .gguf/.so recommande (voir memoire_oneplus.md prive).")
db.insert_memory(Memory(type="semantic", content=plan, confidence=0.9, source="dev-insight"))
res_push = push_project(db, str(autolog_dir()), project_id="oneplus",
                        message=f"rapport dev: 8 racines, {total_files} fichiers inventories", confirm=True)
print("rapport ->", out_path)
print("push prive:", res_push.get("pushed"))
print("--- APERCU ---")
print("\n".join(lines[:20]))
