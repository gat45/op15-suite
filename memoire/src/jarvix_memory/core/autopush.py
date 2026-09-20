"""P-final — Git autopilot: export memories grouped by project_id and push to GitHub.

The project commits its own knowledge: a markdown export per project_id is
written into the repo (docs/memory/), committed and pushed. Fully deterministic,
no LLM. Private data (the SQLite DB itself) never leaves the machine — only
the exported markdown.
"""

import json
import re
import subprocess
import logging
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

EXPORT_DIR = "docs"  # relative to repo root


def autolog_dir(config_path: Path = None) -> Path:
    """Data repo dir from config.json (key 'autolog_dir'); default = package dir (source repo)."""
    cfg_path = config_path or Path(__file__).resolve().parents[3] / "config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        d = cfg.get("autolog_dir")
        if d and Path(d).exists():
            return Path(d)
    except Exception:
        pass
    return Path(__file__).resolve().parents[3]


def _safe_project(name: Optional[str]) -> str:
    if not name:
        return "default"
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()) or "default"


def _short(content: str, n: int = 400) -> str:
    c = (content or "").strip()
    return c if len(c) <= n else c[:n] + "…"


def export_project(db, repo_path: str, project_id: Optional[str] = None) -> Dict:
    """Export memories (optionally scoped by project_id and cross-agent scope)
    to docs/memoire_<project>.md and return the file path + counts."""
    conn = db._connect()
    if project_id:
        rows = conn.execute(
            "SELECT * FROM memories WHERE project_id = ? OR project_id IS NULL ORDER BY type, created_at",
            (project_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY type, created_at").fetchall()
    memories: List[Dict] = [dict(r) for r in rows]

    # Group by type -> sections
    by_type: Dict[str, List[Dict]] = {}
    for m in memories:
        by_type.setdefault(m["type"] or "unknown", []).append(m)

    slug = _safe_project(project_id)
    out_path = Path(repo_path) / EXPORT_DIR / f"memoire_{slug}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Mémoire exportée — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Projet : `{slug}` · {len(memories)} souvenirs · générée par JARVIX autopilot",
        "",
    ]
    for t in sorted(by_type):
        section = by_type[t]
        lines.append(f"## {t} ({len(section)})")
        lines.append("")
        for m in section[:80]:
            content = _short(m.get("content", ""))
            conf = m.get("confidence", 1.0)
            status = m.get("status", "")
            lines.append(f"- [{status}|conf={conf}] {content}")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return {"export_path": str(out_path), "memories": len(memories),
            "types": {t: len(v) for t, v in by_type.items()}}


def push_project(db, repo_path: str, remote: str = "origin", branch: str = "main",
                 project_id: Optional[str] = None, model=None,
                 message: Optional[str] = None, confirm: bool = False) -> Dict:
    """Export + git commit + push. Policy in code: push requires confirm=True
    (MCP agents get dry_run showing what WOULD be committed). Trust chain:
    local export file -> remote repo."""
    info = export_project(db, repo_path, project_id)
    if not confirm:
        return {**info, "pushed": False, "dry_run": True,
                "reason": "confirm=True requis pour commit+push (politique autopilot)"}
    slug = _safe_project(project_id)

    def run(cmd: List[str]) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=repo_path)

    status = run(["git", "status", "--porcelain", "--", f"{EXPORT_DIR}/"])
    if not status.stdout.strip():
        return {**info, "pushed": False, "reason": "nothing new to commit"}

    commit_msg = message or (
        f"autopilot: mémoire exportée ({slug}) — "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    a = run(["git", "add", EXPORT_DIR])
    if a.returncode != 0:
        return {**info, "pushed": False, "error": a.stderr}
    c = run(["git", "commit", "-m", commit_msg])
    if c.returncode != 0:
        return {**info, "pushed": False, "error": c.stderr}
    p = run(["git", "push", remote, branch])
    if p.returncode != 0:
        return {**info, "pushed": False, "error": p.stderr, "note": "commit local créé mais push a échoué"}
    return {**info, "pushed": True, "commit": c.stdout.strip().splitlines()[-1] if c.stdout else commit_msg}
