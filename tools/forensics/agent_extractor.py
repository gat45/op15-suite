"""
agent_extractor.py
Nettoie le texte brut et extrait des entités :
  - génériques (dates, URLs, noms propres) — heuristiques simples
  - OnePlus 15 (modèles, builds, OS, partitions, outils, procédures,
    composants, risques) — motifs regex du domaine op15_domain.PATTERNS

Contrat : process_document(doc) -> (cleaned_text, list[ExtractedEntity]).
Ajoute les types op15_* ; les types génériques restent compatibles.
"""

import re
from dataclasses import dataclass
from html import unescape

from agent_collector import RawDocument
from op15_domain import PATTERNS, ENTITY_TYPE_BY_PATTERN, FILE_ALIASES

# Version du pipeline d'extraction : incrémenter force la ré-ingestion des
# documents même si leur contenu n'a pas changé (cache fingerprint).
EXTRACTOR_VERSION = "6"


@dataclass
class ExtractedEntity:
    name: str
    entity_type: str  # "date", "organisation", "op15_model", ...


TAG_RE = re.compile(r"<[^>]+>")
DATE_RE = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")
YEAR_RE = re.compile(r"\b(\d{4})\b")
MEASURE_RE = re.compile(r"\b\d{4}\s*(?:mAh|Mo|Go|GHz|MHz|MHz|MP|nits|nit|Hz|W|V|mA|mAh)\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s\"'<>]+")
# URLs d'assets décoratifs (badges, images, avatars) : pas des entités
ASSET_URL_RE = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|bmp)(\?|$)|/(badge|avatar)s?/", re.IGNORECASE)
CAPITALIZED_RE = re.compile(r"\b([A-Z][a-zéèêàâîïôûù]{2,}(?:\s[A-Z][a-zéèêàâîïôûù]{2,})*)\b")

# Mots vides fréquents dans le contenu web : jamais des entités utiles.
STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "your", "have",
    "are", "was", "were", "will", "their", "there", "when", "what", "about",
    "which", "into", "after", "before", "then", "than", "each", "other",
    "such", "same", "also", "only", "more", "most", "very", "just", "been",
    "being", "does", "doing", "done", "have", "has", "had", "not", "you",
    "can", "could", "should", "would", "may", "might", "must", "shall",
    "read", "more", "one", "two", "new", "click", "here", "menu", "apps",
    "system", "page", "home", "back", "open", "close", "start", "select",
    "download", "install", "update", "settings", "options", "device",
    "phone", "user", "users", "root", "apps", "adb", "fastboot", "via",
    "how", "why", "top", "next", "first", "last", "best", "check", "make",
    "get", "set", "use", "need", "using", "window", "table", "guide",
}

# Faux noms propres : mots anglais/français courants capitalisés en début de
# phrase, qui polluent le graphe s'ils sont pris pour des entités.
FAUX_NOMS_PROPRES = {
    "working", "without", "wireless", "windows", "website", "widescreen",
    "whitelist", "whitelister", "webmaster", "watchers", "currently", "there",
    "these", "those", "their", "would", "should", "could", "might", "about",
    "after", "again", "also", "because", "before", "being", "between", "both",
    "each", "every", "from", "have", "having", "here", "into", "just", "like",
    "make", "more", "most", "much", "must", "need", "only", "other", "over",
    "same", "some", "such", "than", "that", "them", "then", "they", "this",
    "under", "used", "very", "when", "where", "which", "while", "will",
    "with", "your", "data", "yes", "you", "all", "any", "can", "did", "does",
    "few", "for", "get", "has", "his", "its", "may", "new", "not", "now",
    "off", "old", "one", "our", "out", "own", "per", "say", "see", "she",
    "the", "too", "two", "use", "via", "way", "who", "why", "yet", "you",
    "dans", "sur", "pour", "avec", "sans", "pas", "mais", "tout", "tous",
    "cette", "cet", "ces", "qui", "que", "quoi", "dont", "vers", "entre",
    "restants", "restauration", "generale", "general", "retour", "suite",
    "version", "prise", "donnees", "android", "microsoft", "apple", "google",
}

