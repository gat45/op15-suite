"""Environment snapshots — every memory tying to the conditions it was true under.

An environment is a fingerprinted snapshot of OS/hardware/software context.
Claims/experiments referencing an environment are only "valid under" it.
"""

import json
import uuid
import hashlib
import platform
import logging
import subprocess
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def _capture_base() -> Dict:
    env = {
        "os": platform.system(),
        "os_release": platform.release(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "captured_at": datetime.utcnow().isoformat(),
    }
    # git commit if inside a repo
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=5)
        if out.returncode == 0:
            env["git_commit"] = out.stdout.strip()[:12]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return env


class EnvironmentStore:
    def __init__(self, db):
        self.db = db

    def capture(self, extra: Dict = None) -> Dict:
        """Capture a full env snapshot; returns {env_id, fingerprint, snapshot}."""
        snapshot = _capture_base()
        if extra:
            snapshot.update(extra)
        # fingerprint = stable hash of the *identity* fields (not the date)
        identity = {k: snapshot[k] for k in snapshot
                    if k not in ("captured_at",) and isinstance(snapshot[k], str)}
        fp = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:12]
        env_id = f"env_{fp}"
        content = f"ENVIRONMENT {env_id}: {json.dumps(identity, sort_keys=True)}"
        # Deduplicate: same fingerprint = same environment record
        existing = self.db._connect().execute(
            "SELECT id, content FROM memories WHERE type = 'environment' AND content = ?",
            (content,)).fetchone()
        if not existing:
            from ..core.models import Memory
            m = Memory(type="environment", content=content, confidence=1.0,
                       source="auto", metadata={"env_id": env_id, "snapshot": snapshot})
            self.db.insert_memory(m)
        return {"env_id": env_id, "fingerprint": fp, "snapshot": snapshot}

    def get(self, env_id: str) -> Optional[Dict]:
        conn = self.db._connect()
        row = conn.execute(
            "SELECT * FROM memories WHERE type = 'environment' AND metadata LIKE ? LIMIT 1",
            (f'%"env_id": "{env_id}"%',)).fetchone()
        if not row:
            return None
        meta = json.loads(dict(row).get("metadata", "{}"))
        return {"id": dict(row)["id"], "env_id": env_id, "snapshot": meta.get("snapshot", {})}

    def diff(self, env_a: str, env_b: str) -> Dict:
        """Compare two environment snapshots — changed keys reduce trust in results."""
        a, b = self.get(env_a), self.get(env_b)
        if not a or not b:
            return {"error": "environment not found"}
        # Only compare identity fields (captured_at is always different)
        sa = {k: v for k, v in a["snapshot"].items() if k != "captured_at"}
        sb = {k: v for k, v in b["snapshot"].items() if k != "captured_at"}
        changed = {k: (sa.get(k), sb.get(k))
                   for k in set(sa) & set(sb)
                   if sa.get(k) != sb.get(k)}
        return {"env_a": env_a, "env_b": env_b, "changed_keys": changed,
                "compatible": not changed}
