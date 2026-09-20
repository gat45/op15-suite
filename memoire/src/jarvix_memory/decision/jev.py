"""P2.10 — JEV decision layer: bounded typed judgements, no text generation.

Three primitives:
  Choice(context) -> distribution over options (arguable winner + confidence)
  Score(grid)     -> 0..x scores per dimension
  Noul(gate)      -> probability for ALLOW/REVIEW/BLOCK gates

Provider abstraction: RuleBasedProvider is deterministic/offline. A future
LocalLLMProvider can implement the same contract without touching callers.
Thresholds stay in code — a probability is not proof.
"""

import json
import re
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DESTRUCTIVE_PATTERNS = [
    (r"\b(delete|rm\s|del\s|remove|erase)\b", 0.85),
    (r"\b(format|flash|unlock bootloader|wipe)\b", 0.97),
    (r"\b(disable|kill|stop)\b", 0.55),
    (r"\b(dangerous|risky|irreversible)\b", 0.8),
]


class DecisionProvider:
    """Contract: route / filter / verify / gate / score."""
    def route(self, query: str) -> Dict:...
    def filter(self, memory: Dict, context: str) -> Dict:...
    def verify(self, claim: str, evidence_stats: Dict) -> Dict:...
    def gate(self, action: str, destructive_priority: float = 0.85) -> Dict:...
    def score(self, grid: Dict) -> Dict:...  # {"criterion": observed_0_to_1}


class RuleBasedProvider(DecisionProvider):
    """Deterministic judge — works offline, no model, instant."""

    MEM_KEYWORDS = {
        "episodic": ["s'est", "hier", "avant", "event", "when", "crash", "log", "sessions"],
        "semantic": ["fact", "fait", "c'est", "what", "qui", "definition", "tok/s", "version"],
        "procedural": ["how", "comment", "procedure", "steps", "build", "flash", "compile"],
        "decision": ["why", "pourquoi", "choix", "decision", "alternative"],
        "hypothesis": ["hypothesis", "si je", "maybe", "probable", "cause"],
        "strategy": ["approach", "method", "solution", "best way", "strategy"],
        "recovery": ["failure", "error", "retry", "recover", "fail"],
        "evidence": ["proof", "preuve", "verify", "test", "sha256"],
    }

    def route(self, query: str) -> Dict:
        """Layer distribution (JEV Noul) — one query -> which memory layer matters."""
        q = query.lower()
        scores = {}
        for layer, kws in self.MEM_KEYWORDS.items():
            hits = sum(1 for kw in kws if kw in q)
            scores[layer] = round(min(1.0, 0.1 + hits * 0.4), 3)
        # epistemic base fallback: semantic
        if sum(scores.values()) <= 0.1:
            scores["semantic"] = 0.5
        total = sum(scores.values()) or 1.0
        dist = {k: round(v / total, 3) for k, v in scores.items()}
        winner = max(dist, key=dist.get)
        return {"choice": winner, "distribution": dist,
                "confidence": round(dist[winner], 3)}

    def filter(self, memory: Dict, context: str, max_tokens: int = None) -> Dict:
        """Inject probability (JEV Noul): keyword overlap + cost budget."""
        mbytes = (memory.get("content") or "").lower()
        words = [w for w in context.lower().split() if len(w) > 3]
        overlap = sum(1 for w in words if w in mbytes)
        import sys as _sys
        base = min(1.0, 0.15 + overlap * 0.3)
        confidence = memory.get("confidence", 0.5) or 0.5
        prob = base * (0.7 + 0.3 * confidence)
        if max_tokens and len(mbytes) * 0.25 > max_tokens:
            prob *= 0.5  # cost penalty
        action = "inject" if prob >= 0.75 else ("maybe" if prob >= 0.45 else "ignore")
        return {"decision": action, "prob": round(float(prob), 3)}

    def verify(self, claim: str, evidence_stats: Dict) -> Dict:
        """Given evidence stats {total, passed, failed}: support/contradict/unknown."""
        total = evidence_stats.get("total", 0)
        passed = evidence_stats.get("passed", 0)
        failed = evidence_stats.get("failed", 0)
        if total == 0:
            return {"supports": 0.0, "contradicts": 0.0, "unknown": 1.0,
                    "label": "no_evidence"}
        s = passed / (total + 1e-6)
        c = failed / total
        u = max(0.0, 1.0 - s - c)
        label = ("supports" if s >= 0.8 else
                 "contradicts" if c >= 0.8 else
                 "inconclusive")
        return {"supports": round(s, 3), "contradicts": round(c, 3),
                "unknown": round(u, 3), "label": label}

    def gate(self, action: str, destructive_threshold: float = 0.85) -> Dict:
        """ALLOW / REVIEW / BLOCK for a proposed action text (destructive check)."""
        a = action.lower()
        max_p, pattern = 0.0, None
        for pat, sev in DESTRUCTIVE_PATTERNS:
            if re.search(pat, a.lower()):
                if sev > max_p:
                    max_p, pattern = sev, pat
        if max_p >= destructive_threshold:
            decision = "BLOCK"
        elif max_p > 0:
            decision = "REVIEW"
        else:
            decision = "ALLOW"
        return {"decision": decision, "destructive_prob": max_p,
                "matched_pattern": pattern}

    def score(self, grid: Dict) -> Dict:
        """JEV Score: given {criterion: observed_0_to_1}, compute weighted verdict."""
        weights = grid.pop("_weights", {}) or {k: 1.0 for k in grid}
        total_w = sum(weights.get(k, 1.0) for k in grid) or 1.0
        weighted = sum((v or 0.0) * weights.get(k, 1.0) for k, v in grid.items()) / total_w
        return {"score": round(weighted, 3),
                "label": "high" if weighted >= 0.75 else ("medium" if weighted >= 0.45 else "low"),
                "per_criterion": {k: v for k, v in grid.items() if k != "_weights"}}


