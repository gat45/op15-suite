"""Automatic DB migration with version tracking."""

import sqlite3
import logging
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

# Registry of migrations: version -> (name, sql_or_fn)
MIGRATIONS: Dict[int, tuple] = {}


def migrate(version: int, name: str = ""):
    """Decorator to register a migration."""
    def decorator(fn):
        MIGRATIONS[version] = (name, fn)
        return fn
    return decorator


def _ensure_meta(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    row = conn.execute("SELECT value FROM _meta WHERE key = 'schema_version'").fetchone()
    if row is None:
        conn.execute("INSERT INTO _meta (key, value) VALUES ('schema_version', '0')")
        conn.commit()


def get_version(conn: sqlite3.Connection) -> int:
    _ensure_meta(conn)
    row = conn.execute("SELECT value FROM _meta WHERE key = 'schema_version'").fetchone()
    return int(row[0]) if row else 0


def set_version(conn: sqlite3.Connection, version: int):
    conn.execute("UPDATE _meta SET value = ? WHERE key = 'schema_version'", (str(version),))
    conn.commit()


def run_migrations(conn: sqlite3.Connection) -> int:
    """Run all pending migrations. Returns new version."""
    _ensure_meta(conn)
    current = get_version(conn)
    applied = 0

    for version in sorted(MIGRATIONS.keys()):
        if version > current:
            name, fn = MIGRATIONS[version]
            logger.info("Migration %d: %s", version, name or "unnamed")
            try:
                fn(conn)
                set_version(conn, version)
                applied += 1
                logger.info("Migration %d applied successfully", version)
            except Exception as e:
                logger.error("Migration %d failed: %s", version, e)
                raise

    if applied:
        logger.info("Applied %d migration(s), now at version %d", applied, get_version(conn))
    return get_version(conn)


# ── Migrations ──────────────────────────────────────────────────

@migrate(1, "add embedding column to memories")
def _migration_001(conn: sqlite3.Connection):
    # embedding column already exists in base schema, skip
    pass


@migrate(2, "add embedding metadata columns")
def _migration_002(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            memory_id TEXT PRIMARY KEY,
            embedding BLOB NOT NULL,
            model_name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_emb_model ON memory_embeddings(model_name)")


@migrate(3, "add llm_conversations table")
def _migration_003(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_conversations (
            id TEXT PRIMARY KEY,
            memory_id TEXT,
            messages TEXT DEFAULT '[]',
            model TEXT,
            tokens_used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE SET NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_memory ON llm_conversations(memory_id)")


@migrate(4, "add tags column to memories")
def _migration_004(conn: sqlite3.Connection):
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN tags TEXT DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass  # Column already exists
