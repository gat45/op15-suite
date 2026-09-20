"""
orchestrator.py
Fait tourner le cycle complet : Collecte -> Extraction -> Corrélation ->
Hypothèses -> Mémoire -> Rapport, spécialisé OnePlus 15.

Modes :
    --urls <u...>        cycle sur une liste d'URLs (réseau)
    --local <dir>        cycle sur des documents locaux .md/.txt (hors-ligne)
    --bootstrap          amorce la mémoire avec le catalogue domaine (idempotent)
    --report             génère le rapport spécialisé op15 (reports/op15_*.json|md)
    --auto               bootstrap + local (dossier parent) + seed URLs + rapport

Usage :
    python orchestrator.py --auto
    python orchestrator.py --local ../ --report
"""

import argparse
import json
import sys
import time
from pathlib import Path

from agent_collector import AgentCollector, RawDocument
from agent_correlator import AgentCorrelator
from agent_extractor import process_document, EXTRACTOR_VERSION
from agent_hypothesis import AgentHypothesis
from memory_store import MemoryStore, fingerprint
import op15_domain
import op15_sources
from op15_report import build_report

ROOT = Path(__file__).resolve().parent


def _fp(doc_text: str) -> str:
    """Empreinte liée au contenu ET à la version de l'extracteur."""
    return fingerprint(f"{EXTRACTOR_VERSION}::{doc_text}")


