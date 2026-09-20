"""Vector store for RAG — sentence-transformers embeddings + cosine similarity."""

import sqlite3
import json
import threading
import logging
from typing import List, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer
    import numpy as np

logger = logging.getLogger(__name__)

# Small, fast model (80MB, 384 dims)
DEFAULT_MODEL = "all-MiniLM-L6-v2"


class VectorStore:
    def __init__(self, db: "Database", model_name: str = DEFAULT_MODEL):
        self.db = db
        self._model_name = model_name
        self._model: Optional["SentenceTransformer"] = None
        self._warm_done = False
        self._init_table()

    @property
    def _np(self):
        try:
            import numpy as np
            return np
        except Exception as e:
            raise RuntimeError(f"numpy unavailable: {e}") from e

    @property
    def model(self) -> "SentenceTransformer":
        if self._model is None:
            # Lazy import — torch/sentence-transformers may be broken on some installs
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s", self._model_name)
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def warm(self) -> bool:
        """Preload the embedding model in background (kills the 8-10s cold start
        on the first query). Called by MCP/UI servers at startup."""
        if self._warm_done:
            return False
        self._warm_done = True

        def _bg():
            try:
                _ = self.model
                self.model.encode("warmup", normalize_embeddings=True)
                logger.info("Vector store warm")
            except Exception as e:
                logger.warning("Vector warm failed: %s", e)

        threading.Thread(target=_bg, daemon=True, name="jarvix-vector-warm").start()
        return True

    def _init_table(self):
        conn = self.db._connect()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                memory_id TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                model_name TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_emb_model ON memory_embeddings(model_name)"
        )
        conn.commit()

    def embed_and_store(self, memory_id: str, text: str) -> None:
        """Embed text and store the vector."""
        embedding = self.model.encode(text, normalize_embeddings=True)
        blob = embedding.tobytes()
        conn = self.db._connect()
        conn.execute(
            "INSERT OR REPLACE INTO memory_embeddings (memory_id, embedding, model_name) VALUES (?, ?, ?)",
            (memory_id, blob, self._model_name),
        )
        conn.commit()

    def embed_batch(self, items: List[Tuple[str, str]]) -> int:
        """Embed and store multiple (memory_id, text) pairs. Returns count stored."""
        if not items:
            return 0
        ids = [item[0] for item in items]
        texts = [item[1] for item in items]
        embeddings = self.model.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
        conn = self.db._connect()
        conn.executemany(
            "INSERT OR REPLACE INTO memory_embeddings (memory_id, embedding, model_name) VALUES (?, ?, ?)",
            [(mid, emb.tobytes(), self._model_name) for mid, emb in zip(ids, embeddings)],
        )
        conn.commit()
        return len(items)

    def search(self, query: str, limit: int = 10, min_score: float = 0.0) -> List[Dict]:
        """Semantic search — returns memories ranked by cosine similarity."""
        np = self._np
        query_emb = self.model.encode(query, normalize_embeddings=True)
        conn = self.db._connect()

        # Load all embeddings (fast for < 100K memories)
        rows = conn.execute(
            "SELECT memory_id, embedding FROM memory_embeddings WHERE model_name = ?",
            (self._model_name,),
        ).fetchall()

        if not rows:
            return []

        # Compute cosine similarities (dot product since normalized)
        scores: List[Tuple[str, float]] = []
        for row in rows:
            mid = row["memory_id"]
            emb = np.frombuffer(row["embedding"], dtype=np.float32)
            score = float(np.dot(query_emb, emb))
            if score >= min_score:
                scores.append((mid, score))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        top_ids = [sid for sid, _ in scores[:limit]]

        if not top_ids:
            return []

        # Fetch full memories
        placeholders = ",".join("?" * len(top_ids))
        mem_rows = conn.execute(
            f"SELECT * FROM memories WHERE id IN ({placeholders})", top_ids
        ).fetchall()

        # Preserve ranking order
        mem_by_id = {dict(r)["id"]: dict(r) for r in mem_rows}
        results = []
        for mid, score in scores[:limit]:
            if mid in mem_by_id:
                mem = mem_by_id[mid]
                mem["_score"] = round(score, 4)
                results.append(mem)

        return results

    def rebuild(self) -> int:
        """Re-embed all memories. Returns count embedded."""
        conn = self.db._connect()
        rows = conn.execute("SELECT id, content FROM memories WHERE content IS NOT NULL").fetchall()
        items = [(r["id"], r["content"]) for r in rows]
        # Clear existing embeddings
        conn.execute("DELETE FROM memory_embeddings WHERE model_name = ?", (self._model_name,))
        conn.commit()
        return self.embed_batch(items)

    def stats(self) -> Dict:
        conn = self.db._connect()
        count = conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0]
        return {"embeddings": count, "model": self._model_name, "dimensions": 384}
