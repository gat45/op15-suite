# Exemples d'usage op15-suite

## Diagnostic boot (à lancer à chaque session)

```bash
op15 doctor                          # verdict texte par serveur
op15 doctor --json --out doctor.json # rapport JSON (CI / rapport de session)
```

## Connaissance

```bash
# interroger le RAG forensics
op15 rag "unbrick EDL 9008" --top 3
op15 rag "root invisible SUSFS play integrity"

# ingérer un nouveau dossier de docs
op15 learn D:/mes/nouveaux/rapports

# passer un rapport de session dans les 3 mémoires
op15 report RAPPORT_SESSION_xxx.md
```

## Diagnostic build GGUF

```bash
# l'arch du modèle explique les garbage « ? » si le build ne la connaît pas
op15 gguf D:/lmm/Krypto-WhiteRabbitNeo-7B-Exploit-qwen35-IQ4NL.gguf
```

## Campagne MoE §8.1-4 (device branché requis)

```bash
op15 campaign --list                          # voir les gates G0..G7
op15 campaign --model D:/lmm/mon-modele.gguf  # exécution porte à porte
# gate G7 attendu REFUSED (ab_evidence) tant que l'A/B §8.8 n'a pas tourné
```

## Requêtes RAG prêtes à l'emploi (examples/queries.txt)

Voir `queries.txt` — exemples validés sur la mémoire de production.
