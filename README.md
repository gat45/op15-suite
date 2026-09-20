# op15-suite

![CI mcp-doctor](https://github.com/gat45/op15-suite/actions/workflows/doctor.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

OnePlus 15 (CPH2747 / SM8850) knowledge & MoE pipeline — mémoire gouvernée,
RAG forensics, diagnostic MCP, campagne MoE sur device.

## Contenu

| Dossier | Rôle |
|---|---|
| `op15suite/` | CLI unifié (`op15 …`) |
| `tools/mcp_doctor.py` | santé des 4 MCP : handshake JSON-RPC réel + sonne d'appel outil + `--json` |
| `tools/test_upia_mcp.py` | non-régression serveur MCP upia (mode `smoke` 4 outils ~1 s) |
| `tools/report_pipeline.py` | pipeline 3 mémoires (RAG + UPIA + JARVIX) sur un rapport `.md` |
| `tools/gguf_arch.py` | lecture arch GGUF (diagnostic build/type quant) |
| `tools/forensics/` | RAG forensics autonome (ingestion, corrélations, hypothèses, procédures) |
| `memoire/` | JARVIX : mémoire gouvernée (88 outils, FTS5, embeddings, consolidation) |
| `scripts/` | installation & vérification |
| `docs/` | architecture & usage |
| `examples/` | requêtes RAG et exemples de rapports |

## Installation (Windows)

```bash
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e .
scripts/install.ps1        # vérifie prérequis + index JARVIX
```

## Démarrage rapide

```bash
op15 doctor               # 4 MCP : handshake + sonde réelle (all_green ?)
op15 smoke                # non-régression upia
op15 rag "root invisible SUSFS play integrity" --top 3
op15 learn D:/mon/dossier/de/docs
op15 report RAPPORT_xxx.md
op15 gguf modele.gguf
op15 bilan
op15 campaign --list      # gates §8.1-4 (device requis + harness local)
```

## Notes

- `memoire/` (JARVIX) embarque sa DB locale : recréée à la première écriture ;
  `memoire/config.json` peut pointer vers des chemins externes.
- Le RAG forensics crée `memory.db` à l'ingestion ; le RAG du projet réel
  (`op15-forensics`) reste la source de vérité de production.
- `op15 campaign` pointe par défaut vers `E:/oneplus/geniex_harness`
  (`--harness` pour surcharger) — le harness reste hors repo (gros artefacts).
- Serveurs MCP attendus par `doctor` : registre canonique `opencode.json`
  (graft, jarvix-memory, upia, unified_recall) — voir `docs/ARCHITECTURE.md`.
