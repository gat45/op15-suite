from ..core.database import Database
from ..core.models import Memory
import sqlite3
import json
import uuid
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ConsolidationService:
    def __init__(self, db: Database):
        self.db = db
        self._scheduler_thread = None
        self._stop = False

    def start_scheduler(self, interval_hours: float = 6.0):
        """Run sleep cycles automatically every interval_hours (daemon).
        First cycle after ~1 minute of startup, then periodic."""
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return False
        import threading, time as _time

        def _loop():
            # small delay so servers boot before the first cycle
            _time.sleep(60)
            self.run_sleep_cycle()
            while not self._stop:
                _time.sleep(interval_hours * 3600)
                if self._stop:
                    break
                self.run_sleep_cycle()

        self._scheduler_thread = threading.Thread(
            target=_loop, daemon=True, name="jarvix-consolidation")
        self._scheduler_thread.start()
        logger.info("Consolidation scheduler started (every %.1fh)", interval_hours)
        return True

    def stop_scheduler(self):
        self._stop = True

    def decay_importance(self, decay_factor: float = 0.95, min_importance: float = 0.1):
        conn = self.db._connect()
        conn.execute("""
            UPDATE memories
            SET importance = MAX(importance * ?, ?)
            WHERE importance > ?
        """, (decay_factor, min_importance, min_importance))
        conn.commit()

    def merge_episodic_to_semantic(self, min_repeat: int = 3):
        conn = self.db._connect()
        conn.row_factory = sqlite3.Row
        episodic = conn.execute(
            "SELECT content, COUNT(*) as cnt FROM memories "
            "WHERE type = 'episodic' GROUP BY content HAVING cnt >= ?",
            (min_repeat,)
        ).fetchall()
        merged = 0
        for row in episodic:
            existing = conn.execute(
                "SELECT id FROM memories WHERE type = 'semantic' AND content = ?",
                (row["content"],)
            ).fetchone()
            if not existing:
                mem = Memory(
                    type="semantic",
                    content=row["content"],
                    status="verified",
                    confidence=0.8,
                    importance=0.7,
                    source="consolidation",
                    metadata={"merged_from": "episodic", "repeat_count": row["cnt"]},
                )
                self.db.insert_memory(mem)
                merged += 1
        if merged:
            logger.info("Merged %d episodic memories into semantic", merged)

    def archive_old_provisional(self, max_age_days: int = 30):
        conn = self.db._connect()
        conn.execute("SAVEPOINT sp_archive")
        try:
            rows = conn.execute(
                "SELECT id FROM memories WHERE status = 'provisional' "
                "AND datetime(created_at) < datetime('now', ? || ' days')",
                (f'-{max_age_days}',)
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE memories SET status = 'archived' WHERE id = ?",
                    (row[0],)
                )
                self._fts_sync_status(conn, row[0], "archived")
            conn.execute("RELEASE sp_archive")
            if rows:
                logger.info("Archived %d old provisional memories", len(rows))
        except Exception:
            conn.execute("ROLLBACK TO sp_archive")
            raise

    def _fts_sync_status(self, conn: sqlite3.Connection, memory_id: str, new_status: str):
        # FTS was replaced by LIKE search — status change needs no index sync
        pass

    def archive_stale_actions(self, max_age_hours: int = 72,
                              max_utility: float = 0.2) -> int:
        """Blur-spot fix: actions 'provisional' jamais approuvees/executed vieillissent
        et se font ARCHIVER (sinon la pile d'actions devient un junk-heap)."""
        conn = self.db._connect()
        conn.execute("SAVEPOINT sp_act")
        try:
            rows = conn.execute(
                "SELECT id FROM memories WHERE type = 'action' AND status = 'provisional' "
                "AND datetime(created_at) < datetime('now', '-' || ? || ' hours') "
                "AND utility < ?",
                (int(max_age_hours), max_utility)).fetchall()
            for row in rows:
                conn.execute("UPDATE memories SET status = 'archived' WHERE id = ?", (row[0],))
            conn.execute("RELEASE sp_act")
            # Mirror in recovery realm: stale failed actions too
            n = len(rows)
            if n:
                logger.info("Auto-archived %d stale provisional actions (> %dh, utility<%.2f)", n, max_age_hours, max_utility)
            return n
        except Exception:
            conn.execute("ROLLBACK TO sp_act")
            raise

    def run_sleep_cycle(self):
        logger.info("Starting consolidation sleep cycle")
        self.decay_importance()
        self.merge_episodic_to_semantic()
        self.archive_old_provisional()
        self.archive_stale_actions()

    def stats(self) -> dict:
        conn = self.db._connect()
        rows = conn.execute(
            "SELECT type, status, COUNT(*) as cnt FROM memories GROUP BY type, status"
        ).fetchall()
        # clés stringifiées : json.dumps (MCP) refuse les clés tuple
        return {f"{r[0]}/{r[1]}": r[2] for r in rows}
