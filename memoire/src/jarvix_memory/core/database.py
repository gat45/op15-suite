import sqlite3
import json
import logging
import threading
from typing import List, Dict, Optional
from .models import Memory
from .migration import run_migrations

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = "jarvix_memory.db", skip_vector: bool = False):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
        # Auto-migrate schema
        conn = self._connect()
        self.schema_version = run_migrations(conn)
        logger.info("DB schema version: %d", self.schema_version)
        # Vector store (lazy import — model loads on first use)
        self.vector = None
        if not skip_vector:
            try:
                from .vector_store import VectorStore
                self.vector = VectorStore(self)
            except Exception as e:
                logger.info("Vector search disabled (%s)", e)

    def _connect(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA cache_size=-64000")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def _init_db(self):
        conn = self._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                type TEXT,
                status TEXT DEFAULT 'provisional',
                content TEXT,
                source TEXT,
                source_trust REAL DEFAULT 1.0,
                project_id TEXT,
                agent_id TEXT,
                session_id TEXT,
                environment_id TEXT,
                created_at TEXT,
                observed_at TEXT,
                valid_from TEXT,
                valid_until TEXT,
                confidence REAL DEFAULT 1.0,
                importance REAL DEFAULT 0.5,
                utility REAL DEFAULT 0.0,
                provenance_chain TEXT DEFAULT '[]',
                cost_ram REAL DEFAULT 0.0,
                cost_cpu REAL DEFAULT 0.0,
                cost_tokens INTEGER DEFAULT 0,
                cost_storage_kb REAL DEFAULT 0.0,
                metadata TEXT DEFAULT '{}',
                relations TEXT DEFAULT '[]'
            );

            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
            CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
            CREATE INDEX IF NOT EXISTS idx_memories_type_status ON memories(type, status);

            CREATE TABLE IF NOT EXISTS proactive_rules (
                id TEXT PRIMARY KEY,
                name TEXT,
                trigger_condition TEXT,
                memory_type TEXT,
                max_age_hours INTEGER DEFAULT 24,
                min_importance REAL DEFAULT 0.5,
                priority INTEGER DEFAULT 5,
                enabled INTEGER DEFAULT 1,
                created_at TEXT
            );
        """)
        conn.commit()

    def _fts_insert(self, memory_id: str, content: str, mem_type: str, status: str):
        # No-op: FTS with content=memories auto-syncs via triggers
        pass

    def _fts_delete(self, memory_id: str):
        # No-op: FTS with content=memories auto-syncs via triggers
        pass

    def _fts_sync(self, conn: sqlite3.Connection, memory_id: str):
        # No-op: FTS with content=memories auto-syncs on UPDATE
        pass

    def insert_memory(self, memory: Memory) -> None:
        conn = self._connect()
        conn.execute("SAVEPOINT sp_insert")
        try:
            conn.execute("""
                INSERT OR REPLACE INTO memories (
                    id, type, status, content, source, source_trust,
                    project_id, agent_id, session_id, environment_id,
                    created_at, observed_at, valid_from, valid_until,
                    confidence, importance, utility, provenance_chain,
                    cost_ram, cost_cpu, cost_tokens, cost_storage_kb,
                    metadata, relations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                memory.id, memory.type, memory.status, memory.content,
                memory.source, memory.source_trust,
                memory.project_id, memory.agent_id, memory.session_id,
                memory.environment_id,
                memory.created_at.isoformat() if memory.created_at else None,
                memory.observed_at.isoformat() if memory.observed_at else None,
                memory.valid_from.isoformat() if memory.valid_from else None,
                memory.valid_until.isoformat() if memory.valid_until else None,
                memory.confidence, memory.importance, memory.utility,
                json.dumps(memory.provenance_chain),
                memory.cost.ram_mb, memory.cost.cpu_ms, memory.cost.tokens,
                memory.cost.storage_kb,
                json.dumps(memory.metadata),
                json.dumps(memory.relations)
            ))
            # FTS auto-syncs via content=memories
            conn.execute("RELEASE sp_insert")
        except Exception:
            conn.execute("ROLLBACK TO sp_insert")
            raise
        # Auto-embed for vector search (non-blocking failure)
        if self.vector is not None and memory.content:
            try:
                self.vector.embed_and_store(memory.id, memory.content)
            except Exception as e:
                logger.warning("Auto-embed failed: %s", e)

    def get_memory(self, memory_id: str) -> Optional[Dict]:
        conn = self._connect()
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_memory(self, memory_id: str, **fields) -> bool:
        if not fields:
            return False
        allowed = {
            "type", "status", "content", "source", "source_trust",
            "project_id", "agent_id", "session_id", "environment_id",
            "observed_at", "valid_from", "valid_until",
            "confidence", "importance", "utility",
            "provenance_chain", "cost_ram", "cost_cpu", "cost_tokens",
            "cost_storage_kb", "metadata", "relations",
        }
        set_parts = []
        values = []
        for k, v in fields.items():
            if k not in allowed:
                logger.warning("update_memory: unknown field '%s' skipped", k)
                continue
            if k in ("metadata", "relations", "provenance_chain") and isinstance(v, (list, dict)):
                v = json.dumps(v)
            set_parts.append(f"{k} = ?")
            values.append(v)
        if not set_parts:
            return False
        values.append(memory_id)
        conn = self._connect()
        conn.execute("SAVEPOINT sp_update")
        try:
            conn.execute(
                f"UPDATE memories SET {', '.join(set_parts)} WHERE id = ?",
                values
            )
            self._fts_sync(conn, memory_id)
            conn.execute("RELEASE sp_update")
            return True
        except Exception:
            conn.execute("ROLLBACK TO sp_update")
            raise

    def delete_memory(self, memory_id: str) -> bool:
        conn = self._connect()
        conn.execute("SAVEPOINT sp_delete")
        try:
            self._fts_delete(memory_id)
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.execute("RELEASE sp_delete")
            return True
        except Exception:
            conn.execute("ROLLBACK TO sp_delete")
            raise

    def search_vector(self, query: str, limit: int = 10, min_score: float = 0.2) -> List[Dict]:
        """Semantic search via embeddings. Falls back to LIKE if unavailable."""
        if self.vector is not None:
            try:
                return self.vector.search(query, limit=limit, min_score=min_score)
            except Exception as e:
                logger.warning("Vector search failed: %s", e)
        return self.search_fts(query, limit=limit)

    def search_hybrid(self, query: str, limit: int = 10) -> List[Dict]:
        """Hybrid search: vector + text, deduplicated, vector results first."""
        results = []
        seen = set()
        if self.vector is not None:
            try:
                for r in self.vector.search(query, limit=limit):
                    mid = r.get("id")
                    if mid not in seen:
                        seen.add(mid)
                        results.append(r)
            except Exception as e:
                logger.warning("Vector search failed in hybrid: %s", e)
        for r in self.search_fts(query, limit=limit):
            mid = r.get("id")
            if mid not in seen:
                seen.add(mid)
                results.append(r)
        return results[:limit]

    def recall_cost_aware(self, query: str, limit: int = 10, budget_tokens: int = None,
                          min_value: float = 0.0005, abstain_below: float = 0.35) -> List[Dict]:
        """P1.4 — hybrid ranked by value/cost. ABSTENTION policy: no LIKE match AND
        top vector score < abstain_below => 'NO_RELIABLE_MEMORY' (no lucky guesses)."""
        from .cost import rerank
        like_hits = self.search_fts(query, limit=limit * 3)  # only if it can produce,
        base = self.search_hybrid(query, limit=limit * 3)
        reranked = rerank(base, lambda m: (m.get("_score") or 0.5) if "_score" in m else 0.5)
        if not like_hits and (not reranked or max((m.get("_score", 0) for m in reranked if "_score" in m), default=0.0) < abstain_below):
            top_v = max((m.get("_score", 0) for m in reranked if "_score" in m), default=0.0)
            return [{"abstain": True,
                     "status": "NO_RELIABLE_MEMORY",
                     "reason": f"aucun match lexical, meilleure sim vectorielle {round(top_v, 3)} < {abstain_below}",
                     "query": query}]
        out = [m for m in reranked if m["_value"] >= min_value]
        if not out:
            return [{"abstain": True,
                     "status": "NO_RELIABLE_MEMORY",
                     "reason": f"aucune memoire >= valeur seuil {min_value}",
                     "query": query}]
        if budget_tokens is not None:
            final, spent = [], 0
            for m in out:
                cost = m.get("_cost_tokens", 0)
                if spent + cost > budget_tokens:
                    break
                spent += cost
                final.append(m)
            return final
        return out[:limit]

    def record_usage(self, memory_id: str, used: bool = True) -> bool:
        """Reinforcement: increment utility when a memory is actually used."""
        from .cost import record_usage as _ru
        return _ru(self, memory_id, used=used)

    def search_fts(self, query: str, limit: int = 50) -> List[Dict]:
        if not query or query.strip() == "":
            return []
        conn = self._connect()
        # LIKE prefilter (fast, substring) then WHOLE-WORD post-rank:
        # full-word matches float to the top, partial matches sink —
        # junk queries built on common short words stop polluting top results.
        import re as _re
        terms = [t.strip() for t in query.replace('"', ' ').split() if t.strip()]
        if not terms:
            return []
        conditions = " AND ".join(["content LIKE ?" for _ in terms])
        params = [f"%{t}%" for t in terms]
        params.append(max(limit * 3, limit))
        try:
            cursor = conn.execute(
                f"SELECT * FROM memories WHERE {conditions} LIMIT ?",
                params
            )
            rows = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.warning("search_fts failed: %s", e)
            return []

        def word_score(m: Dict) -> int:
            c = (m.get("content") or "").lower()
            return sum(1 for t in terms if len(t) > 2 and
                       _re.search(rf"\b{_re.escape(t.lower())}\b", c))

        rows.sort(key=lambda m: (word_score(m), m.get("created_at") or ""), reverse=True)
        return rows[:limit]

    def search_by_type(self, memory_type: str, limit: int = 50) -> List[Dict]:
        conn = self._connect()
        old_factory = conn.row_factory
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                "SELECT * FROM memories WHERE type = ? ORDER BY created_at DESC LIMIT ?",
                (memory_type, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.row_factory = old_factory

    def list_all(self, limit: int = 100) -> List[Dict]:
        """List recent memories of any type."""
        conn = self._connect()
        cursor = conn.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]

    def count(self, memory_type: Optional[str] = None) -> int:
        conn = self._connect()
        if memory_type:
            row = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE type = ?", (memory_type,)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return row[0] if row else 0
