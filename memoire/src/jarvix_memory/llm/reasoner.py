"""LLM Reasoner — connects to local llama.cpp or OpenAI-compatible server."""

import json
import logging
import urllib.request
import urllib.error
from typing import List, Dict, Optional
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:8080"


class LLMReasoner:
    """RAG pipeline: query → retrieve memories → reason → respond."""

    def __init__(self, db: "Database", vector_store=None, base_url: str = DEFAULT_BASE_URL):
        self.db = db
        self.vector_store = vector_store
        self.base_url = base_url

    def _chat(self, messages: List[Dict], max_tokens: int = 1024, temperature: float = 0.3) -> str:
        """Send chat completion request to local LLM."""
        payload = json.dumps({
            "model": "local",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                content = msg.get("content", "") or ""
                reasoning = msg.get("reasoning_content", "") or ""
                return content or reasoning
        return ""

    def _retrieve(self, query: str, limit: int = 5) -> List[Dict]:
        """Retrieve relevant memories via vector search or LIKE fallback."""
        if self.vector_store:
            results = self.vector_store.search(query, limit=limit, min_score=0.2)
            if results:
                return results
        # Fallback to LIKE search
        return self.db.search_fts(query, limit=limit)

    def _build_context(self, memories: List[Dict]) -> str:
        """Build context string from retrieved memories."""
        if not memories:
            return "Aucune mémoire pertinente trouvée."

        lines = []
        for i, mem in enumerate(memories, 1):
            score = mem.get("_score", "")
            score_str = f" [score={score}]" if score else ""
            content = (mem.get("content", "") or "")[:300]
            mem_type = mem.get("type", "unknown")
            lines.append(f"{i}. [{mem_type}]{score_str} {content}")

        return "\n".join(lines)

    def reason(self, query: str, max_tokens: int = 1024, temperature: float = 0.3,
               live_max_tokens: int = 1200) -> Dict:
        """RAG + LIVE: retrieve memories + bundle the real-time state into context."""
        # 1. Retrieve
        memories = self._retrieve(query)
        context = self._build_context(memories)

        # 1b. live context bundle (state NOW: inventories/hypotheses/recoveries)
        live_part = ""
        try:
            from ..core.livectl import LiveContext
            live = LiveContext(self.db)
            b = live.bundle(query, max_tokens=live_max_tokens)
            if b["status"] == "OK_RELIABLE":
                lines = []
                for it in b["items"]:
                    if it["kind"] == "inventory":
                        lines.append(f"- [INVENTAIRE] {it['root']} : {it['files']} fichiers — "
                                     f"{it['summary'][:140]}")
                    elif it["kind"] == "hypothesis":
                        lines.append(f"- [{it['status']}] {it['content']}")
                    elif it["kind"] == "recovery":
                        lines.append(f"- [ECHEC ACTIF] {it['content']}")
                    else:
                        lines.append(f"- [{it.get('conf', '')}] {it.get('content', '')[:180]}")
                live_part = "## CONTEXTE LIVE DU PROJET\n" + "\n".join(lines)
        except Exception as e:
            logger.warning("live bundle indisponible: %s", e)

        # 2. Build prompt
        messages = [
            {
                "role": "system",
                "content": (
                    "Tu es JARVIX, un assistant IA spécialisé dans la mémoire cognitive. "
                    "Tu as accès au contexte LIVE du projet (inventaires disque récents, hypothèses "
                    " réfutées à ne pas re-tester, échecs en cours). Utilise-le pour répondre de "
                    "manière précise et concise. Cite les sources quand pertinent. Réponds en français."
                ),
            },
            {
                "role": "user",
                "content": f"{live_part}\n\n{context}\n\n## Question\n{query}",
            },
        ]

        # 3. Reason
        try:
            response = self._chat(messages, max_tokens=max_tokens, temperature=temperature)
        except Exception as e:
            logger.error("LLM reasoning failed: %s", e)
            response = f"[LLM indisponible: {e}]"

        return {
            "query": query,
            "response": response,
            "memories_used": len(memories),
            "memory_ids": [m.get("id") for m in memories],
            "live": bool(live_part),
        }

    def summarize(self, text: str, max_tokens: int = 256) -> str:
        """Summarize text using LLM."""
        messages = [
            {"role": "system", "content": "Résume en 3-5 lignes. Sois précis et concis."},
            {"role": "user", "content": text},
        ]
        try:
            return self._chat(messages, max_tokens=max_tokens)
        except Exception as e:
            return f"[Erreur: {e}]"

    def find_connections(self, memory_id: str) -> Dict:
        """Find connections between a memory and others."""
        mem = self.db.get_memory(memory_id)
        if not mem:
            return {"error": "memory not found"}

        content = mem.get("content", "")
        related = self._retrieve(content, limit=5)
        # Exclude self
        related = [r for r in related if r.get("id") != memory_id]

        if not related:
            return {"connections": [], "summary": "Aucune connexion trouvée."}

        context = self._build_context(related)
        messages = [
            {
                "role": "system",
                "content": "Identifie les connexions entre la mémoire source et les mémoires liées. Sois bref.",
            },
            {
                "role": "user",
                "content": f"Source: {content[:500]}\n\nLiées:\n{context}",
            },
        ]

        try:
            summary = self._chat(messages, max_tokens=512)
        except Exception as e:
            summary = f"[Erreur: {e}]"

        return {
            "source_id": memory_id,
            "related_ids": [r.get("id") for r in related],
            "connections": related,
            "summary": summary,
        }

    def health(self) -> Dict:
        """Check LLM server health."""
        try:
            req = urllib.request.Request(f"{self.base_url}/v1/models", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = data.get("data", [])
                return {
                    "available": True,
                    "model": models[0].get("id", "unknown") if models else "unknown",
                    "url": self.base_url,
                }
        except Exception:
            return {"available": False, "url": self.base_url}