class JEV:
    """Facade around a DecisionProvider — the jarvix decision brain.
    Provider selection: config.json {"jev_provider": "remote"|"rules"} + env.
    Falls back to RuleBasedProvider if remote is unavailable or fails."""

    def __init__(self, db, provider: DecisionProvider = None, config_path=None):
        self.db = db
        self.provider = provider or self._pick_provider(config_path)

    @staticmethod
    def _pick_provider(config_path=None) -> DecisionProvider:
        import os
        from pathlib import Path as _Path
        cfg_path = config_path or _Path(__file__).resolve().parents[3] / "config.json"
        cfg = {}
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        want_remote = (os.environ.get("JARVIX_JEV_PROVIDER") == "remote"
                       or cfg.get("jev_provider") == "remote"
                       or bool(os.environ.get("JARVIX_JEV_API_KEY"))
                       or bool(os.environ.get("TYPESAFE_API_KEY")))
        if want_remote:
            try:
                from .jev_remote import JevRemoteProvider
                rp = JevRemoteProvider(
                    base_url=os.environ.get("JARVIX_JEV_BASE_URL") or cfg.get("jev_base_url"),
                    model=os.environ.get("JARVIX_JEV_MODEL") or cfg.get("jev_model"),
                    config_path=cfg_path)
                if rp.available:
                    return rp
                logger.warning("Jev remote sans cle API — RuleBasedProvider")
            except ImportError:
                logger.warning("jev_remote module absent — RuleBasedProvider")
        return RuleBasedProvider()

    def log_decision(self, kind: str, subject: str, result: Dict):
        from ..core.models import Memory
        self.db.insert_memory(Memory(
            type="decision",
            content=f"JEV {kind}: {subject} -> {result.get('choice') or result.get('decision') or result.get('label')}",
            confidence=result.get("confidence") or result.get("destructive_prob") or 0.7,
            source="jev",
            metadata={"jev_kind": kind, "subject": subject, "result": result,
                      "decided_at": datetime.utcnow().isoformat()}))

    def route(self, query: str, log: bool = True) -> Dict:
        r = self.provider.route(query)
        if log:
            self.log_decision("route", query[:100], r)
        return r

    def filter(self, memory: Dict, context: str, max_tokens: int = None, log: bool = False) -> Dict:
        return self.provider.filter(memory, context, max_tokens=max_tokens)

    def verify(self, claim: str, evidence_stats: Dict, log: bool = True) -> Dict:
        r = self.provider.verify(claim, evidence_stats)
        if log:
            self.log_decision("verify", claim[:100], r)
        return r

    def gate(self, action: str, destructive_threshold: float = 0.85, log: bool = True) -> Dict:
        r = self.provider.gate(action, destructive_threshold)
        if log:
            self.log_decision("gate", action[:100], r)
        return r

    def score(self, grid: Dict, subject: str = None, log: bool = True) -> Dict:
        r = self.provider.score(dict(grid))
        if log:
            self.log_decision("score", subject or "score-grid", r)
        return r

    def decide(self, context: str, options: List[str]) -> Dict:
        """JEV Choice over explicit options — delegated to provider (remote or rules)."""
        r = self.provider.decide(context, options)
        r = {"choice": r.get("choice"), "distribution": r.get("distribution", {}),
             "confidence": r.get("confidence", 0.0), "provider": r.get("provider", "rules")}
        self.log_decision("decide", context[:100], r)
        return r
