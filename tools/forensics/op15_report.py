"""
op15_report.py
Génère le rapport spécialisé OnePlus 15 à partir de la mémoire :
  - rapport structuré JSON : reports/op15_report.json
  - rapport lisible : reports/op15_report.md

Contrat : build_report(memory_store) -> dict ; écrit les deux fichiers.
Le rapport est une synthèse, pas une instruction opérationnelle : chaque
procédure y figure avec son statut (verified/hypothesis/in_progress).
"""

import json
from datetime import datetime
from pathlib import Path

import op15_domain
from memory_store import MemoryStore

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
DEVICE_PROFILE_PATH = ROOT / "device_profile.json"


def _load_device_profile() -> dict:
    try:
        return json.loads(DEVICE_PROFILE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Fallback explicite: un profil absent ou invalide ne bloque pas le rapport.
        pass
    return {}


def _device_build(device_profile: dict) -> str:
    """Return the profiled build, with an explicit value for missing data."""
    return str(device_profile.get("build") or "build inconnu (profil absent ou incomplet)")


def build_report(memory: MemoryStore, correlator=None) -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    device_profile = _load_device_profile()
    device_build = _device_build(device_profile)

    procedures = memory.get_procedures()
    aspects = memory.get_aspects()
    hypotheses = memory.all_hypotheses()

    by_aspect: dict[str, list[dict]] = {}
    for aspect in op15_domain.ASPECTS:
        by_aspect[aspect] = []
        for p in procedures:
            if p["aspect"] != aspect:
                continue
            by_aspect[aspect].append({
                "name": p["name"],
                "status": p["status"],
                "steps": json.loads(p["steps"]),
                "risks": json.loads(p["risks"]),
                "source_refs": json.loads(p["source_refs"]),
                "contract": p["contract"],
            })

    models = {m: v for m, v in op15_domain.MODELS.items()}
    tools = list(op15_domain.TOOLS)
    partitions = list(op15_domain.PARTITIONS)
    components = {k: v for k, v in op15_domain.COMPONENTS.items()}

    # --- Failles : catalogue + interconnexion observée dans le graphe -------
    vulns_report = []
    for name, v in op15_domain.VULNS.items():
        proc_names = v.get("procedures", [])
        proc_detail = []
        for pn in proc_names:
            entry = next((p for p in procedures if p["name"] == pn), None)
            proc_detail.append({
                "name": pn,
                "aspect": entry["aspect"] if entry else None,
                "status": entry["status"] if entry else None,
            })
        vulns_report.append({
            "id": name,
            "label": v["label"],
            "famille": v["famille"],
            "status": v["status"],
            "cibles": v["cibles"],
            "vecteur": v["vecteur"],
            "impact": v["impact"],
            "cves": v["cves"],
            "axes": v["axes"],
            "procedures": proc_detail,
            "utilite": v.get("utilite", ""),
            "determination": v.get("determination", ""),
        })

    open_questions = []
    for p in procedures:
        if p["status"] == "hypothesis":
            open_questions.append(
                f"Procédure {p['name']} (aspect {p['aspect']}) : statut 'hypothesis' — "
                f"à confirmer sur appareil réel."
            )
        elif p["status"] == "in_progress":
            open_questions.append(
                f"Procédure {p['name']} (aspect {p['aspect']}) : en cours — pas de stable confirmé."
            )
    for h in hypotheses:
        if h["confidence"] < 0.5:
            open_questions.append(
                f"Hypothèse confiance {h['confidence']:.2f} : «{h['statement']}» — besoin de preuves."
            )

    graph_stats = correlator.stats() if correlator else {"nodes": 0, "edges": 0}
    top_pmi = []
    if correlator:
        # Recharge le graphe depuis la mémoire persistée : le rapport est
        # déterministe même si l'ingestion incrémentale n'a rien ré-ingéré.
        correlator.reload_from_memory(memory)
        graph_stats = correlator.stats()
        for a, b, w, sources, pmi in correlator.top_correlations(
                min_weight=1, limit=8, score="pmi"):
            top_pmi.append({
                "a": a, "b": b, "weight": w, "pmi": round(pmi, 3),
                "sources": len(sources),
            })
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "device_profile": device_profile,
        "device": {"models": models, "aspects": op15_domain.ASPECTS},
        "catalog": {
            "tools": tools, "partitions": partitions, "components": components,
        },
        "per_aspect": by_aspect,
        "vulns": vulns_report,
        "observations": {
            "sources_ingerees": memory.conn.execute(
                "SELECT COUNT(*) FROM sources").fetchone()[0],
            "entites": memory.conn.execute(
                "SELECT COUNT(*) FROM entities").fetchone()[0],
            "correlations_persistees": memory.conn.execute(
                "SELECT COUNT(*) FROM correlations").fetchone()[0],
            "arretes_graphe_vivant": graph_stats["edges"],
            "docs_ingerees_correlateur": graph_stats.get("docs_ingerees", 0),
            "hypotheses": len(hypotheses),
            "failles_cataloguees": len(vulns_report),
            "failles_known": sum(1 for v in vulns_report if v["status"] == "known"),
            "failles_possibles": sum(1 for v in vulns_report if v["status"] == "possible"),
            "cves_references": len({c for v in vulns_report for c in v["cves"]}),
        },
        "top_correlations_pmi": top_pmi,
        "open_questions": open_questions,
    }

    (REPORTS_DIR / "op15_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(report)
    return report


def _write_markdown(report: dict) -> None:
    lines = ["# Rapport spécialisé — OnePlus 15", ""]
    device_build = _device_build(report.get("device_profile", {}))
    lines.append(f"Généré le {report['generated_at']}")
    lines.append("Ce rapport est une synthèse de sources publiques ; il n'est pas "
                 "une instruction opérationnelle.")
    lines.append("")

    if report.get("device_profile"):
        lines.append("## Appareil cible")
        for k, v in report["device_profile"].items():
            lines.append(f"- **{k}** : {v}")
        lines.append("")

    lines.append("## Modèles")
    for m, v in report["device"]["models"].items():
        lines.append(f"- **{m}** : région {v['region']}, {v['firmware']} (codename {v['codename']})")
    lines.append("")

    lines.append("## Catalogue matériel")
    lines.append("| Élément | Détails |")
    lines.append("|---|---|")
    for comp, dets in report["catalog"]["components"].items():
        lines.append(f"| {comp} | {', '.join(dets)} |")
    lines.append("")

    lines.append("## Procédures par aspect")
    for aspect, procs in report["per_aspect"].items():
        lines.append(f"\n### {aspect}")
        if not procs:
            lines.append("_Aucune procédure cataloguée._")
            continue
        for p in procs:
            lines.append(f"- **{p['name']}** — statut: `{p['status']}`")
            lines.append(f"  - Contrat: {p['contract']}")
            lines.append(f"  - Risques: {', '.join(p['risks'])}")
            lines.append(f"  - Sources: {', '.join(p['source_refs'])}")
    lines.append("")

    lines.append("## Observations")
    obs = report["observations"]
    for k, v in obs.items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines.append("## Corrélations les plus significatives (PMI)")
    if report.get("top_correlations_pmi"):
        lines.append("| Entité A | Entité B | Poids | PMI | Sources |")
        lines.append("|---|---|---|---|---|")
        for c in report["top_correlations_pmi"]:
            lines.append(f"| {c['a']} | {c['b']} | {c['weight']} | "
                         f"{c['pmi']} | {c['sources']} |")
    else:
        lines.append("_Aucune corrélation calculée (correlateur non fourni)._\n")
    lines.append("")

    # --- Failles & vulnérabilités -------------------------------------------
    vulns = report.get("vulns", [])
    if vulns:
        lines.append("## Failles & vulnérabilités (logicielles et matérielles)")
        lines.append("Statut : `known` = corroboré par sources publiques ; "
                     "`possible` = possible/communautaire, non confirmé sur "
                     "appareil réel. Aucune de ces failles n'implique "
                      # Historique: les anciens rapports indiquaient CPH2747 build 204.
                      f"d'exploitation documentée ou garantie sur CPH2747 {device_build}.")
        lines.append("")

        fam_labels = {
            "bootchain_software": "Bootchain / logiciel OP15",
            "soc_qualcomm": "SoC Qualcomm SM8850",
            "android": "Android / système",
            "hardware": "Matériel",
        }
        by_fam: dict[str, list] = {}
        for v in vulns:
            by_fam.setdefault(v["famille"], []).append(v)

        for fam in op15_domain.VULN_FAMILIES:
            if fam not in by_fam:
                continue
            lines.append(f"### {fam_labels.get(fam, fam)}")
            lines.append("| Faille | Statut | Partitions cibles | Procédures liées | CVEs | Utilité |")
            lines.append("|---|---|---|---|---|---|")
            for v in by_fam[fam]:
                procs = ", ".join(p["name"] for p in v["procedures"]) or "_—_"
                cves = ", ".join(v["cves"]) or "_—_"
                lines.append(f"| {v['label']} | `{v['status']}` | "
                             f"{', '.join(v['cibles'])} | {procs} | {cves} | "
                             f"{v.get('utilite','')} |")
            lines.append("")

        # Utilités & détermination détaillées
        lines.append("### Utilités & détermination (pourquoi known / possible)")
        for v in vulns:
            lines.append(f"- **{v['label']}** (`{v['status']}`)")
            if v.get("utilite"):
                lines.append(f"  - Utilité : {v['utilite']}")
            if v.get("determination"):
                lines.append(f"  - Détermination : {v['determination']}")
        lines.append("")

        # Matrice visuelle faille x partition x procédure
        lines.append("### Matrice d'interconnexion — faille × partition × procédure")
        lines.append("X = lien établi dans le catalogue ; vide = non établi.")
        lines.append("")
        all_procs = sorted({p["name"] for v in vulns for p in v["procedures"]})
        all_cibles = sorted({c for v in vulns for c in v["cibles"]})
        lines.append("**Faille × partition**")
        lines.append("| Faille | " + " | ".join(all_cibles) + " |")
        lines.append("|---|" + "---|" * len(all_cibles))
        for v in vulns:
            cells = ["X" if c in v["cibles"] else " " for c in all_cibles]
            lines.append(f"| {v['label']} | " + " | ".join(cells) + " |")
        lines.append("")

        lines.append("**Faille × procédure**")
        lines.append("| Faille | " + " | ".join(all_procs) + " |")
        lines.append("|---|" + "---|" * len(all_procs))
        for v in vulns:
            pset = {p["name"] for p in v["procedures"]}
            cells = ["X" if p in pset else " " for p in all_procs]
            lines.append(f"| {v['label']} | " + " | ".join(cells) + " |")
        lines.append("")

        # Tableau CVE -> axe
        lines.append("### CVEs → axe concerné")
        lines.append("| CVE | Faille | Axes |")
        lines.append("|---|---|---|")
        for v in vulns:
            for c in v["cves"]:
                lines.append(f"| {c} | {v['label']} | {', '.join(v['axes'])} |")
        lines.append("")
    else:
        lines.append("_Aucune faille cataloguée._\n")

    lines.append("## Questions ouvertes (preuves à apporter)")
    for q in report["open_questions"]:
        lines.append(f"- {q}")
    lines.append("")

    (REPORTS_DIR / "op15_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    m = MemoryStore()
    try:
        build_report(m)
        print("rapport écrit : reports/op15_report.json + .md")
    finally:
        m.close()
