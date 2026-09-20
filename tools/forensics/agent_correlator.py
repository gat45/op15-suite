"""
agent_correlator.py
Construit un graphe de relations entre entités à partir de leur co-occurrence
dans les mêmes documents/sources.

Score d'importance :
  - weight : nombre de documents où la paire co-apparaît
  - pmi    : pointwise mutual information (significativité > co-occurrence brute)
  - lift   : P(a,b)/(P(a).P(b)) — facteur de dépassement du hasard

Les noms d'entités sont normalisés (minuscules, espacement) pour fusionner
les variantes orthographiques (Magisk/magisk, init_boot/init boot).
"""

import json
import math
from collections import defaultdict
from itertools import combinations

import networkx as nx

from agent_extractor import ExtractedEntity


def normalize_name(name: str) -> str:
    """Normalise un nom d'entité pour fusionner les variantes orthographiques."""
    n = name.strip().lower()
    n = n.replace("_", " ").replace("-", " ")
    n = " ".join(n.split())
    return n


class AgentCorrelator:
    def __init__(self):
        self.graph = nx.Graph()
        self._doc_count = 0

    def _ensure_node(self, name: str, entity_type: str):
        key = normalize_name(name)
        if not self.graph.has_node(key):
            self.graph.add_node(key, entity_type=entity_type, display=name, sources=set())
        return key

    def ingest(self, entities: list[ExtractedEntity], source_id: int):
        """Ajoute les entités d'un document et relie celles qui co-apparaissent."""
        self._doc_count += 1
        keys = []
        for e in entities:
            key = self._ensure_node(e.name, e.entity_type)
            self.graph.nodes[key]["sources"].add(source_id)
            keys.append(key)

        for a, b in combinations(sorted(set(keys)), 2):
            if self.graph.has_edge(a, b):
                self.graph[a][b]["weight"] += 1
                self.graph[a][b]["sources"].add(source_id)
            else:
                self.graph.add_edge(a, b, weight=1, sources={source_id})

    def _pmi(self, a: str, b: str, weight: int) -> float:
        """Pointwise mutual information pour la paire (normalisée en [0,1])."""
        if self._doc_count == 0:
            return 0.0
        na = len(self.graph.nodes[a]["sources"])
        nb = len(self.graph.nodes[b]["sources"])
        if na == 0 or nb == 0:
            return 0.0
        pa, pb, pab = na / self._doc_count, nb / self._doc_count, weight / self._doc_count
        if pab == 0:
            return 0.0
        pmi = math.log(pab / (pa * pb), 2)
        # normalisation par -log2(pab) : [0,1]
        return max(0.0, min(pmi / (-math.log2(pab)) if pab < 1 else 1.0, 1.0))

    def _lift(self, a: str, b: str, weight: int) -> float:
        if self._doc_count == 0:
            return 0.0
        na = len(self.graph.nodes[a]["sources"])
        nb = len(self.graph.nodes[b]["sources"])
        if na == 0 or nb == 0:
            return 0.0
        pa, pb, pab = na / self._doc_count, nb / self._doc_count, weight / self._doc_count
        if pa * pb == 0:
            return 0.0
        return pab / (pa * pb)

    def top_correlations(self, min_weight: int = 2, limit: int = 20,
                         score: str = "pmi"):
        """Retourne les corrélations les plus significatives.

        score = "weight" (brut), "pmi" (par défaut) ou "lift".
        """
        if not self.graph.edges:
            return []
        edges = []
        for a, b, d in self.graph.edges(data=True):
            w = d["weight"]
            if w < min_weight:
                continue
            if score == "weight":
                s = float(w)
            elif score == "lift":
                s = self._lift(a, b, w)
            else:
                s = self._pmi(a, b, w)
            edges.append((a, b, w, d["sources"], s))
        # significativité décroissante, départage par poids
        edges.sort(key=lambda x: (x[4], x[2]), reverse=True)
        return edges[:limit]

    def neighbors_of(self, entity: str):
        if entity not in self.graph:
            return []
        return list(self.graph.neighbors(entity))

    def reload_from_memory(self, memory) -> int:
        """Reconstruit le graphe depuis la mémoire persistée.

        Charge TOUS les nœuds distincts (table entities) puis les arêtes
        domaine (table correlations). Permet au rapport d'être déterministe
        et complet même quand l'ingestion incrémentale n'a rien ré-ingéré."""
        self.graph = nx.Graph()
        self._doc_count = memory.conn.execute(
            "SELECT COUNT(*) FROM sources").fetchone()[0]
        # 1) tous les nœuds distincts (y compris génériques : URLs, dates, …)
        ent_rows = memory.conn.execute(
            "SELECT name, entity_type, source_id FROM entities").fetchall()
        for r in ent_rows:
            key = self._ensure_node(r["name"], r["entity_type"])
            self.graph.nodes[key]["sources"].add(r["source_id"])
        # 2) arêtes persistées (domaine)
        rows = memory.conn.execute(
            """SELECT ea.name AS na, ea.entity_type AS ta,
                      eb.name AS nb, eb.entity_type AS tb,
                      c.weight, c.evidence
               FROM correlations c
               JOIN entities ea ON ea.id = c.entity_a
               JOIN entities eb ON eb.id = c.entity_b""").fetchall()
        for r in rows:
            a = self._ensure_node(r["na"], r["ta"])
            b = self._ensure_node(r["nb"], r["tb"])
            try:
                sources = set(json.loads(r["evidence"] or "[]"))
            except Exception:  # noqa: BLE001
                sources = set()
            self.graph.nodes[a]["sources"].update(sources)
            self.graph.nodes[b]["sources"].update(sources)
            if self.graph.has_edge(a, b):
                self.graph[a][b]["weight"] += r["weight"]
                self.graph[a][b]["sources"].update(sources)
            else:
                self.graph.add_edge(a, b, weight=r["weight"], sources=set(sources))
        return len(rows)

    def stats(self):
        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "docs_ingerees": self._doc_count,
        }


if __name__ == "__main__":
    corr = AgentCorrelator()
    corr.ingest(
        [ExtractedEntity("Marie Curie", "nom_propre"), ExtractedEntity("Nobel", "nom_propre")],
        source_id=1,
    )
    corr.ingest(
        [ExtractedEntity("Marie Curie", "nom_propre"), ExtractedEntity("Radium", "nom_propre")],
        source_id=2,
    )
    print(corr.stats())
    print(corr.top_correlations(min_weight=1))
