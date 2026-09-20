"""Serveur MCP upia — expose la mémoire temporelle UPIA comme outils natifs opencode.

upia (Universal Project Intelligence Agent) vit dans E:\\oneplus\\geniex_harness
(Python 3.12, installé en package). Ce serveur délègue au CLI
``governor.upia.upia.cli`` via subprocess et hérite de l'environnement
UPIA_LLM_URL / UPIA_LLM_KEY / UPIA_LLM_MODEL / UPIA_LLM_THINK pour la synthèse LLM.

Store utilisé : le store canonique du projet `governor_state/upia` (même choix que
`py -m governor upia`), synchronisé avec ~/.upia le 2026-09-20
(1232 events, 606 claims — backup de l'ancien : *.bak_20260920).
"""
from __future__ import annotations

import os
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

# Windows : stdout par défaut cp1252 → UnicodeEncodeError sur les réponses non-ASCII.
# Le protocole MCP est du JSON unicode : forcer UTF-8 sur les deux flux.
for _s in (sys.stdout, sys.stderr):
    try:
        if _s.encoding and _s.encoding.lower().replace("-", "") != "utf8":
            _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

HARNESS = r"E:\oneplus\geniex_harness"
DEFAULT_TARGET = HARNESS
STORE_BASE = r"E:\oneplus\geniex_harness\governor_state\upia"
PY = sys.executable  # le Python 3.12 qui a upia installé

mcp = FastMCP(
    "upia",
    instructions=(
        "Mémoire temporelle UPIA du projet geniex_harness. Utilise upia_ask pour "
        "toute question d'historique (« qu'est-ce qui a changé », conclusions, "
        "dates), upia_update après une session de travail pour ingérer les nouveaux "
        "événements, upia_unknown pour voir les trous de connaissance."
    ),
)


def _run(args: list[str], timeout: int = 180) -> str:
    """Exécute le CLI upia dans le harness et renvoie sa sortie (stdout d'abord)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "UPIA_STORE": STORE_BASE}
    try:            p = subprocess.run(
                [PY, "-m", "governor.upia.upia.cli", *args],
                cwd=HARNESS, env=env, capture_output=True,
                stdin=subprocess.DEVNULL,  # sinon l'enfant hérite du stdin MCP (pipe sans EOF) et bloque
                text=True, encoding="utf-8", errors="replace", timeout=timeout,
            )
    except subprocess.TimeoutExpired:
        return f"ERREUR: timeout {timeout}s sur upia {' '.join(args[:2])}"
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    return out if out else (err or "(aucune sortie)")


@mcp.tool()
def upia_ask(question: str, target: str = DEFAULT_TARGET) -> str:
    """Pose une question d'historique au projet (réponse avec provenance, sources et citations)."""
    return _run(["ask", question, target], timeout=300)


@mcp.tool()
def upia_status(target: str = DEFAULT_TARGET) -> str:
    """État du modèle temporel : compteurs (events, commits, docs), vocabulaire, structure."""
    return _run(["status", target])


@mcp.tool()
def upia_events(target: str = DEFAULT_TARGET, since: str = "") -> str:
    """Événements récents du projet (optionnel : since au format YYYY-MM-DD)."""
    args = ["events", target]
    if since:
        args += ["--since", since]
    return _run(args, timeout=120)


@mcp.tool()
def upia_graph(target: str = DEFAULT_TARGET) -> str:
    """Graphe entités/relations extraites du projet."""
    return _run(["graph", target], timeout=120)


@mcp.tool()
def upia_unknown(target: str = DEFAULT_TARGET) -> str:
    """Registre des inconnus : ce que upia ne sait pas encore (INSUFFICIENT_INFO, STALE...)."""
    return _run(["unknown", target], timeout=120)


@mcp.tool()
def upia_update(target: str = DEFAULT_TARGET, commits: int = 0) -> str:
    """Ingère les nouveaux événements git/fichiers/docs (idempotent). commits: nb de commits (0=défaut)."""
    args = ["update", target]
    if commits:
        args += ["--commits", str(commits)]
    return _run(args, timeout=600)


@mcp.tool()
def upia_research(query: str, target: str = DEFAULT_TARGET) -> str:
    """Recherche externe (arXiv/GitHub) pour combler les inconnus du projet."""
    return _run(["research", query, target], timeout=300)


if __name__ == "__main__":
    mcp.run()
