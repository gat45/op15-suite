"""
memory_store.py
Mémoire persistante (SQLite) : entités, sources, corrélations, hypothèses.
"""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional


DB_PATH = Path(__file__).parent / "memory.db"


def fingerprint(text: str) -> str:
    """Empreinte courte d'un texte pour détecter les documents inchangés."""
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


class MemoryStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            fetched_at REAL,
            raw_text TEXT,
            fingerprint TEXT
        );

        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            entity_type TEXT,
            source_id INTEGER,
            first_seen REAL,
            FOREIGN KEY(source_id) REFERENCES sources(id)
        );

        CREATE TABLE IF NOT EXISTS correlations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a INTEGER,
            entity_b INTEGER,
            relation_type TEXT,
            weight REAL,
            evidence TEXT,
            created_at REAL,
            FOREIGN KEY(entity_a) REFERENCES entities(id),
            FOREIGN KEY(entity_b) REFERENCES entities(id)
        );

        CREATE TABLE IF NOT EXISTS hypotheses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement TEXT,
            confidence REAL,
            supporting_correlations TEXT,
            created_at REAL,
            status TEXT DEFAULT 'open'
        );

        CREATE TABLE IF NOT EXISTS procedures (
            name TEXT PRIMARY KEY,
            aspect TEXT,
            status TEXT,
            steps TEXT,
            risks TEXT,
            source_refs TEXT,
            contract TEXT,
            updated_at REAL
        );

        CREATE TABLE IF NOT EXISTS procedure_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            procedure_name TEXT,
            entity_name TEXT,
            entity_type TEXT,
            source_id INTEGER,
            FOREIGN KEY(procedure_name) REFERENCES procedures(name),
            FOREIGN KEY(source_id) REFERENCES sources(id)
        );

        CREATE TABLE IF NOT EXISTS aspects (
            aspect TEXT PRIMARY KEY,
            description TEXT,
            updated_at REAL
        );
        """)
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_correlations_pair "
                    "ON correlations(entity_a, entity_b)")
        self._migrate_schema(cur)
        self.conn.commit()

    def _migrate_schema(self, cur: sqlite3.Cursor):
        """Ajoute les colonnes manquantes sur les bases existantes (idempotent)."""
        cols = {r["name"] for r in cur.execute("PRAGMA table_info(sources)").fetchall()}
        if "fingerprint" not in cols:
            cur.execute("ALTER TABLE sources ADD COLUMN fingerprint TEXT")

    def add_source(self, url: str, title: str, raw_text: str,
                   fp: str | None = None) -> tuple[int, bool]:
        """Ajoute (ou récupère) une source. Retourne (source_id, changée).

        Si une source au même URL existe avec la même empreinte, elle est
        considérée inchangée : rien n'est ré-ingéré (idempotence + gain perf).
        """
        fp = fp or fingerprint(raw_text)
        cur = self.conn.cursor()
        cur.execute("SELECT id, fingerprint FROM sources WHERE url = ?", (url,))
        row = cur.fetchone()
        if row:
            if row["fingerprint"] == fp:
                return row["id"], False
            cur.execute(
                "UPDATE sources SET title = ?, raw_text = ?, fetched_at = ?, fingerprint = ? "
                "WHERE id = ?",
                (title, raw_text, time.time(), fp, row["id"]),
            )
            self.conn.commit()
            return row["id"], True
        cur.execute(
            "INSERT INTO sources (url, title, fetched_at, raw_text, fingerprint) "
            "VALUES (?, ?, ?, ?, ?)",
            (url, title, time.time(), raw_text, fp),
        )
        self.conn.commit()
        return cur.lastrowid, True

    def _entity_id(self, cur: sqlite3.Cursor, name: str, entity_type: str,
                   source_id: int) -> int:
        """Identifiant d'une entité (création SANS commit — pour les lots).

        B3 (audit 2026-08-18) : permet à add_domain_correlations d'insérer
        plusieurs entités/corrélations dans UNE transaction atomique, au lieu
        d'un commit() par ligne via add_entity().
        """
        row = cur.execute(
            "SELECT id FROM entities WHERE name = ? AND entity_type = ?",
            (name, entity_type),
        ).fetchone()
        if row:
            return row["id"]
        cur.execute(
            "INSERT INTO entities (name, entity_type, source_id, first_seen) VALUES (?, ?, ?, ?)",
            (name, entity_type, source_id, time.time()),
        )
        return cur.lastrowid

    def add_entity(self, name: str, entity_type: str, source_id: int) -> int:
        cur = self.conn.cursor()
        eid = self._entity_id(cur, name, entity_type, source_id)
        self.conn.commit()
        return eid

    def add_domain_correlation(self, name_a: str, type_a: str,
                               name_b: str, type_b: str, source_id: int) -> int:
        """Corrélation de domaine (entités op15_*) cumulée par paire ordonnée.
        Idempotent par source : une même paire vue dans la même source ne
        ré-incrémente pas le poids à chaque re-exécution du pipeline."""
        id_a = self.add_entity(name_a, type_a, source_id)
        id_b = self.add_entity(name_b, type_b, source_id)
        row = self.conn.execute(
            "SELECT weight, evidence FROM correlations "
            "WHERE entity_a = ? AND entity_b = ?", (id_a, id_b)).fetchone()
        if row:
            try:
                sources = set(json.loads(row["evidence"] or "[]"))
            except Exception:  # noqa: BLE001 — ancien format "source_id=N"
                sources = set()
            if source_id in sources:
                return id_a
            sources.add(source_id)
            self.conn.execute(
                "UPDATE correlations SET weight = weight + 1, evidence = ? "
                "WHERE entity_a = ? AND entity_b = ?",
                (json.dumps(sorted(sources)), id_a, id_b),
            )
        else:
            self.conn.execute(
                """INSERT INTO correlations (entity_a, entity_b, relation_type,
                   weight, evidence, created_at)
                   VALUES (?, ?, 'cooccurrence', 1, ?, ?)""",
                (id_a, id_b, json.dumps([source_id]), time.time()),
            )
        self.conn.commit()
        return id_a

    def add_hypothesis(self, statement: str, confidence: float,
                        supporting_correlations: list[int]) -> int:
        cur = self.conn.cursor()
        row = cur.execute("SELECT id, confidence FROM hypotheses WHERE statement = ?",
                          (statement,)).fetchone()
        if row:
            # B5 (audit 2026-08-18) : reflète la confiance recalculée (peut baisser
            # si le graphe de preuves s'affaiblit) au lieu d'un max monotone qui
            # masquait un affaiblissement.
            cur.execute(
                "UPDATE hypotheses SET confidence = ?, status = 'open' WHERE id = ?",
                (confidence, row["id"]),
            )
            self.conn.commit()
            return row["id"]
        cur.execute(
            """INSERT INTO hypotheses
               (statement, confidence, supporting_correlations, created_at)
               VALUES (?, ?, ?, ?)""",
            (statement, confidence, json.dumps(supporting_correlations), time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def all_entities(self):
        return self.conn.execute("SELECT * FROM entities").fetchall()

    def all_correlations(self):
        return self.conn.execute("SELECT * FROM correlations").fetchall()

    def all_hypotheses(self, min_confidence: float = 0.0):
        return self.conn.execute(
            "SELECT * FROM hypotheses WHERE confidence >= ? ORDER BY confidence DESC",
            (min_confidence,),
        ).fetchall()

    def upsert_procedure(self, name: str, aspect: str, status: str,
                         steps: list[str], risks: list[str],
                         source_refs: list[str], contract: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """INSERT INTO procedures
               (name, aspect, status, steps, risks, source_refs, contract, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 aspect=excluded.aspect, status=excluded.status,
                 steps=excluded.steps, risks=excluded.risks,
                 source_refs=excluded.source_refs, contract=excluded.contract,
                 updated_at=excluded.updated_at""",
            (name, aspect, status, json.dumps(steps), json.dumps(risks),
             json.dumps(source_refs), contract, time.time()),
        )
        self.conn.commit()

    def record_procedure_mention(self, procedure_name: str, entity_name: str,
                                 entity_type: str, source_id: int) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO procedure_mentions
               (procedure_name, entity_name, entity_type, source_id)
               VALUES (?, ?, ?, ?)""",
            (procedure_name, entity_name, entity_type, source_id),
        )
        self.conn.commit()

    def get_procedures(self, aspect: str | None = None,
                       status: str | None = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM procedures"
        conds, args = [], []
        if aspect:
            conds.append("aspect = ?")
            args.append(aspect)
        if status:
            conds.append("status = ?")
            args.append(status)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY aspect, name"
        return self.conn.execute(q, args).fetchall()

    def upsert_aspect(self, aspect: str, description: str) -> None:
        self.conn.execute(
            """INSERT INTO aspects (aspect, description, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(aspect) DO UPDATE SET
                 description=excluded.description, updated_at=excluded.updated_at""",
            (aspect, description, time.time()),
        )
        self.conn.commit()

    def get_aspects(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM aspects ORDER BY aspect").fetchall()

    def procedure_mentions(self, procedure_name: str) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT pm.*, s.url AS source_url FROM procedure_mentions pm
               LEFT JOIN sources s ON pm.source_id = s.id
               WHERE pm.procedure_name = ?""",
            (procedure_name,),
        ).fetchall()

    def correlation_by_pair(self, name_a: str, name_b: str) -> int | None:
        """Retourne l'id d'une corrélation persistée entre deux entités nommées."""
        row = self.conn.execute(
            """SELECT c.id FROM correlations c
               JOIN entities ea ON ea.id = c.entity_a
               JOIN entities eb ON eb.id = c.entity_b
               WHERE LOWER(ea.name) = LOWER(?) AND LOWER(eb.name) = LOWER(?)""",
            (name_a, name_b),
        ).fetchone()
        return row["id"] if row else None

    def add_domain_correlations(self, pairs: list[tuple], source_id: int) -> int:
        """Variante par lot d'add_domain_correlation : UNE transaction atomique."""
        added = 0
        cur = self.conn.cursor()
        for (name_a, type_a, name_b, type_b) in pairs:
            id_a = self._entity_id(cur, name_a, type_a, source_id)
            id_b = self._entity_id(cur, name_b, type_b, source_id)
            row = self.conn.execute(
                "SELECT weight, evidence FROM correlations "
                "WHERE entity_a = ? AND entity_b = ?", (id_a, id_b)).fetchone()
            if row:
                try:
                    sources = set(json.loads(row["evidence"] or "[]"))
                except Exception:  # noqa: BLE001
                    sources = set()
                if source_id in sources:
                    continue
                sources.add(source_id)
                self.conn.execute(
                    "UPDATE correlations SET weight = weight + 1, evidence = ? "
                    "WHERE entity_a = ? AND entity_b = ?",
                    (json.dumps(sorted(sources)), id_a, id_b),
                )
            else:
                self.conn.execute(
                    """INSERT INTO correlations (entity_a, entity_b, relation_type,
                       weight, evidence, created_at)
                       VALUES (?, ?, 'cooccurrence', 1, ?, ?)""",
                    (id_a, id_b, json.dumps([source_id]), time.time()),
                )
            added += 1
        self.conn.commit()
        return added

    def close(self):
        self.conn.close()
