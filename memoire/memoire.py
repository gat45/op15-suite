#!/usr/bin/env python3
"""CLI JARVIX Memory — interface terminal pour Buffy/agents.

Usage :
  python memoire.py add "<contenu>" --type semantic --conf 1.0 --source "<src>"
  python memoire.py search "<query>" [--limit 10]
  python memoire.py get "<id>"
  python memoire.py list [--type semantic] [--limit 20]
  python memoire.py stats
  python memoire.py decision "<décision>" "<raisonnement>"
  python memoire.py episodic "<action>" "<résultat>"
  python memoire.py graph "<sujet>" "<prédicat>" "<objet>"
  python memoire.py strategy-best "<situation>"
"""
import argparse
import json
import os
import sys
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent
SRC = PKG_ROOT / "src"
sys.path.insert(0, str(SRC))

# DB ancrée au dossier du paquet (le défaut du core est relatif au CWD,
# ce qui fragmente la mémoire : chaque agent voyait sa propre base).
os.chdir(PKG_ROOT)

from jarvix_memory.router import MemoryRouter  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(prog="memoire")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("content")
    a.add_argument("--type", default="semantic")
    a.add_argument("--conf", type=float, default=1.0)
    a.add_argument("--source", default=None)

    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)

    g = sub.add_parser("get")
    g.add_argument("memory_id")

    l = sub.add_parser("list")
    l.add_argument("--type", default=None)
    l.add_argument("--limit", type=int, default=20)

    sub.add_parser("stats")

    d = sub.add_parser("decision")
    d.add_argument("decision")
    d.add_argument("reasoning")

    e = sub.add_parser("episodic")
    e.add_argument("action")
    e.add_argument("result")

    gr = sub.add_parser("graph")
    gr.add_argument("subject")
    gr.add_argument("predicate")
    gr.add_argument("obj")

    sb = sub.add_parser("strategy-best")
    sb.add_argument("situation")

    b = sub.add_parser("bilan")
    b.add_argument("--json", action="store_true")
    b.add_argument("--save", action="store_true")
    b.add_argument("--short", action="store_true")

    args = p.parse_args()
    r = MemoryRouter(str(PKG_ROOT / "jarvix_memory.db"))

    if args.cmd == "add":
        from jarvix_memory.core.models import Memory
        m = Memory(type=args.type, content=args.content,
                   confidence=args.conf, source=args.source)
        r.db.insert_memory(m)   # insert_memory remplit m.id in place (retourne None)
        print(json.dumps({"id": m.id, "type": args.type}))
    elif args.cmd == "search":
        # Contournement du core : search_fts() encapsule la requête dans des
        # quotes ("...") → phrase exacte. On injecte des termes pré-quotés qui
        # restent valides après wrapping : "a"" ""AND"" ""b" → "a" "AND" "b".
        terms = [t for t in args.query.replace('"', " ").split() if t]
        inner = '" "'.join(terms) if terms else "*"
        res = r.db.search_fts(inner)          # après wrapping : "a" "b" … (AND implicite)
        if not res and len(terms) > 1:
            res = r.db.search_fts('" OR "'.join(terms))  # après wrapping : "a" OR "b"
        print(json.dumps(res[: args.limit], default=str, ensure_ascii=False, indent=1))
    elif args.cmd == "get":
        print(json.dumps(r.db.get_memory(args.memory_id), default=str, ensure_ascii=False))
    elif args.cmd == "list":
        res = (r.db.search_by_type(args.type, limit=args.limit)
               if args.type else r.db.search_fts("*", limit=args.limit))
        print(json.dumps(res, default=str, ensure_ascii=False, indent=1))
    elif args.cmd == "stats":
        print(json.dumps(r.stats(), ensure_ascii=False, indent=1))
    elif args.cmd == "decision":
        m = r.decision.log_decision(args.decision, args.reasoning)
        print(json.dumps({"id": m.id, "type": "decision"}))
    elif args.cmd == "episodic":
        m = r.episodic.log_event(args.action, args.result)
        print(json.dumps({"id": m.id, "type": "episodic"}))
    elif args.cmd == "graph":
        m = r.graph.add_relation(args.subject, args.predicate, args.obj)
        print(json.dumps({"id": m.id, "type": "graph"}))
    elif args.cmd == "strategy-best":
        print(json.dumps(r.strategy.best_for_situation(args.situation), default=str, ensure_ascii=False))
    elif args.cmd == "bilan":
        from bilan import generate_report
        report = generate_report(save=args.save, as_json=args.json, short=args.short)
        print(report)


if __name__ == "__main__":
    main()
