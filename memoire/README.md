# JARVIX Memory

Système de mémoire cognitive persistante, multi-couches, pour agents IA — avec boucle fermée de vérification, expérimentation et apprentissage. 100% local (SQLite, pas de cloud), interface Python + MCP (87 outils) + web UI.

Le projet est **distribuable sans rien éditer à la main** : aucun chemin codé en dur, aucune donnée personnelle. La configuration se fait par `config.json` (local) et variables d'environnement.

## Architecture

```
                    AGENT (opencode, MCP)
                         │
                  MEMORY ROUTER
                         │
   ┌────┬────┬────┬──────┼────┬─────┬────────┐
   ▼    ▼    ▼    ▼      ▼    ▼     ▼        ▼
episodic semantic procedural decision graph + 8 autres couches
                         │
   ADMISSION → JUGEMENT (JEV) → RECHERCHE (hybride/value-coût)
                         │
   Runtime (P2.9) ← Calibration ← Observation ← Perception
                         │
      AUTOVERIFIER (preuves fichier/git/commande/mesure)
                         ↓
         EXPERIMENT (hypothèses, do_not_repeat)
                         ↓
      RECOVERY · STRATEGY · PROACTIVE · CONSOLIDATION
```

**13 couches mémoire** : episodic, semantic, procedural, decision, graph, verification/evidence, hypothesis, experiment, recovery, world, cost, strategy, environment + consolidation.

**3 cerveaux séparés** :
- **Mémoire** — conserve l'expérience et les connaissances (traceable, vérifiable)
- **LLM** (optionnel) — génère, explique, résume
- **JEV** — juge rapidement via des primitives typées (Choice/Score/Gate), sans texte, seuils dans le code

## Démarrage rapide

```bash
# Installation (Python >= 3.10)
pip install -e .

# Pour la recherche vectorielle + l'UI
pip install -e ".[vector,ui]"
pytest tests/            # 29 tests unitaires → OK
```

### CLI

```bash
python memoire.py add "<contenu>" --type semantic --source "<src>"
python memoire.py search "<termes>"   # AND implicite, fallback OR
python memoire.py stats | list | get <id>
python memoire.py decision "<quoi>" "<pourquoi>"
python memoire.py episodic "<action>" "<resultat>"
```

### Interface web

```bash
python -m jarvix_memory.ui.app          # http://127.0.0.1:5000
# recherche hybride, chat RAG, couches, fichiers, llama.cpp, device adb, bilan, autopush GitHub
```

### Serveur MCP (pour agents type opencode)

```json
{ "mcpServers": { "jarvix-memory": {
    "command": "python", "args": ["mcp_server.py"], "cwd": "<chemin-du-programme>"
}}}
```

**87 MCP tools** organisés en 20 familles : core (5), episodic (2), semantic (2), graph (2), decision (2), procedural (2), verification (3), action (6), strategy (5), learning (3), recovery (5), proactive (5), world model (7), consolidation (1), CRUD (3), bilan (1), vector (3), embeddings (2), LLM reasoning (4), verify_auto (11), env/experiment (10), P1 cost/strategy/monitor (5), P2 perception/quant/jev (8), autopilot git (1).

Exécumentos clés :

| Famille | Outils | Ce qu'ils font |
|---|---|---|
| Vérification auto | `verify_auto` | Préuves déterministes zero-LLM : file_exists, file_contains, git_diff, command, measurement → verified/rejected |
| Environment | `env_capture/…` | Snapshot OS/python/git, fingerprint, diff — résultats attachés à leur environnement |
| Expérience | `hyp_*` | hypothèse → expériences → **confirmé/réfuté** ; piste déjà réfutée → `do_not_repeat` (garde anti re-test) |
| Cost-aware | `recall_cost` | Recherche classée par **valeur/coût** (tokens attendus, utility), budget à injecter |
| Recovery | `recovery_*` | Échec → diagnostic → **hypothèse changée obligatoirement** → retry |
| Proactive | `proactive_monitor` | Interruption **silencieuse par défaut** : n'alerte que sur une piste réfutée en cours de re-test |
| JEV | `jev_*` | Primitives typées : choix de route, gate destructive (ALLOW/REVIEW/BLOCK), score pondéré, choix d'option |
| Perception | `perceive_file` | Log/PDF/image → signaux (SIGSEGV, OOM, thermal, tok/s…) + signature sha256 → observation épisodique |
| Autopilot | `autopush` | Export du souvenir groupé par `project_id` → commit + push GitHub |

