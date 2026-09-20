"""P1.4 — Cost-aware recall: value = relevance x confidence x utility / token cost.

Cost lives on every memory (cost_tokens, cost_ram, utility). A retrieval that
returns a 4 KB wall of text at score 0.5 is worse than 200 bytes at score 0.45
when the budget is tight. This module computes both sides.
"""

import json
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

TOKENS_PER_CHAR = 0.25  # ~4 chars per token, English/tech text


def estimate_cost(mem: Dict) -> int:
    content = mem.get("content", "") or ""
    return max(1, int(len(content) * TOKENS_PER_CHAR) + int(mem.get("cost_tokens", 0) or 0))


def score(mem: Dict, relevance: float) -> float:
    """value/cost score. Higher is better to inject."""
    cost = estimate_cost(mem)
    confidence = mem.get("confidence", 0.5) or 0.5
    utility = mem.get("utility", 0.0) or 0.0
    # value grows with relevance, trust and past usefulness; cost shrinks it (1 + tokens/200)
    return round(relevance * (confidence + utility) / (1.0 + cost / 200.0), 6)


def cost_report(mem: Dict) -> Dict:
    return {
        "tokens": estimate_cost(mem),
        "ram_kb": round(len(json.dumps(mem)) / 1024, 2),
        "confidence": mem.get("confidence", 0.5),
        "utility": mem.get("utility", 0.0),
    }


def rerank(memories: List[Dict], relevance_fn) -> List[Dict]:
    """Re-rank memories by value/cost. relevance_fn(mem) -> float 0..1."""
    scored = []
    for m in memories:
        v = score(m, relevance_fn(m))
        m["_value"] = v
        m["_cost_tokens"] = estimate_cost(m)
        scored.append(m)
    scored.sort(key=lambda x: x["_value"], reverse=True)
    return scored


def record_usage(db, memory_id: str, used: bool = True) -> bool:
    """Positive reinforcement: a memory that got used gains utility."""
    mem = db.get_memory(memory_id)
    if not mem:
        return False
    if used:
        db.update_memory(memory_id, utility=min(1.0, (mem.get("utility", 0.0) or 0.0) + 0.1))
    return True
