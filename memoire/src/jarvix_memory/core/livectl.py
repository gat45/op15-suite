"""Real-time context server — "what the dev needs NOW", indexed & pushed live.

bundle(query)   -> one payload: fresh inventories + facts + hypotheses + recoveries
start_watch()   -> daemon: periodic re-ingest of config scan_dirs + autopush
Deterministic, no LLM. Exports go to the PRIVATE data repo.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

FRESH_HOURS = 26  # what counts as "current" in the live feed


class LiveContext:
    def __init__(self, db, autolog_dir: str = None, config_path: str = None):
        self.db = db
        self.autolog_dir = autolog_dir
        self.watch_thread: Optional[threading.Thread] = None
        self._stop = False
        self.last_push: Dict = {}
        cfg = {}
        if config_path and Path(config_path).exists():
            try:
                cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
            except Exception:
                pass
        self._cfg = cfg
        self._config_path = config_path

    # ── bundle builders (deterministic) ────────────────────

    def _fresh_semantics(self, query: str, limit: int = 5) -> List[Dict]:
        rows = self.db.search_hybrid(query, limit=limit * 3)
        cutoff = (datetime.utcnow() - timedelta(hours=FRESH_HOURS)).isoformat()
        return [m for m in rows if (m.get("created_at") or "") > cutoff][:limit]

    def bundle(self, query: str = "", max_tokens: int = 4000) -> Dict:
        """Everything an LLM needs to work the project NOW — one payload."""
        buf: Dict = {"items": []}
        est = 0

        def add(kind, item, token_est=40):
            nonlocal est
            if est + token_est > max_tokens:
                return False
            buf["items"].append({"kind": kind, **item})
            est += token_est
            return True

        # 1. inventory summaries (the disk index)
        conn = self.db._connect()
        inv = conn.execute(
            "SELECT content, metadata FROM memories WHERE type='semantic' "
            "AND content LIKE 'PROJET INVENTAIRE %' ORDER BY created_at DESC LIMIT 8"
        ).fetchall()
        for content, meta in inv:
            m = json.loads(meta or "{}")
            add("inventory", {"root": m.get("ingest_root"), "files": m.get("files"),
                              "summary": (content or "")[:400]}, 90)
        # 2. fresh semantic facts matching the query
        for m in self._fresh_semantics(query, limit=4):
            add("fact", {"content": (m.get("content") or "")[:400],
                         "conf": m.get("confidence")}, 60)
        # 3. open hypotheses (never re-test refuted paths)
        for h in self.db.search_by_type("hypothesis", limit=8):
            meta = json.loads(h.get("metadata", "{}"))
            add("hypothesis", {"id": h["id"][:8],
                               "status": meta.get("h_status", "PROPOSED"),
                               "content": (h.get("content") or "")[:200]}, 40)
        # 4. active recoveries
        for rcv in self.db.search_by_type("recovery", limit=6):
            meta = json.loads(rcv.get("metadata", "{}"))
            if meta.get("status") in ("failed", "retrying", "diagnosed"):
                add("recovery", {"content": (rcv.get("content") or "")[:150],
                                 "attempt": meta.get("attempt")}, 40)
        buf["estimated_tokens"] = est
        buf["ts"] = datetime.utcnow().isoformat()
        buf["status"] = "OK_RELIABLE" if buf["items"] else "NO_RELIABLE_MEMORY"
        return buf

    # ── realtime watcher ───────────────────────────────────

    def _resolve_scan_dirs(self) -> List[str]:
        return self._cfg.get("scan_dirs", []) \
            if self._cfg else self.__load_cfg().get("scan_dirs", [])

    def __load_cfg(self) -> Dict:
        try:
            cp = Path(self._config_path or
                      Path(__file__).resolve().parents[3] / "config.json")
            self._cfg = json.loads(cp.read_text(encoding="utf-8"))
            return self._cfg
        except Exception:
            return {}

    def interval_s(self) -> int:
        try:
            return int(self.__load_cfg().get("live_interval_min", 30)) * 60
        except Exception:
            return 1800

    def _watcher_once(self):
        from .ingest import ingest_directory
        for root in self._resolve_scan_dirs():
            try:
                res = ingest_directory(self.db, root, note="live-watcher",
                                       max_files=200000)
                self._check_inventory_drift(root, res)
            except Exception as e:
                logger.warning("live ingest failed %s: %s", root, e)
        try:
            from .autopush import push_project, autolog_dir
            push_project(self.db,
                         self.autolog_dir or str(autolog_dir()),
                         project_id=self._cfg.get("live_project", "live"),
                         message=f"live: index mis a jour {datetime.now().strftime('%H:%M')}",
                         confirm=True)
        except Exception as e:
            logger.warning("live push failed: %s", e)

    def _check_inventory_drift(self, root: str, delta_threshold: float = 0.10):
        """Real-time change detection: if latest inventory differs by >10% files
        from the previous scan of the SAME root, register a drift hypothesis."""
        conn = self.db._connect()
        rows = conn.execute(
            "SELECT content, metadata FROM memories WHERE type='semantic' "
            "AND content LIKE ? ORDER BY created_at DESC LIMIT 2",
            (f"PROJET INVENTAIRE {root}",)).fetchall()
        if len(rows) < 2:
            return
        new_meta = json.loads(rows[0][1] or "{}")
        old_meta = json.loads(rows[1][1] or "{}")
        new_files, old_files = new_meta.get("files", 0), old_meta.get("files", 0)
        if not old_files:
            return
        delta = (new_files - old_files) / old_files
        if abs(delta) < delta_threshold:
            return
        tag = f"DRIFT {root} {round(delta, 2)}%"
        dup = conn.execute(
            "SELECT id FROM memories WHERE type='hypothesis' AND content=? LIMIT 1",
            (tag,)).fetchone()
        if dup:
            return
        from ..core.models import Memory
        self.db.insert_memory(Memory(
            type="hypothesis",
            content=tag,
            confidence=0.9,
            source="live-watcher",
            metadata={"h_status": "PROPOSED", "kind": "inventory_drift",
                      "old_files": old_files, "new_files": new_files,
                      "root": root,
                      "detected_at": datetime.utcnow().isoformat()}))
        logger.info("inventory drift: %s (%.0f%%)", root, delta * 100)

    def start_watch(self) -> bool:
        if self.watch_thread and self.watch_thread.is_alive():
            return False
        self._stop = False

        def _loop():
            self._watcher_once()
            while not self._stop:
                for _ in range(self.interval_s()):
                    if self._stop:
                        return
                    threading.Event().wait(1)
                self._watcher_once()

        self.watch_thread = threading.Thread(target=_loop, daemon=True,
                                             name="jarvix-live-watcher")
        self.watch_thread.start()
        logger.info("live watcher started (par cycle %d min)", self.interval_s() // 60)
        return True

    def stop_watch(self) -> bool:
        was = bool(self.watch_thread and self.watch_thread.is_alive())
        self._stop = True
        return was
