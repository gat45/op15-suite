"""Experiment memory — hypothesis lifecycle with negative knowledge.

HYPOTHESIS -> EXPERIMENT(s) -> CONFIRMED / REFUTED / INCONCLUSIVE
A refuted hypothesis gets do_not_repeat=true: the system must never spend
the same experiment twice.
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

REFUTED_TEST_LIMIT = 2  # attempts before do_not_repeat is set


class ExperimentTracker:
    def __init__(self, db):
        self.db = db

    # ── Create memory rows with the right type ──
    def _insert(self, mtype: str, content: str, metadata: Dict) -> Dict:
        from ..core.models import Memory
        m = Memory(type=mtype, content=content, status="provisional",
                   metadata=metadata, source="jarvix")
        self.db.insert_memory(m)
        return {"id": m.id, "type": mtype, "content": content}

    def propose_hypothesis(self, statement: str, env_id: Optional[str] = None,
                           rationale: str = None) -> Dict:
        meta = {"h_status": "PROPOSED", "experiments": [], "created_at": datetime.utcnow().isoformat()}
        if env_id:
            meta["env_id"] = env_id
        if rationale:
            meta["rationale"] = rationale
        return self._insert("hypothesis", statement, meta)

    def run_experiment(self, hyp_id: str, name: str, result: str, success: bool,
                       env_id: Optional[str] = None, measurements: Dict = None) -> Dict:
        hyp_mem = self.db.get_memory(hyp_id)
        if not hyp_mem:
            return {"error": "hypothesis not found"}
        exp_meta = {
            "hypothesis_id": hyp_id,
            "name": name,
            "result": result,
            "success": success,
            "env_id": env_id,
            "measurements": measurements or {},
            "ran_at": datetime.utcnow().isoformat(),
        }
        exp = self._insert("experiment", f"[{name}] {result} (ENV {env_id or 'n/a'})", exp_meta)

        hyp_meta = json.loads(hyp_mem.get("metadata", "{}"))
        exps = hyp_meta.setdefault("experiments", [])
        exps.append({"experiment_id": exp["id"], "name": name, "success": success,
                     "env_id": env_id, "ran_at": exp_meta["ran_at"]})
        hyp_meta["h_status"] = "TESTING"
        self.db.update_memory(hyp_id, metadata=json.dumps(hyp_meta))
        out = {"experiment_id": exp["id"], "hypothesis_id": hyp_id, "attempts": len(exps)}
        # Blind-spot fix: auto-refute without waiting for an explicit conclude
        fails = sum(1 for e in exps if not e.get("success"))
        if fails >= REFUTED_TEST_LIMIT and hyp_meta.get("h_status") not in ("REFUTED", "CONFIRMED"):
            concl = self.conclude(hyp_id, "refuted")
            out["auto_refuted"] = True
            out["do_not_repeat"] = concl["do_not_repeat"]
        return out

    def conclude(self, hyp_id: str, verdict: str) -> Dict:
        """verdict: confirmed | refuted | inconclusive | superseded"""
        if verdict not in ("confirmed", "refuted", "inconclusive", "superseded"):
            return {"error": "verdict invalide"}
        hyp_mem = self.db.get_memory(hyp_id)
        if not hyp_mem:
            return {"error": "hypothesis not found"}
        meta = json.loads(hyp_mem.get("metadata", "{}"))
        exps = meta.get("experiments", [])
        meta["h_status"] = verdict.upper()
        meta["concluded_at"] = datetime.utcnow().isoformat()
        # Negative knowledge: enough refuting attempts -> do_not_repeat
        fails = sum(1 for e in exps if not e.get("success"))
        if verdict == "refuted" or fails >= REFUTED_TEST_LIMIT:
            meta["do_not_repeat"] = True
            meta["refutation_evidence"] = [
                (e.get("experiment_id"), e.get("name"), e.get("env_id")) for e in exps
                if not e.get("success")]
        self.db.update_memory(hyp_id, metadata=json.dumps(meta))
        return {"hypothesis_id": hyp_id, "verdict": verdict,
                "do_not_repeat": meta.get("do_not_repeat", False),
                "attempts": len(exps), "failures": fails}

    def repeat_guard(self, statement: str, limit: int = 5) -> Dict:
        """Check before re-running an experiment: has this path already been refuted?"""
        matches = self.db.search_fts(statement, limit=limit)
        guarded = []
        for m in matches:
            if m.get("type") != "hypothesis":
                continue
            meta = json.loads(m.get("metadata", "{}"))
            if meta.get("do_not_repeat") or meta.get("h_status") == "REFUTED":
                guarded.append({
                    "id": m["id"], "statement": (m.get("content") or "")[:200],
                    "verdict": meta.get("h_status"),
                    "refutations": meta.get("refutation_evidence", []),
                })
        return {"blocked": bool(guarded), "refuted_paths": guarded}

    def pending_hypotheses(self, limit: int = 20) -> List[Dict]:
        rows = self.db.search_by_type("hypothesis", limit=limit)
        out = []
        for r in rows:
            meta = json.loads(r.get("metadata", "{}"))
            if meta.get("h_status") in ("PROPOSED", "TESTING", None, ""):
                out.append({"id": r["id"], "content": r.get("content"),
                            "status": meta.get("h_status", "PROPOSED"),
                            "attempts": len(meta.get("experiments", []))})
        return out
