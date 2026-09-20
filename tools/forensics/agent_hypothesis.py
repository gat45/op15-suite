"""
agent_hypothesis.py
Génère des hypothèses à partir du graphe de corrélations.

Deux modes :
  - générique : corrélation co-occurrence (existant)
  - domaine   : phrases OnePlus 15 construites à partir de l'ontologie
               (modèle -> procédure, outil -> procédure, build -> partition).

Toute hypothèse porte un statut explicite (open/verified/rejected) et un
score de confiance [0,1]. Jamais de fausse certitude (§10 : une affirmation
sans preuve est une hypothèse, pas un fait).
"""

from dataclasses import dataclass

from agent_correlator import AgentCorrelator
from op15_domain import PROCEDURES


@dataclass
class Hypothesis:
    statement: str
    confidence: float  # 0.0 - 1.0
    evidence_weight: int
    entities: tuple[str, str]
    domain: bool = False
    status: str = "open"
    significance: float = 0.0  # PMI normalisé, indépendant du nombre de sources


def confidence_from_weight(weight: int, max_weight: int) -> float:
    if max_weight == 0:
        return 0.0
    return round(min(weight / max_weight, 1.0), 2)


def _hybrid_confidence(weight: int, max_weight: int, pmi: float) -> float:
    """Confiance hybride : fréquence relative pondérée par la significativité PMI."""
    w = confidence_from_weight(weight, max_weight)
    if pmi <= 0:
        return 0.0
    return round(min(0.9 * w + 0.1 * pmi, 1.0), 2)


class AgentHypothesis:
    def __init__(self, correlator: AgentCorrelator, min_weight: int = 2):
        self.correlator = correlator
        self.min_weight = min_weight

    def _domain_statement(self, a: str, b: str) -> str | None:
        # Détecte un couple (entité domaine) et construit une phrase métier.
        types = self.correlator.graph.nodes
        ta = types[a].get("entity_type", "") if a in types else ""
        tb = types[b].get("entity_type", "") if b in types else ""

        if ta == "op15_model" and tb == "op15_procedure":
            return f"Le modèle {a} est associé à la procédure «{b}»."
        if tb == "op15_model" and ta == "op15_procedure":
            return f"Le modèle {b} est associé à la procédure «{a}»."
        if ta == "op15_tool" and tb == "op15_procedure":
            return f"L'outil {a} intervient dans la procédure «{b}»."
        if tb == "op15_tool" and ta == "op15_procedure":
            return f"L'outil {b} intervient dans la procédure «{a}»."
        if ta == "op15_partition" and tb == "op15_procedure":
            return f"La partition {a} est impliquée dans la procédure «{b}»."
        if tb == "op15_partition" and ta == "op15_procedure":
            return f"La partition {b} est impliquée dans la procédure «{a}»."
        if ta == "op15_build" and tb == "op15_partition":
            return f"Le build {a} se patche via la partition {b}."
        if tb == "op15_build" and ta == "op15_partition":
            return f"Le build {b} se patche via la partition {a}."
        return None

    def generate(self, limit: int = 10) -> list[Hypothesis]:
        top = self.correlator.top_correlations(min_weight=self.min_weight, limit=limit * 3)
        if not top:
            return []
        max_weight = max(w for _, _, w, _, _ in top)

        def is_domain(entity: str) -> bool:
            if entity not in self.correlator.graph:
                return False
            et = self.correlator.graph.nodes[entity].get("entity_type", "")
            return et.startswith("op15_")

        domain_hyp, generic_hyp = [], []
        for a, b, weight, sources, pmi in top:
            # garde-fou : une URL (badge shields.io, asset) n'est jamais un
            # partenaire de corrélation valable — bruit d'extraction markdown
            if a.startswith(("http://", "https://")) \
                    or b.startswith(("http://", "https://")):
                continue
            conf = _hybrid_confidence(weight, max_weight, pmi)
            stmt = self._domain_statement(a, b)
            if stmt:
                domain_hyp.append(Hypothesis(
                    statement=stmt, confidence=conf, evidence_weight=weight,
                    entities=(a, b), domain=True, significance=pmi,
                ))
                continue
            if not (is_domain(a) or is_domain(b)):
                continue
            statement = (
                f"Corrélation observée entre '{a}' et '{b}' "
                f"(dans {len(sources)} source(s), poids={weight})."
            )
            generic_hyp.append(Hypothesis(
                statement=statement, confidence=conf,
                evidence_weight=weight, entities=(a, b), significance=pmi,
            ))

        return (domain_hyp + generic_hyp)[:limit]


if __name__ == "__main__":
    from agent_extractor import ExtractedEntity

    corr = AgentCorrelator()
    corr.ingest([ExtractedEntity("CPH2747", "op15_model"),
                 ExtractedEntity("root", "op15_procedure")], source_id=1)
    corr.ingest([ExtractedEntity("CPH2747", "op15_model"),
                 ExtractedEntity("Magisk", "op15_tool")], source_id=2)
    hyp_agent = AgentHypothesis(corr, min_weight=1)
    for h in hyp_agent.generate():
        print(f"[{h.confidence}][{h.status}] {h.statement}")
