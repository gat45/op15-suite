"""JEV remote provider — TypeSafe System One API (jev-latest).

One POST to /v1/systemone per call; questions are evaluated in parallel
server-side (70-500 ms). Answers use typed constraints: noul (yes/no
probability), choice (option + distribution), score (rubric 0..N).

The API key is NEVER committed: JARVIX_JEV_API_KEY env or config.json.
Every method returns the same shaped dict as RuleBasedProvider plus a
"provider" field — callers get policies without knowing who judged.
"""

import json
import os
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Optional
from .jev import DecisionProvider, RuleBasedProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.typesafe.ai/v1"
DEFAULT_MODEL = "jev-latest"


class JevRemoteProvider(DecisionProvider):
    """System One typed judgements. Same DecisionProvider contract as rules."""

    MEM_LAYERS = ["episodic", "semantic", "procedural", "decision",
                  "hypothesis", "strategy", "recovery", "evidence", "graph"]

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None,
                 timeout: float = 30.0, config_path: Path = None):
        # Key priority: explicit arg > env > config.json (gitignored)
        self.api_key = api_key or os.environ.get("JARVIX_JEV_API_KEY") \
            or os.environ.get("TYPESAFE_API_KEY")
        if not self.api_key and config_path:
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                self.api_key = cfg.get("jev_api_key")
                if not base_url:
                    base_url = cfg.get("jev_base_url")
                if not model:
                    model = cfg.get("jev_model")
            except Exception:
                pass
        self.base_url = base_url or os.environ.get("JARVIX_JEV_BASE_URL") or DEFAULT_BASE_URL
        self.model = model or os.environ.get("JARVIX_JEV_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        self.last_error: Dict = {}
        self.last_quota: Dict = {}

    def status(self) -> Dict:
        """Availability + last known quota (jev-agent extra). One tiny probe call."""
        base = {"provider": "jev-remote", "base_url": self.base_url,
                "model": self.model, "available": self.available}
        if not self.available:
            return base
        try:
            self._request("HEALTHCHECK", {
                "ok": {"type": "noul", "criteria": {"true": "oui", "false": "non"},
                        "instructions": "Le service repond-t-il ?"},
            })
            return {**base, "quota": self.last_quota, "ok": True}
        except Exception as e:
            return {**base, "ok": False, "reason": str(e)}

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _request(self, state, questions: Dict, retries: int = 2) -> Dict:
        """Single HTTP call. Official policy: 429/529 -> backoff with Retry-After."""
        import time as _time
        last_exc: Exception = RuntimeError("no attempt")
        for attempt in range(retries + 1):
            req = urllib.request.Request(
                f"{self.base_url}/systemone",
                data=json.dumps({
                    "model": self.model,
                    "state": state,
                    "questions": questions,
                }).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read())
                self.last_error = {}
                self.last_quota = body.get("quota", {})
                return body.get("answers", {})
            except urllib.error.HTTPError as e:
                last_exc = e
                if e.code in (429, 529) and attempt < retries:
                    raw = (e.headers.get("Retry-After") or "").strip()
                    wait = float(raw) if raw.replace(".", "", 1).isdigit() else 0.5 * (2 ** attempt)
                    logger.warning("jev HTTP %s — retry apres %.1fs", e.code, wait)
                    _time.sleep(wait)
                    continue
                raise
        raise last_exc

    # ── DecisionProvider contract ─────────────────────────────

    def route(self, query: str) -> Dict:
        """Jev Choice: which memory layer serves this query."""
        criteria = {l: f"Acces la couche memoire {l} pour cette requete"
                    for l in self.MEM_LAYERS}
        try:
            a = self._request(query, {
                "layer": {
                    "type": "choice",
                    "instructions": "Quelle couche memoire est la plus pertinente pour cette requete ?",
                    "criteria": criteria,
                },
            }).get("layer", {})
            choice = a.get("choice")
            if choice:
                probs = a.get("probabilities", {})
                return {"choice": choice, "distribution": probs,
                        "confidence": round(a.get("confidence", probs.get(choice, 0.0)), 3),
                        "provider": "jev-remote"}
            raise ValueError("reponse choice vide")
        except Exception as e:
            logger.warning("jev route fallback: %s", e)
            return {"choice": "semantic", "distribution": {}, "confidence": 0.3,
                    "provider": "rules", "reason": str(e)}

    def filter(self, memory: Dict, context: str, max_tokens: int = None) -> Dict:
        """Jev Noul: inject this memory NOW? (cost-aware caller keeps budget)."""
        state = {"memory": (memory.get("content") or "")[:2000],
                 "context": context[:2000]}
        try:
            a = self._request(state, {
                "inject": {"type": "noul",
                           "criteria": {"true": "injecter maintenant", "false": "ne pas injecter"},
                           "instructions": "Cette memoire est-elle pertinente a INJECTER dans ce contexte MAINTENANT ?"},
            }).get("inject", {})
            p = float(a.get("noul", 0.0))
            action = "inject" if p >= 0.75 else ("maybe" if p >= 0.45 else "ignore")
            return {"decision": action, "prob": p, "provider": "jev-remote"}
        except Exception as e:
            logger.warning("jev filter fallback: %s", e)
            return {"decision": "ignore", "prob": 0.0,
                    "provider": "rules", "reason": str(e)}

    def verify(self, claim: str, evidence_stats: Dict) -> Dict:
        # Rich state: plain-language breakdown so the model can actually judge
        total = evidence_stats.get("total", 0)
        ev_list = evidence_stats.get("evidence", [])
        passed = sum(1 for e in ev_list if isinstance(e, dict) and e.get("passed"))
        failed = sum(1 for e in ev_list
                     if isinstance(e, dict) and e.get("passed") is False)
        if not passed and not failed and total:
            passed = int(evidence_stats.get("passed", 0))
        types = sorted({e.get("type") for e in ev_list if isinstance(e, dict) and e.get("type")})
        state = (f"CLAIM: {claim[:1200]}\n"
                 f"PREUVES: {passed} passent, {failed} echouent ; "
                 f"types={types if types else 'n/a'}")
        try:
            a = self._request(state, {
                "supports": {"type": "noul",
                             "criteria": {"true": "les preuves soutiennent le claim", "false": "elles le contredisent ou ne le soutiennent pas"},
                             "instructions": "Les preuves presentees supportent-elles ce claim ?"},
            }).get("supports", {})
            s = float(a.get("noul", 0.0))
            label = ("supports" if s >= 0.8 else
                     "contradicts" if s <= 0.2 else
                     "inconclusive")
            return {"supports": round(s, 3), "contradicts": round(1.0 - s, 3),
                    "unknown": 0.0, "label": label, "provider": "jev-remote"}
        except Exception as e:
            logger.warning("jev verify fallback: %s", e)
            return {"supports": 0.0, "contradicts": 0.0, "unknown": 1.0,
                    "label": "no_evidence", "provider": "rules", "reason": str(e)}

    def gate(self, action: str, destructive_threshold: float = 0.85) -> Dict:
        try:
            a = self._request(f"PROPOSED ACTION: {action[:3000]}", {
                "destructive": {"type": "noul",
                                "criteria": {"true": "action destructive/irreversible", "false": "action reversible ou sure"},
                                "instructions": "Cette action est-elle destructive/irreversible (suppression, flash, format) ?"},
                "allow": {"type": "noul",
                          "criteria": {"true": "sure sans supervision", "false": "supervision recommandee"},
                          "instructions": "Cette action est-elle sure a executer sans supervision humaine ?"},
            })
            d = float(a.get("destructive", {}).get("noul", 0.0))
            allow = float(a.get("allow", {}).get("noul", 0.0))
            if d >= 0.75:
                decision = "BLOCK"
            elif d >= 0.5:
                decision = "REVIEW"
            elif allow >= 0.8:
                decision = "ALLOW"
            else:
                decision = "REVIEW"
            return {"decision": decision, "destructive_prob": d, "allow_prob": allow,
                    "provider": "jev-remote"}
        except Exception as e:
            logger.warning("jev gate fallback: %s", e)
            fb = RuleBasedProvider().gate(action, destructive_threshold)
            fb["provider"] = "rules"
            fb["reason"] = str(e)
            return fb

    def score(self, grid: Dict) -> Dict:
        """Jev Score per criterion (0..4 legend), weighted average in code."""
        criteria = {k: v for k, v in grid.items()
                    if k != "_weights" and isinstance(v, (int, float))}
        if not criteria:
            return {"score": 0.0, "label": "low", "per_criterion": {}, "provider": "jev-remote"}
        legend = ["Tres faible", "Faible", "Moyen", "Bon", "Excellent"]
        questions = {f"rate_{k}": {
            "type": "score",
            "instructions": f"Note (0=catastrophe .. 4=excellent) la qualite sur: {k}",
            "criteria": legend,
        } for k in criteria}
        try:
            crit_text = "; ".join(f"{k}={v}" for k, v in criteria.items())
            answers = self._request(f"CRITERES A NOTER: {crit_text[:3000]}", questions)
            total, per, divisor = 0.0, {}, []
            for k in criteria:
                a = answers.get(f"rate_{k}", {})
                sv = a.get("score")
                # jev score = prob-weighted mean of rubric indices, 0..n-1
                legend = a.get("legend") or {}
                max_idx = max((int(x) for x in legend.keys()), default=4) if legend else 4
                norm = float(sv) / max_idx if (sv is not None and max_idx) else \
                    float(criteria[k])  # caller-provided already 0..1
                divisor.append(max_idx)
                per[k] = round(norm, 3)
                total += norm
            s = total / len(criteria)
            label = ("high" if s >= 0.75 else "medium" if s >= 0.45 else "low")
            return {"score": round(s, 3), "label": label, "per_criterion": per,
                    "provider": "jev-remote"}
        except Exception as e:
            logger.warning("jev score fallback: %s", e)
            fb = RuleBasedProvider().score(dict(grid))
            fb["provider"] = "rules"
            fb["reason"] = str(e)
            return fb

    def decide(self, context: str, options: list) -> Dict:
        if not options:
            return {"choice": None, "distribution": {}, "confidence": 0.0,
                    "provider": "jev-remote"}
        try:
            a = self._request(f"CONTEXTE: {context[:3000]}", {
                "pick": {"type": "choice",
                         "instructions": "Quel est le meilleur choix pour le contexte donne ?",
                         "criteria": {opt: str(opt)[:200] for opt in options}},
            }).get("pick", {})
            return {"choice": a.get("choice", options[0]),
                    "distribution": a.get("probabilities", {}),
                    "confidence": a.get("confidence", 0.0),
                    "provider": "jev-remote"}
        except Exception as e:
            logger.warning("jev decide fallback: %s", e)
            return {"choice": options[0], "distribution": {}, "confidence": 0.0,
                    "provider": "rules", "reason": str(e)}