# Marques / noms propres connus utiles au domaine : acceptés même seuls.
NOMS_PROPRES_WHITELIST = {
    "youtube", "wikipedia", "waydroid", "zendesk", "magisk", "kernelsu",
    "orangefox", "twrp", "lineageos", "grapheneos", "microg", "shamiko",
    "lsposed", "xda", "oneplus", "oppo", "realme", "qualcomm", "snapdragon",
    "android", "linux", "github", "google", "microsoft", "samsung",
}


def clean_html(raw: str) -> str:
    text = unescape(raw)
    text = TAG_RE.sub(" ", text)
    # nettoie aussi les balises de script/style pour éviter le bruit
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    # badges/images markdown (shields.io, avatars…) : bruit décoratif qui
    # pollue les entités `url` et fabrique des corrélations sans contenu
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def canonicalize(name: str, entity_type: str) -> str:
    """Ramène un nom à sa forme canonique via les alias du domaine."""
    if entity_type == "op15_file":
        for canon, aliases in FILE_ALIASES.items():
            if name.lower() == canon.lower() or name.lower() in [a.lower() for a in aliases]:
                return canon
    return name


def _extract_op15(text: str) -> list[ExtractedEntity]:
    entities: list[ExtractedEntity] = []
    seen: set[tuple[str, str]] = set()
    for key, pattern in PATTERNS.items():
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = m.group(0).strip()
            et = ENTITY_TYPE_BY_PATTERN[key]
            name = canonicalize(raw, et)
            norm = name.lower()
            if (norm, et) in seen:
                continue
            seen.add((norm, et))
            entities.append(ExtractedEntity(name=name, entity_type=et))
    return entities


def extract_entities(text: str) -> list[ExtractedEntity]:
    entities: list[ExtractedEntity] = []

    # texte sans les mesures pour ne pas confondre "7300 mAh" avec une année
    text_no_measure = MEASURE_RE.sub(" ", text)

    for m in DATE_RE.finditer(text_no_measure):
        entities.append(ExtractedEntity(name=m.group(0), entity_type="date"))

    # années plausibles uniquement (1900-2099)
    for m in YEAR_RE.finditer(text_no_measure):
        y = int(m.group(1))
        if 1900 <= y <= 2099:
            entities.append(ExtractedEntity(name=m.group(0), entity_type="date"))

    for m in URL_RE.finditer(text):
        u = m.group(0)
        # assets décoratifs (badges, images) : jamais des entités
        if "shields.io" in u or ASSET_URL_RE.search(u):
            continue
        entities.append(ExtractedEntity(name=u, entity_type="url"))

    seen = set()
    # mots capitalisés qui sont DÉJÀ des entités op15_* (outils, partitions, …)
    op15_names = {e.name.lower() for e in _extract_op15(text)}
    for m in CAPITALIZED_RE.finditer(text):
        name = m.group(0)
        words = name.split()
        low = name.lower()
        # filtre le bruit : mots vides, expressions trop longues, mots mixtes,
        # faux noms propres, et les noms déjà couverts par le domaine op15_*.
        if (len(words) > 4 or len(name) < 4
                or any(w.lower() in STOPWORDS for w in words)
                or not all(w[0].isupper() for w in words)
                or low in op15_names):
            continue
        # un seul mot capitalisé : accepté seulement si marque/nom connu
        # (whitelist), sinon considéré comme bruit de phrase.
        if len(words) == 1:
            if low in FAUX_NOMS_PROPRES or low not in NOMS_PROPRES_WHITELIST:
                continue
        if name not in seen:
            seen.add(name)
            entities.append(ExtractedEntity(name=name, entity_type="nom_propre"))

    entities.extend(_extract_op15(text))
    return entities


def process_document(doc: RawDocument) -> tuple[str, list[ExtractedEntity]]:
    cleaned = clean_html(doc.text)
    entities = extract_entities(cleaned)
    return cleaned, entities


if __name__ == "__main__":
    sample = RawDocument(
        url="https://example.com",
        title="Test",
        text=("<p>Le OnePlus 15 CPH2747_16.0.8.300(EX01) sous OxygenOS se root "
              "via init_boot.img et Magisk, en fastboot flashing unlock.</p>"),
    )
    cleaned, ents = process_document(sample)
    print(cleaned)
    for e in ents:
        print(e)