class Orchestrator:
    def __init__(self, db_path=None):
        self.collector = AgentCollector()
        self.correlator = AgentCorrelator()
        self.memory = MemoryStore(db_path) if db_path else MemoryStore()

    def bootstrap_domain(self):
        """Amorce la mémoire avec le catalogue de procédures du domaine."""
        for aspect in op15_domain.ASPECTS:
            desc = f"Aspect matériel OnePlus 15 : {aspect}"
            self.memory.upsert_aspect(aspect, desc)
        for name, p in op15_domain.PROCEDURES.items():
            self.memory.upsert_procedure(
                name=name, aspect=p["aspect"], status=p["status"],
                steps=p["steps"], risks=p["risks"],
                source_refs=p["source_refs"], contract=p["contract"],
            )
        print(f"[bootstrap] {len(op15_domain.ASPECTS)} aspect(s), "
              f"{len(op15_domain.PROCEDURES)} procédure(s) cataloguée(s)")

    def load_device_profile(self, path: Path = ROOT / "device_profile.json") -> dict | None:
        """Charge la fiche appareil cible et l'ingère comme document source."""
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        text = " ; ".join(f"{k}: {v}" for k, v in data.items())
        doc = RawDocument(url=f"file://{path}", title="Device Profile CPH2747", text=text)
        source_id, changed = self.memory.add_source(
            doc.url, doc.title, text, fp=_fp(text))
        if changed:
            self._ingest_doc(doc, source_id)
        print(f"[bootstrap] appareil cible chargé : {data.get('modele')} — {data.get('build')}")
        return data

    def _ingest_doc(self, doc: RawDocument, source_id: int, aspect: str | None = None):
        cleaned, entities = process_document(doc)
        for ent in entities:
            self.memory.add_entity(ent.name, ent.entity_type, source_id)
        self.correlator.ingest(entities, source_id)
        domain = [e for e in entities if e.entity_type.startswith("op15_")]
        seen = set()
        pairs = []
        for i in range(len(domain)):
            for j in range(i + 1, len(domain)):
                a, b = sorted((domain[i].name, domain[j].name))
                key = (a, b)
                if key in seen:
                    continue
                seen.add(key)
                ta = domain[i].entity_type if domain[i].name == a else domain[j].entity_type
                tb = domain[j].entity_type if domain[i].name == a else domain[i].entity_type
                pairs.append((a, ta, b, tb))
        if pairs:
            self.memory.add_domain_correlations(pairs, source_id)
        for ent in entities:
            if ent.entity_type == "op15_procedure":
                for name, proc in op15_domain.PROCEDURES.items():
                    kw = name.split("_")[0]
                    if kw in ent.name.lower():
                        self.memory.record_procedure_mention(
                            name, ent.name, ent.entity_type, source_id)
        return cleaned, entities

    SKIP_DIRS = {
        "reports", "__pycache__",
        # B2 (audit 2026-08-18) : ne pas ingérer les repos tiers clonés, le vendor
        # téléchargé (Hexagon SDK 6.6.0.0, sources clonées) ni les artefacts générés
        # (graphe Graft, .git). Ces contenus polluaient la mémoire OP15 (état « 499
        # sources » avant dédup) sans être du contenu OnePlus 15.
        "Box-main", "local-dream-master", "OllamaAMDNPU-main",
        "snapdragon-npu-llm-main", "downloads", "graft", ".graft",
        ".git", "Nouveau dossier", "OnePlus-USB-Drivers-Setup",
    }

    def learn_local(self, directory: Path, min_weight: int = 2):
        """Ingère les documents locaux markdown du dossier donné."""
        files = [f for f in directory.rglob("*.md")
                 if not any(part in self.SKIP_DIRS for part in f.parts)]
        if not files:
            print(f"[local] aucun document .md dans {directory}")
            return []
        print(f"\n=== Apprentissage local : {len(files)} document(s) ===")
        ingested = skipped = 0
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError as e:
                print(f"[local] lecture impossible {f}: {e}")
                continue
            doc = RawDocument(url=f"file://{f}", title=f.stem, text=text)
            source_id, changed = self.memory.add_source(
                doc.url, doc.title, text, fp=_fp(text))
            if changed:
                self._ingest_doc(doc, source_id)
                ingested += 1
                print(f"  + {f.name}")
            else:
                skipped += 1
        print(f"[local] {ingested} ingéré(s), {skipped} inchangé(s) ignoré(s)")
        self._report_stats(min_weight)
        return files

    def run_cycle(self, urls: list[str], min_weight: int = 2):
        print(f"\n=== Cycle : {len(urls)} URL(s) ===")
        docs = self.collector.fetch_many(urls)
        print(f"[orchestrator] {len(docs)} document(s) collecté(s)")
        ingested = skipped = 0
        for doc in docs:
            source_id, changed = self.memory.add_source(
                doc.url, doc.title, doc.text, fp=_fp(doc.text))
            if changed:
                self._ingest_doc(doc, source_id)
                ingested += 1
            else:
                skipped += 1
        print(f"[orchestrator] {ingested} ingéré(s), {skipped} inchangé(s) ignoré(s)")
        self._report_stats(min_weight)
        return docs

    def learn_cves(self, min_weight: int = 2):
        """Ingère les CVEs du catalogue depuis le cache NVD (JSON, non-JS).

        Chaque CVE devient une source : description + CVSS + références, puis
        entités/corrélations via l'extracteur (motifs CVE/vuln).
        """
        from cve_lookup import load_cache
        cache = load_cache()
        if not cache:
            print("[cve] cache NVD vide — lancer python cve_lookup.py --refresh")
            return
        ingested = skipped = 0
        for cve_id, entry in cache.items():
            if entry.get("status") != "ok":
                continue
            text = (f"{cve_id} : {entry.get('description','')}. "
                    f"Publication {entry.get('published','')}. "
                    f"CVSS {entry.get('cvss')} {entry.get('severity','')}. "
                    f"Faiblesses : {'; '.join(entry.get('weaknesses',[]))}. "
                    f"Références : {' '.join(entry.get('references',[]))}.")
            url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"
            source_id, changed = self.memory.add_source(
                url, f"NVD {cve_id}", text, fp=_fp(text))
            if changed:
                self._ingest_doc(RawDocument(url=url, title=f"NVD {cve_id}", text=text),
                                 source_id)
                ingested += 1
            else:
                skipped += 1
        print(f"[cve] {ingested} CVE(s) ingéré(s), {skipped} inchangé(s)")
        self._report_stats(min_weight)

    def bugtracker(self, min_weight: int = 2):
        """Ingère le rapport de bugs communautaires (issues GitHub publiques).

        Génère downloads/bugs_report.md via bug_tracker.py puis l'ajoute
        comme source mémoire (entités/corrélations). Idempotent (fingerprint).
        """
        try:
            from bug_tracker import collect, render
            report = collect()
            text = render(report)
            md = ROOT / "downloads" / "bugs_report.md"
            md.write_text(text, encoding="utf-8")
            source_id, changed = self.memory.add_source(
                f"file://{md}", "Bugs communautaires OP15", text, fp=_fp(text))
            if changed:
                self._ingest_doc(RawDocument(url=f"file://{md}",
                                             title="Bugs communautaires OP15",
                                             text=text), source_id)
                print("[bugtracker] rapport ingéré dans la mémoire")
            else:
                print("[bugtracker] rapport inchangé (déjà en mémoire)")
        except Exception as e:  # noqa: BLE001
            print(f"[bugtracker] erreur (réseau/API) : {e}")

    def telemetry(self):
        """Vérifie l'état télémétrie (apps espionnes + Private DNS) et le
        consigne dans downloads/telemetry_watch.log. Non bloquant."""
        try:
            import subprocess
            r = subprocess.run(
                [sys.executable, str(ROOT / "telemetry_watch.py"), "--check"],
                capture_output=True, text=True, timeout=90,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            out = (r.stdout or "") + (r.stderr or "")
            print(f"[telemetry] {out.strip()}")
        except Exception as e:  # noqa: BLE001
            print(f"[telemetry] erreur : {e}")

    def _report_stats(self, min_weight: int):
        stats = self.correlator.stats()
        print(f"[orchestrator] Graphe : {stats['nodes']} entités, {stats['edges']} relations, "
              f"{stats['docs_ingerees']} doc(s)")
        failed = self.collector.failed_urls()
        if failed:
            path = self.collector.export_failed()
            print(f"[orchestrator] {len(failed)} URL(s) non atteinte(s) -> {path}")
            for f in failed:
                detail = f" ({f.detail})" if f.detail else ""
                print(f"  - {f.url} [{f.reason}]{detail}")
        hyp_agent = AgentHypothesis(self.correlator, min_weight=min_weight)
        hypotheses = hyp_agent.generate(limit=15)
        for h in hypotheses:
            # Preuves réelles : id des corrélations persistées correspondantes
            support = []
            for pair in (h.entities, (h.entities[1], h.entities[0])):
                cid = self.memory.correlation_by_pair(pair[0], pair[1])
                if cid is not None:
                    support.append(cid)
            self.memory.add_hypothesis(
                statement=h.statement, confidence=h.confidence,
                supporting_correlations=support,
            )
        print(f"[orchestrator] {len(hypotheses)} hypothèse(s) générée(s)")
        for h in hypotheses:
            print(f"  [{h.confidence:.2f}] {h.statement}")

    def generate_report(self) -> dict:
        return build_report(self.memory, correlator=self.correlator)

    def close(self):
        self.memory.close()


def main():
    # stdout en UTF-8 : évite le mojibake des accents sur console Windows (cp1252),
    # comme le font déjà rag_bm25.py et pipeline_all.py.
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Orchestrateur agents — spécialisé OnePlus 15")
    parser.add_argument("--urls", nargs="*", default=[], help="URLs à traiter")
    parser.add_argument("--urls-file", type=str, help="Fichier texte, une URL par ligne")
    parser.add_argument("--local", type=str, help="Dossier de documents locaux à ingérer")
    parser.add_argument("--bootstrap", action="store_true", help="Amorcer la mémoire domaine")
    parser.add_argument("--report", action="store_true", help="Générer le rapport op15")
    parser.add_argument("--auto", action="store_true", help="Boucle autonome complète")
    parser.add_argument("--min-weight", type=int, default=2)
    parser.add_argument("--network", action="store_true", help="Autoriser le réseau (seed URLs)")
    args = parser.parse_args()

    orch = Orchestrator()
    try:
        if args.bootstrap or args.auto:
            orch.bootstrap_domain()
            orch.load_device_profile()

        if args.auto:
            parent = ROOT.parent
            orch.learn_local(parent, min_weight=args.min_weight)
            orch.learn_local(ROOT, min_weight=args.min_weight)
            if args.network:
                orch.run_cycle(op15_sources.all_seed_urls(), min_weight=args.min_weight)
            orch.generate_report()
            return

        if args.local:
            orch.learn_local(Path(args.local), min_weight=args.min_weight)

        urls = list(args.urls)
        if args.urls_file:
            with open(args.urls_file, encoding="utf-8") as f:
                urls.extend(line.strip() for line in f if line.strip())
        if urls:
            orch.run_cycle(urls, min_weight=args.min_weight)

        if args.report:
            orch.generate_report()
    finally:
        orch.close()


if __name__ == "__main__":
    main()
