# OPMAP — carte de lancement pour agents sans contexte

Tu es un agent LLM qui découvre ce repo sans historique. Voici tout ce qu'il
faut, dans l'ordre. **Règle d'or : ne déduis rien de la mémoire — mesure.**

## 0. La seule commande de démarrage

```bash
op15 status
```

Elle teste : repo complet, registre MCP, **device OP15 (adb)**, harness,
LLM local (:18181), mémoires (JARVIX/RAG). Elle affiche ensuite la
**prochaine action conseillée** — suis-la, ne devine pas.

## 1. Symptôme → commande (jamais d'exploration ad hoc)

| Symptôme / besoin | Commande |
|---|---|
| « qu'est-ce qui tourne ? » | `op15 status` |
| « les MCP répondent-ils vraiment ? » | `op15 doctor` (handshake + sonde outil réelle) |
| rapport JSON pour audit | `op15 doctor --json --out dr.json` puis `python tools/validate_doctor_report.py dr.json --registry opencode.json` |
| question de connaissance pipeline/device | `op15 rag "<question>" --top 3` |
| nouveau dossier de docs à ingérer | `op15 learn <dossier>` |
| rapport de session → 3 mémoires | `op15 report RAPPORT_xxx.md` |
| GGUF suspect / garbage « ? » | `op15 gguf <fichier.gguf>` (lit l'arch — le build doit la connaître) |
| bilan mémoire JARVIX | `op15 bilan` |
| campagne MoE §8.1-4 (device branché) | `op15 campaign --model <GGUF>` |
| voir les gates sans device | `op15 campaign --list` |
| smoke upia sans LLM (~1 s) | `op15 smoke` |

## 2. Pièges connus (déjà vécus — ne les re-découvre pas)

1. **unified_recall répond au handshake mais sa 1re recherche prend 15–25 s**
   (cold-start index). Ce n'est pas un hang — timeout 45 s côté doctor.
2. **Port mort sous Windows = hang de 90–120 s**, pas un refus instantané.
   Un health-check 2 s existe côté upia (`llm_available()`).
3. **Le patch expert-trace vit dans la variante dspqueue** (`ggml-hexagon.cpp`) ;
   la campagne mempool compile `ggml-hexagon-fastrpc.cpp` — vérifier le portage
   avant G3, sinon 0 événement de trace.
4. **`campaign_moe.py` du repo = copie vendor** (CI) — la version canonique est
   dans le harness (`--harness`). Ne patche pas la copie vendor.
5. **DB runtime ignorées par git** (dérivables) : JARVIX se recrée à la 1re
   écriture, le RAG par ingestion (`op15 learn`). Un DB absente n'est pas une
   panne.
6. **Secrets** : `memoire/config.json` contient des placeholders. Toute vraie clé
   va dans l'env, jamais dans le repo (`tools/secret_scan.py` existe).
7. **Env var utile** : `OP15_HARNESS` surcharge le chemin du harness pour
   `status`/`campaign`.

## 3. Chaîne de vérité (qui prime sur quoi)

RAG/procédures > savoir générique du modèle. Mémoire JARVIX > re-lecture de
rapports. `status`/`doctor` > toute supposition sur l'état d'un service.
Le governor n'accepte que des métriques passées par les gates (REFUSED sans
preuve device = comportement correct, pas un bug).

## 4. Après toute modification

```bash
op15 doctor && op15 smoke        # non-régression minimale
```

Puis commit. La CI GitHub (install 2 OS + schéma du rapport + nightly §8)
est le filet : laisse-la verte.
