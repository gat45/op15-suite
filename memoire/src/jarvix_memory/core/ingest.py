"""Deterministic directory ingestion — filesystem facts become queryable memories.

Each directory gets: 1 semantic summary (type counts, total size, stamp) +
1 episodic ingest event. Auto-embedded on insert. Roots added at runtime
(JARVIX_SCAN_DIRS) or from config.json "scan_dirs" — nothing hardcoded.
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

NOTABLE_EXTS = {".py", ".md", ".mdx", ".txt", ".json", ".yml", ".yaml", ".sh",
                ".ps1", ".bat", ".kt", ".java", ".log", ".gguf", ".so", ".cpp",
                ".h", ".c", ".ts", ".rs", ".toml", ".csv", ".prof", ".cfg"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "build", "out",
             ".idea", ".vscode", ".cache", ".gradle", ".kotlin", "downloads"}
MAX_FILES_PER_DIR = 5000


def _human(n: int) -> str:
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def scan_directory(root: str, max_files: int = MAX_FILES_PER_DIR,
                   max_depth: int = 4) -> Optional[Dict]:
    """Scan a real directory (bounded). Returns summary dict or None."""
    r = Path(root)
    if not r.exists() or not r.is_dir():
        return {"error": f"repertoire introuvable: {root}"}
    counts: Dict[str, int] = {}
    sizes: Dict[str, int] = {}
    total_files, total_size, skipped = 0, 0, 0
    subdirs: List[str] = []
    n_seen = 0
    for dirpath, dirnames, filenames in os.walk(r):
        rel_depth = len(Path(dirpath).resolve().relative_to(r.resolve()).parts)
        if rel_depth >= max_depth:
            dirnames[:] = []  # os.walk prune
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if dirnames and rel_depth <= 1:
            subdirs.extend(dirnames[:12])
        for fn in filenames:
            n_seen += 1
            if n_seen > max_files:
                skipped += 1
                continue
            ext = Path(fn).suffix.lower() or "(sans-ext)"
            total_files += 1
            counts[ext] = counts.get(ext, 0) + 1
            try:
                sz = Path(dirpath, fn).stat().st_size
                total_size += sz
                sizes[ext] = sizes.get(ext, 0) + sz
            except OSError:
                pass
    return {"path": str(r), "total_files": total_files, "total_size": total_size,
            "counts": counts, "sizes": sizes, "subdirs": sorted(subdirs)[:12],
            "skipped_due_to_cap": skipped, "scanned_at": datetime.utcnow().isoformat()}


def ingest_directory(db, root: str, note: str = None,
                      max_files: int = MAX_FILES_PER_DIR) -> Dict:
    """Scan + create memories. Returns ids + stats."""
    from ..core.models import Memory
    info = scan_directory(root, max_files=max_files)
    if "error" in info:
        return info
    top_ext = sorted(info["counts"].items(), key=lambda x: -x[1])[:8]
    top_size_ext = sorted(info["sizes"].items(), key=lambda x: -x[1])[:5]
    summary = (
        f"PROJET INVENTAIRE {info['path']}: {info['total_files']} fichiers, "
        f"{_human(info['total_size'])} ; principaux types: "
        + ", ".join(f"{e} x{c}" for e, c in top_ext)
        + " ; plus lourds: " + ", ".join(f"{e} {_human(sz)}" for e, sz in top_size_ext)
        + (f" ; sous-dossiers: {', '.join(info['subdirs'][:8])}" if info["subdirs"] else "")
        + (f" ; note: {note}" if note else "")
    )
    sem = Memory(type="semantic", content=summary, confidence=0.9,
                 source="ingest", metadata={"ingest_root": info["path"],
                                            "files": info["total_files"]})
    db.insert_memory(sem)
    epi = Memory(type="episodic",
                 content=f"INGEST {info['path']} -> {info['total_files']} fichiers indexes ({info['scanned_at']})",
                 confidence=1.0, source="ingest")
    db.insert_memory(epi)
    return {"semantic_id": sem.id, "episodic_id": epi.id, "summary": summary,
            "files": info["total_files"], "size": info["total_size"],
            "skipped": info["skipped_due_to_cap"]}


def get_scan_roots(config_path: Path = None, env_prefix: str = "JARVIX_SCAN_DIRS") -> List[str]:
    roots: List[str] = []
    env = os.environ.get(env_prefix)
    if env:
        roots += [x for x in env.split(os.pathsep) if x.strip()]
    if config_path and Path(config_path).exists():
        try:
            roots += json.loads(config_path.read_text(encoding="utf-8")).get("scan_dirs", [])
        except Exception:
            pass
    return roots
