# Architecture op15-suite

## Vue d'ensemble

```
┌────────────────────────────────────────────────────────────┐
│                      op15 (CLI unifié)                      │
│  doctor · smoke · rag · learn · report · gguf · bilan ·     │
│  campaign                                                   │
└──────┬──────────┬──────────┬───────────┬──────────┬────────┘
       │          │          │           │          │
   mcp_doctor  test_upia  forensics/  report_    campaign_moe
   (.json)     smoke      rag_bm25    pipeline   (harness)
       │                      │
   4 MCP registre        memory.db
   (graft, jarvix,       (RAG: sources,
   upia, recall)          entités, hypothèses,
                          procédures)
                            │
              ┌─────────────┼──────────────┐
          JARVIX         UPIA           RAG
      memoire/         (harness)     forensics/
   mémoire gouvernée   timeline      preuves +
   (semantic,          datée         procédures
   decision, proc,
   recovery, world…)
```

## Les 3 mémoires

| Mémoire | Stockage | Force | Quand l'utiliser |
|---|---|---|---|
| **JARVIX** | `memoire/jarvix_memory.db` (SQLite, FTS5, embeddings) | typée + gouvernée (provisional→verified→invalid, consolidation, stratégies, recovery) | faits vérifiés, décisions, procédures validées |
| **UPIA** | store harness (`governor_state/upia`) | axe du temps (events/commits/docs, révisions de conclusions) | « que savait-on à la date X ? » |
| **RAG forensics** | `tools/forensics/memory.db` | corrélations + hypothèses auditées + procédures statutées | questions pipeline/failles/CVEs |

## Frontières (volontaires)

- **Hors repo** : harness geniex (`E:/oneplus/geniex_harness`, artefacts lourds),
  worktree `ab-wt`, SDK Hexagon, modèles GGUF, device_logs. Le CLI `campaign`
  y pointe via `--harness`.
- **DB runtime ignorées** par git (dérivables par ingestion) — le repo porte le
  **code + docs + scripts**, jamais l'état.

## Diagnostic en 3 niveaux (mcp_doctor)

1. **handshake** `initialize` — le serveur démarre comme opencode le lance
2. **tools/list** — le contrat d'outils est là (jarvix 88, upia 7, recall 3)
3. **sonne réelle** — un appel lecture seule passe (mémoire lisible, store à jour,
   index RAG chargé : cold-start ~15 s pour unified_recall, timeout 45 s)