## Apprendre sans fine-tuning

```python
# Déclarer une hypothèse testable, l'expérimenter, la réfuter — le système n'oublie jamais
hyp = router.experiment.propose_hypothesis("mmap causes the reboot")
router.experiment.run_experiment(hyp["id"], "test-A", "no effect", success=False, env_id=env["env_id"])
router.experiment.conclude(hyp["id"], "refuted")   # do_not_repeat activé

# Avant un re-test : JARVIX bloque les pistes déjà réfutées
router.experiment.repeat_guard("mmap causes the reboot")   # → {"blocked": true, ...}
```

## Configuration (aucun chemin hardcodé)

Tout est dérivé de **l'environnement** :

- `jarvix_memory.db` : DB SQLite locale, créée à côté du paquet au premier appel ; migrée automatiquement (versionning `schema_version`, actuellement v4).
- **Variables d'environnement** (optionnelles) :
  - `JARVIX_PROJECT_ROOT` — racine du projet à scanner dans les bilans (défaut : cwd)
  - `JARVIX_REPORTS_DIR` — où écrire les rapports (défaut : `reports/` dans le paquet)
  - `JARVIX_LLAMA_URL` — URL llama.cpp (défaut `http://127.0.0.1:8080`)
- **`config.json`** (créé à la première sauvegarde, tenu privé : dans `.gitignore`) :
  ```json
  { "llama_exe": "/chemin/vers/llama-server.exe", "gguf_dirs": ["/mes/modeles"], "llama_port": 8080 }
  ```
- `config.example.json` donne le template committé, sans data perso.

## Tests

```bash
pytest tests/test_core.py -q       # 29 tests unitaires
python test_all_tools.py           # 87/87 MCP tools vérifiés end-to-end
```

## Git autopilot

`autopush(project_id="X")` exporte les souvenirs du projet vers `docs/memoire_<project>.md`, commit et pousse vers `origin main`. La base SQLite elle-même ne quitte jamais la machine — uniquement le markdown exporté.

## Ce que le projet fait / ne fait pas

**Fait** : mémoire persistante par couches, preuves et provenance, vérification déterministe, mémoire négative (hypothèses réfutées + garde), reconnaissance d'environnement, sélection de stratégie selon coût, prompts sélectifs, JEV de jugement, perception log/fichiers, autopush git per-project.

**Ne fait pas** : LLM (il en fournit la mémoire), agent autonome, recherche web, garant de vérité, base vectorielle seule, fine-tuning de modèle, substitution au système de fichiers.

## Structure

- `src/jarvix_memory/core/` — database, models, migration (v4), environment, cost, autopilot
- `src/jarvix_memory/{episodic,semantic,procedural,decision,graph}/` — couches mémoires
- `src/jarvix_memory/{verification,experiment}/` — claims → preuve → verdict ; hypothèses → expériences
- `src/jarvix_memory/{action,strategy,learning,recovery,proactive,world,multimodal,consolidation}/`
- `src/jarvix_memory/llm/` — raisonnement RAG optionnel (llama.cpp/OpenAI-compat)
- `src/jarvix_memory/ui/` — dashboard Flask
- `mcp_server.py`, `memoire.py` (CLI), `bilan.py` (rapport autonome)
- `docs/` — exports autopush ; `.gitignore` protège `config.json`, DB, logs
