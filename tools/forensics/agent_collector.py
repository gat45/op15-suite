"""
agent_collector.py
Collecte des données depuis des sources OUVERTES et LEGITIMES :
  - APIs de recherche (à brancher : Bing API, SerpAPI, DuckDuckGo API, etc.)
  - Flux RSS publics
  - APIs publiques thématiques (arXiv, GitHub, Wikipedia, etc.)

Respecte systématiquement :
  - robots.txt
  - rate limiting
  - user-agent identifié (pas de camouflage)

Ce module NE CONTOURNE AUCUNE protection anti-bot et NE CIBLE PAS
le "web non référencé" / dark web. Toute source doit être accessible
publiquement et sans authentification contournée.
"""

import time
import urllib.robotparser as robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests


USER_AGENT = "AgentTeamResearchBot/1.0 (+contact: [email protected])"
DEFAULT_DELAY_SECONDS = 2.0


@dataclass
class RawDocument:
    url: str
    title: str
    text: str
    fetched_at: float = field(default_factory=time.time)


@dataclass
class FailedFetch:
    url: str
    reason: str  # "robots_txt_bloque", "robots_txt_illisible", "http_error", "reseau"
    detail: str = ""
    failed_at: float = field(default_factory=time.time)


class RobotsChecker:
    """Vérifie robots.txt avant toute requête."""

    def __init__(self):
        self._cache: dict[str, robotparser.RobotFileParser] = {}

    def check(self, url: str, user_agent: str = USER_AGENT) -> tuple[bool, str]:
        """Retourne (autorisé, raison_si_refuse)."""
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._cache:
            rp = robotparser.RobotFileParser()
            rp.set_url(base + "/robots.txt")
            try:
                rp.read()
            except Exception as e:
                # Si robots.txt inaccessible, on est prudent : on refuse.
                return False, f"robots_txt_illisible: {e}"
            self._cache[base] = rp
        if self._cache[base].can_fetch(user_agent, url):
            return True, ""
        return False, "robots_txt_bloque"


class AgentCollector:
    def __init__(self, delay: float = DEFAULT_DELAY_SECONDS):
        self.delay = delay
        self.robots = RobotsChecker()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.failed: list[FailedFetch] = []

    def fetch_url(self, url: str) -> RawDocument | None:
        """Récupère une page si robots.txt l'autorise. Sinon, log l'échec."""
        allowed, reason = self.robots.check(url)
        if not allowed:
            print(f"[collector] Non atteint ({reason}) : {url}")
            self.failed.append(FailedFetch(url=url, reason=reason))
            return None
        try:
            resp = self.session.get(url, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[collector] Erreur fetch {url}: {e}")
            self.failed.append(FailedFetch(url=url, reason="http_ou_reseau", detail=str(e)))
            return None
        finally:
            time.sleep(self.delay)  # rate limiting poli

        return RawDocument(url=url, title=url, text=resp.text)

    def fetch_many(self, urls: list[str]) -> list[RawDocument]:
        docs = []
        for u in urls:
            doc = self.fetch_url(u)
            if doc:
                docs.append(doc)
        return docs

    def failed_urls(self) -> list[FailedFetch]:
        """Liste des URLs que l'agent n'a pas pu atteindre, avec la raison."""
        return list(self.failed)

    def export_failed(self, path: str = "urls_non_atteintes.txt") -> str:
        """Écrit la liste des URLs non atteintes dans un fichier texte, pour
        que l'utilisateur puisse les récupérer manuellement."""
        with open(path, "w", encoding="utf-8") as f:
            for item in self.failed:
                line = f"{item.url}\t{item.reason}"
                if item.detail:
                    line += f"\t{item.detail}"
                f.write(line + "\n")
        return path

    def search_via_api(self, query: str, api_search_fn) -> list[RawDocument]:
        """
        Point d'extension : brancher ici une vraie API de recherche
        (SerpAPI, Bing Search API, DuckDuckGo Instant Answer, arXiv API...).
        api_search_fn(query) doit retourner une liste de dicts
        {url, title, snippet}.
        """
        results = api_search_fn(query)
        docs = []
        for r in results:
            docs.append(RawDocument(url=r["url"], title=r.get("title", ""), text=r.get("snippet", "")))
        return docs


if __name__ == "__main__":
    # Exemple d'usage minimal
    collector = AgentCollector()
    test_docs = collector.fetch_many(["https://en.wikipedia.org/wiki/Multi-agent_system"])
    for d in test_docs:
        print(d.title, len(d.text), "caractères")
