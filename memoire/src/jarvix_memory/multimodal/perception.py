"""P2.8 — Multimodal perception: raw artifact -> structured observation -> memory.

Deterministic, no LLM required. Every artifact gets a sha256 (dedup + audit),
and at least one verifiable observation (file_exists evidence is automatic).
Text-like artifacts (logs/code/JSON) are parsed for signal lines.
"""

import hashlib
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

TEXT_EXTS = {".txt", ".log", ".json", ".py", ".kt", ".md", ".xml", ".yaml", ".yml", ".sh", ".ps1", ".tsv", ".csv"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
PDF_EXTS = {".pdf"}

# Signal patterns: crash/error/OOM/perf lines in logs
SIGNAL_PATTERNS = [
    (r"(?i)\b(SIGSEGV|SIGBUS|SIGKILL|segfault)\b", "signal"),
    (r"(?i)\b(oom|out of memory|alloc failed|mmap failed)\b", "memory"),
    (r"(?i)\b(deadlock|freeze|watchdog|reboot)\b", "stability"),
    (r"(?i)(\d+\.?\d*)\s*(tok/s|tokens/s)", "throughput"),
    (r"(?i)\b(temperatur\w*|thermal)\D{0,20}(\d+\.?\d*)\s*(°C|C\b|deg)", "thermal"),
    (r"(?i)\b(error|fatal|exception|panic)\b", "error"),
    (r"(?i)\b(0x[0-9a-f]{6,})\b", "address"),
]


class PerceptionEngine:
    """Artifact -> observations. Observations become episodic/evidence memories.
    SANDBOXED: paths must be inside perception_roots (config.json) or the project cwd."""

    def __init__(self, db, allowed_roots: Optional[List[str]] = None):
        self.db = db
        # Policy: roots from caller (UI/MCP reads config), never derived from target paths.
        if allowed_roots:
            self._allowed_roots = [Path(r).resolve() for r in allowed_roots if r]
        else:
            # Default sandbox: anything under the DB's grandparent (package/project root)
            db_resolved = Path(db.db_path).resolve()
            self._allowed_roots = [db_resolved.parent.parent]

    def _check_path(self, path: str) -> Optional[str]:
        p = Path(path).resolve()
        if p.suffix in (".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3"):
            return "lecture de la base memoire interdite"
        for root in self._allowed_roots:
            try:
                p.relative_to(root)
                return None  # ok
            except ValueError:
                continue
        return (f"chemin hors sandbox perception: {p} "
                f"(racines: {[str(r) for r in self._allowed_roots]})")

    def perceive(self, path: str, note: str = None) -> Dict:
        deny = self._check_path(path)
        if deny:
            return {"error": f"sandbox: {deny}"}
        p = Path(path)
        if not p.exists() or not p.is_file():
            return {"error": f"file not found: {path}"}
        try:
            h = self._hash(p)
            meta = {
                "artifact": str(p),
                "sha256": h,
                "size": p.stat().st_size,
                "kind": self._kind(p),
                "perceived_at": datetime.utcnow().isoformat(),
            }
            if meta["kind"] == "text":
                return self._ingest_text(p, meta, note)
            return self._ingest_binary_image(p, meta, note)
        except Exception as e:
            logger.warning("perceive failed: %s", e)
            return {"error": str(e)}

    def _hash(self, p: Path) -> str:
        sha = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def _kind(self, p: Path) -> str:
        ext = p.suffix.lower()
        if ext in TEXT_EXTS:
            return "text"
        if ext in IMAGE_EXTS:
            return "image"
        if ext in PDF_EXTS:
            return "pdf"
        return "binary"

    def _signals(self, text: str) -> List[Dict]:
        out = []
        for line in text.splitlines():
            for pat, tag in SIGNAL_PATTERNS:
                m = re.search(pat, line)
                if m:
                    out.append({"tag": tag, "line": line.strip()[:240],
                                "match": m.group(0)[:60]})
                    if len(out) >= 50:
                        break
            if len(out) >= 50:
                break
        return out

    def _ingest_text(self, p: Path, meta: Dict, note: str = None) -> Dict:
        head = p.read_text(encoding="utf-8", errors="replace")[:100_000]
        signals = self._signals(head)
        top = [s["line"] for s in signals if s["tag"] in ("signal", "memory", "stability", "error")]
        summary = (top[0] if top else head.splitlines()[0][:120]) if head.strip() else "(vide)"
        obs_content = f"OBSERVATION [{meta['artifact']}]: {summary}" + (f" | note: {note}" if note else "")
        return self._store(obs_content, meta, signals)

    def _ingest_binary_image(self, p: Path, meta: Dict, note: str = None) -> Dict:
        # OCR optional: try pytesseract if installed, else reference-only observation
        try:
            import pytesseract
            from PIL import Image
            text = pytesseract.image_to_string(p)
        except Exception:
            text = None
        if text and text.strip():
            signals = self._signals(text)
            top = (signals[0]["line"] if signals else text.strip()[:120])
            obs = f"OBSERVATION [image {meta['artifact']}]: OCR {top}"
            return self._store(obs, meta, signals, ocr=True)
        obs = f"OBSERVATION [image {meta['artifact']}]: sha256={meta['sha256'][:12]}" + (f" note: {note}" if note else "")
        return self._store(obs, meta, [], ocr=False)

    def _store(self, obs_content: str, meta: Dict, signals: List[Dict], ocr: bool = None) -> Dict:
        from ..core.models import Memory
        meta["signals"] = signals
        meta["ocr"] = ocr
        epi = Memory(type="episodic", content=obs_content, confidence=0.8, source="perception",
                     metadata={k: meta[k] for k in ("artifact", "sha256", "kind", "perceived_at", "ocr")})
        self.db.insert_memory(epi)
        ev = Memory(type="evidence", content=f"ARTIFACT {meta['artifact']} sha256={meta['sha256']}",
                    confidence=1.0, source="perception", metadata={"sha256": meta["sha256"],
                    "size": meta["size"], "kind": meta["kind"]})
        self.db.insert_memory(ev)
        n_signals = len(signals)
        highest = ("none", 0.0)
        severities = {"signal": 0.9, "stability": 0.85, "memory": 0.8, "error": 0.7}
        for s in signals:
            if severities.get(s["tag"], 0) > highest[1]:
                highest = (s["tag"], severities[s["tag"]])
        return {"observation_id": epi.id,
                "evidence_id": ev.id,
                "sha256": meta["sha256"],
                "signals": n_signals,
                "top_severity": {"tag": highest[0], "conf": highest[1]} if highest[1] else None}
