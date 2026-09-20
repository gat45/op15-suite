"""
rag_bm25.py — Recherche & Génération Augmentée par Récupération (RAG)
sur la mémoire persistée du pipeline OnePlus 15.

Deux briques :
  1. BM25 : index inversé sur le texte nettoyé des sources ingérées
     (memory.db -> table sources). Retourne les documents pertinents
     pour une requête, avec un score BM25.
  2. RAG  : assemble une réponse ancrée : snippets des documents
     pertinents (preuves) + procédures du catalogue op15_domain qui
     correspondent à la requête. Chaque preuve cite sa source.

Usage :
    python rag_bm25.py "comment rooter le CPH2747 ?"
    python rag_bm25.py "unbrick EDL 9008" --json
    python rag_bm25.py "init_boot" --top 5
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from agent_extractor import clean_html
from memory_store import MemoryStore
import op15_domain


@dataclass
class IndexedDoc:
    id: int
    url: str
    title: str
    text: str
    length: int = 0
    tokens: list[str] = field(default_factory=list)


@dataclass
class Retrieved:
    doc: IndexedDoc
    score: float
    snippet: str = ""


@dataclass
class RagResult:
    question: str
    answer: str
    evidence: list[Retrieved] = field(default_factory=list)
    procedures: list[dict] = field(default_factory=list)
    vulns: list[dict] = field(default_factory=list)
    duration_ms: float = 0.0


# --- Tokenisation -----------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_ACCENTS = str.maketrans(
    "àâäéèêëîïôöùûüçñ", "aaaeeeeiioouuucn")
# Emojis / symboles décoratifs : jamais utiles pour la réponse console
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF"
    "\U00002190-\U000021FF\U00002300-\U000023FF\u2705\u2714\u2716\u2600"
    "\u2601\u260E\u2611\u274C\u274E\u2B50\u2764\u2728]"
)


def _sanitize(text: str) -> str:
    return _EMOJI_RE.sub("", text)


def tokenize(text: str) -> list[str]:
    """Minuscules + accents translittérés + mots alphanumériques."""
    t = text.lower()
    t = t.translate(_ACCENTS)
    return _TOKEN_RE.findall(t)


STOPWORDS_BM25 = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "a",
    "au", "aux", "en", "sur", "dans", "pour", "par", "avec", "sans", "que",
    "qui", "quoi", "ce", "cet", "cette", "ces", "est", "sont", "etait",
    "the", "and", "of", "to", "in", "on", "at", "for", "from", "is", "are",
    "comment", "quel", "quelle", "quels", "quelles", "pourquoi", "avec",
    "peut", "peuvent", "vous", "jai", "pas", "plus", "tout", "tous", "mais",
    "comme", "si", "non", "oui", "the", "was", "were", "be", "been", "this",
    "that", "with", "it", "i", "how", "what", "where", "when", "do", "does",
    "je", "tu", "il", "elle", "nous", "ils", "elles", "faire", "fait",
}


def _query_terms(query: str) -> list[str]:
    return [t for t in tokenize(query) if t not in STOPWORDS_BM25 and len(t) >= 2]


# --- BM25 -------------------------------------------------------------------

class BM25Index:
    """Index BM25 (Okapi BM25) construit depuis la mémoire persistée."""

    def __init__(self, memory: MemoryStore, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: list[IndexedDoc] = []
        self.doc_freq: Counter[str, int] = Counter()
        self.avgdl = 0.0
        self._build(memory)

    def _build(self, memory: MemoryStore):
        rows = memory.conn.execute(
            "SELECT id, url, title, raw_text FROM sources").fetchall()
        total_len = 0
        for r in rows:
            text = clean_html(r["raw_text"] or "")
            tokens = tokenize(text)
            # B4 (audit 2026-08-18) : mémorise les tokens une seule fois au build ;
            # search() les réutilise au lieu de re-tokeniser tout le corpus à chaque requête.
            doc = IndexedDoc(id=r["id"], url=r["url"] or "",
                             title=r["title"] or "", text=text,
                             length=len(tokens), tokens=tokens)
            total_len += doc.length
            for t in set(tokens):
                if t not in STOPWORDS_BM25:
                    self.doc_freq[t] += 1
            self.docs.append(doc)
        self.avgdl = (total_len / len(self.docs)) if self.docs else 0.0

    def _idf(self, term: str) -> float:
        n = len(self.docs)
        df = self.doc_freq[term]
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 5) -> list[Retrieved]:
        terms = _query_terms(query)
        if not terms or not self.docs:
            return []
        scores = []
        for doc in self.docs:
            tf = Counter(t for t in doc.tokens if t not in STOPWORDS_BM25)
            score = 0.0
            for t in terms:
                if t not in tf:
                    continue
                idf = self._idf(t)
                num = tf[t] * (self.k1 + 1)
                denom = tf[t] + self.k1 * (
                    1 - self.b + self.b * doc.length / self.avgdl)
                score += idf * num / denom
            if score > 0:
                scores.append((doc, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [self._with_snippet(doc, score, terms)
                for doc, score in scores[:top_k]]

    @staticmethod
    def _with_snippet(doc: IndexedDoc, score: float, terms: list[str]) -> Retrieved:
        text = _sanitize(doc.text)
        # fenêtre de contexte autour du premier terme trouvé
        idx = -1
        for t in terms:
            found = text.lower().find(t)
            if found != -1:
                idx = found
                break
        if idx == -1:
            idx = 0
        start = max(0, idx - 180)
        end = min(len(text), idx + 400)
        snippet = ("..." if start > 0 else "") + text[start:end] + \
                  ("..." if end < len(text) else "")
        return Retrieved(doc=doc, score=round(score, 3), snippet=snippet)


# --- RAG (assemblage ancré) -------------------------------------------------

_ASPECT_LABELS = {
    "bootloader": "Déverrouillage du bootloader",
    "root": "Root / superutilisateur",
    "firmware": "Firmware / ROM / OTA",
    "reparation": "Réparation / unbrick",
    "amelioration": "Améliorations / custom",
    "hardware": "Matériel / réparation physique",
}


def _match_procedures(query: str, top: int = 5) -> list[dict]:
    """Retourne les procédures du catalogue dont les mots-clés correspondent."""
    terms = set(_query_terms(query))
    scored = []
    for name, p in op15_domain.PROCEDURES.items():
        hay = " ".join([
            name.replace("_", " "), p["aspect"], p["contract"],
            " ".join(p["steps"]), " ".join(p["risks"]),
        ])
        hay_tokens = set(tokenize(hay))
        hits = len(terms & hay_tokens)
        if hits > 0:
            scored.append((hits, name, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for hits, name, p in scored[:top]:
        out.append({
            "name": name, "aspect": p["aspect"],
            "status": p["status"], "hits": hits,
            "steps": p["steps"], "risks": p["risks"],
            "source_refs": p["source_refs"],
            "contract": p["contract"],
        })
    return out


_VULN_FAM_LABELS = {
    "bootchain_software": "Bootchain / logiciel OP15",
    "soc_qualcomm": "SoC Qualcomm SM8850",
    "android": "Android / système",
    "hardware": "Matériel",
}


def _match_vulns(query: str, top: int = 5) -> list[dict]:
    """Retourne les failles du catalogue dont label/vecteur/impact/CVEs matchent."""
    terms = set(_query_terms(query))
    scored = []
    for name, v in op15_domain.VULNS.items():
        hay = " ".join([
            v["label"], v["famille"], v["vecteur"], v["impact"],
            " ".join(v["cves"]), " ".join(v["axes"]),
            " ".join(v["cibles"]), " ".join(v["procedures"]),
            v.get("utilite", ""), v.get("determination", ""),
        ])
        hay_tokens = set(tokenize(hay))
        hits = len(terms & hay_tokens)
        if hits > 0:
            scored.append((hits, name, v))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for hits, name, v in scored[:top]:
        out.append({
            "id": name,
            "label": v["label"],
            "famille": _VULN_FAM_LABELS.get(v["famille"], v["famille"]),
            "status": v["status"],
            "hits": hits,
            "cibles": v["cibles"],
            "cves": v["cves"],
            "vecteur": v["vecteur"],
            "impact": v["impact"],
            "procedures": v["procedures"],
            "utilite": v.get("utilite", ""),
            "determination": v.get("determination", ""),
        })
    return out


def _build_answer(question: str, evidence: list[Retrieved],
                  procedures: list[dict], vulns: list[dict]) -> str:
    lines = [f"Question : {question}", ""]
    if evidence:
        lines.append("Preuves extraites de la mémoire (BM25) :")
        for e in evidence:
            lines.append(f"  - [{e.doc.title or e.doc.url}] (score {e.score})")
            lines.append(f"      {e.snippet.strip()}")
        lines.append("")
    if procedures:
        lines.append("Procédures du catalogue correspondantes :")
        for p in procedures:
            label = _ASPECT_LABELS.get(p["aspect"], p["aspect"])
            lines.append(f"  - {p['name']} [{label}] — statut `{p['status']}`")
            lines.append(f"      Contrat : {p['contract']}")
            lines.append(f"      Étapes : {len(p['steps'])} ; Risques : {len(p['risks'])}")
        lines.append("")
    if vulns:
        lines.append("Failles du catalogue correspondantes :")
        for v in vulns:
            lines.append(f"  - {v['label']} [{v['famille']}] — `{v['status']}`")
            if v["cves"]:
                lines.append(f"      CVEs : {', '.join(v['cves'])}")
            lines.append(f"      Vecteur : {v['vecteur']}")
            lines.append(f"      Impact : {v['impact']}")
            lines.append(f"      Cibles : {', '.join(v['cibles'])}")
            if v["procedures"]:
                lines.append(f"      Procédures liées : {', '.join(v['procedures'])}")
            if v.get("utilite"):
                lines.append(f"      Utilité : {v['utilite']}")
            if v.get("determination"):
                lines.append(f"      Détermination : {v['determination']}")
        lines.append("")
    if not evidence and not procedures and not vulns:
        lines.append("Aucune preuve ni procédure trouvée dans la mémoire.")
    lines.append("Avertissement : synthèse ancrée sur des sources publiques ; "
                 "aucune étape n'est une instruction opérationnelle.")
    return "\n".join(lines)


def rag_answer(memory: MemoryStore, question: str, top_k: int = 5,
               top_proc: int = 5) -> RagResult:
    import time
    t0 = time.time()
    index = BM25Index(memory)
    evidence = index.search(question, top_k=top_k)
    procedures = _match_procedures(question, top=top_proc)
    vulns = _match_vulns(question, top=top_proc)
    answer = _build_answer(question, evidence, procedures, vulns)
    return RagResult(
        question=question, answer=answer, evidence=evidence,
        procedures=procedures, vulns=vulns,
        duration_ms=round((time.time() - t0) * 1000, 1),
    )


def _render(result: RagResult) -> str:
    head = (f"== RAG / BM25 — {result.question} "
            f"({result.duration_ms:.0f} ms, {len(result.evidence)} preuve(s), "
            f"{len(result.procedures)} procédure(s), {len(result.vulns)} faille(s)) ==")
    return head + "\n\n" + result.answer


def main():
    ap = argparse.ArgumentParser(
        description="RAG + BM25 sur la mémoire OnePlus 15")
    ap.add_argument("question", help="question ou requête de recherche")
    ap.add_argument("--top", type=int, default=5,
                    help="nombre de documents preuves (défaut 5)")
    ap.add_argument("--proc", type=int, default=5,
                    help="nombre de procédures liées (défaut 5)")
    ap.add_argument("--json", action="store_true",
                    help="sortie JSON structurée")
    args = ap.parse_args()

    # stdout en UTF-8 pour éviter les erreurs d'encodage console (cp1252)
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    memory = MemoryStore()
    try:
        result = rag_answer(memory, args.question, top_k=args.top,
                            top_proc=args.proc)
        if args.json:
            print(json.dumps({
                "question": result.question,
                "duration_ms": result.duration_ms,
                "evidence": [{
                    "title": e.doc.title, "url": e.doc.url,
                    "score": e.score, "snippet": e.snippet,
                } for e in result.evidence],
                "procedures": result.procedures,
                "answer": result.answer,
            }, ensure_ascii=False, indent=2))
        else:
            print(_render(result))
    finally:
        memory.close()


if __name__ == "__main__":
    sys.exit(main())
