"""
run.py — point d'entrée autonome de l'agent spécialisé OnePlus 15.

    python run.py --auto                amorce mémoire + apprend local + rapport
    python run.py --auto --network      idem + collecte réseau des seed URLs
    python run.py --learn --local ../   apprend les documents locaux
    python run.py --report              régénère le rapport depuis la mémoire
    python run.py --urls https://...    cycle réseau ciblé
"""

import argparse
import sys
from pathlib import Path

from orchestrator import Orchestrator

PROJECT_DIR = Path(__file__).resolve().parent
DOCS_DIR = PROJECT_DIR.parent  # dossiers de référence OnePlus 15


def main():
    # stdout en UTF-8 : évite le mojibake des accents sur console Windows (cp1252),
    # comme le font déjà rag_bm25.py et pipeline_all.py.
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Agent autonome spécialisé OnePlus 15")
    parser.add_argument("--auto", action="store_true", help="Boucle autonome complète")
    parser.add_argument("--network", action="store_true", help="Autoriser la collecte réseau")
    parser.add_argument("--cves", action="store_true",
                        help="Ingérer les CVEs du catalogue depuis le cache NVD")
    parser.add_argument("--learn", action="store_true", help="Mode apprentissage")
    parser.add_argument("--report", action="store_true", help="Générer le rapport")
    parser.add_argument("--local", type=str, help="Dossier de documents locaux")
    parser.add_argument("--urls", nargs="*", default=[], help="URLs à traiter")
    args = parser.parse_args()

    orch = Orchestrator()
    try:
        if args.auto:
            orch.bootstrap_domain()
            orch.load_device_profile()
            orch.learn_local(DOCS_DIR)
            orch.learn_local(PROJECT_DIR)
            if args.network:
                from op15_sources import all_seed_urls
                orch.run_cycle(all_seed_urls())
            if args.cves or args.network:
                orch.learn_cves()
            if args.network:
                orch.bugtracker()
            orch.telemetry()
            orch.generate_report()
            print("\n=== TERMINÉ : rapport dans reports/op15_report.md ===")
            return

        if args.learn:
            orch.bootstrap_domain()
            if args.local:
                orch.learn_local(Path(args.local))
            if args.urls:
                orch.run_cycle(args.urls)
            return

        if args.report:
            orch.generate_report()
            print("rapport généré : reports/op15_report.json + .md")
            return

        parser.print_help()
    finally:
        orch.close()


if __name__ == "__main__":
    main()
