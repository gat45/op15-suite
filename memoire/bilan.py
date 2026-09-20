#!/usr/bin/env python3
"""BILAN — Rapport autonome du projet OnePlus.

Genere un rapport complet et structuré en interrogant :
  1. JARVIX Memory (toutes couches)
  2. Filesystem (inventaire, tailles, dates)
  3. Device (adb si connecté)
  4. Llama.cpp (health, modele charge, stats)
  5. LLM (analyse intelligente du bilan)

Usage :
  python bilan.py                  # rapport complet (terminal)
  python bilan.py --json           # sortie JSON
  python bilan.py --save           # sauvegarde dans reports/
  python bilan.py --short          # version condensée
  python bilan.py --analyze        # envoie au LLM pour analyse
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent
SRC = PKG_ROOT / "src"
sys.path.insert(0, str(SRC))
# Note: os.chdir removed to avoid side effects when imported by MCP server

from jarvix_memory.router import MemoryRouter  # noqa: E402

# Racine du projet a scanner : JARVIX_PROJECT_ROOT > cwd > parent du package
import os as _os  # noqa: E402
ONEPLUS_ROOT = Path(_os.environ.get("JARVIX_PROJECT_ROOT") or _os.getcwd())
REPORTS_DIR = Path(_os.environ.get("JARVIX_REPORTS_DIR") or PKG_ROOT / "reports")
LLAMA_BASE_URL = _os.environ.get("JARVIX_LLAMA_URL", "http://127.0.0.1:8080")


def format_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def get_memory_stats(router: MemoryRouter) -> dict:
    return router.stats()


def get_layer_items(router: MemoryRouter, layer_name: str, limit: int = 50) -> list:
    layer = getattr(router, layer_name, None)
    if not layer:
        return []
    try:
        return layer.list_all(limit=limit)
    except Exception:
        return []


def get_strategies(router: MemoryRouter) -> list:
    try:
        return router.strategy.leaderboard(limit=10)
    except Exception:
        return []


def get_recovery_active(router: MemoryRouter) -> list:
    try:
        return router.recovery.active_recoveries()
    except Exception:
        return []


# ── Llama.cpp ──────────────────────────────────────────────────

def check_llama_health() -> dict:
    """Health check via /v1/models + /health."""
    result = {
        "running": False,
        "model": None,
        "model_size": None,
        "context_size": None,
        "port": 8080,
        "uptime": None,
    }
    try:
        req = urllib.request.Request(f"{LLAMA_BASE_URL}/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            result["running"] = True
            models = data.get("data", [])
            if models:
                result["model"] = models[0].get("id", "unknown")
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        pass

    # /health pour plus de details
    try:
        req = urllib.request.Request(f"{LLAMA_BASE_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            result["status"] = data.get("status", "unknown")
            if "slots" in data:
                slots = data["slots"]
                if slots:
                    slot = slots[0] if isinstance(slots, list) else slots
                    result["context_size"] = slot.get("n_ctx", None)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        pass

    return result


def query_llm(prompt: str, max_tokens: int = 500) -> str:
    """Envoie un prompt au LLM local et retourne la reponse."""
    try:
        payload = json.dumps({
            "model": "local",
            "messages": [
                {"role": "system", "content": "Reponds en francais, sois tres bref (5 lignes max). PAS de chain-of-thought, reponds directement."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{LLAMA_BASE_URL}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                # Qwen met la reponse dans reasoning_content
                content = msg.get("content", "") or ""
                reasoning = msg.get("reasoning_content", "") or ""
                # Prefer content; if empty, try reasoning (strip thinking tags)
                raw = content or reasoning
                if not raw:
                    return "[Pas de contenu]"
                # Strip <think>...</think> blocks if present
                import re
                cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                return cleaned if cleaned else raw
    except Exception as e:
        return f"[LLM indisponible : {e}]"
    return "[Pas de reponse]"


# ── Filesystem ─────────────────────────────────────────────────

def scan_filesystem() -> dict:
    counts = {}
    sizes = {}
    for ext in [".py", ".md", ".sh", ".ps1", ".kt", ".java", ".json",
                ".log", ".gguf", ".so", ".xml", ".yml", ".yaml", ".bat"]:
        counts[ext] = 0
        sizes[ext] = 0

    skip = {".git", ".gradle", ".kotlin", "__pycache__", "node_modules",
            ".cache", "build", ".idea", ".vscode"}

    for f in ONEPLUS_ROOT.rglob("*"):
        if not f.is_file():
            continue
        if any(s in f.parts for s in skip):
            continue
        ext = f.suffix.lower()
        if ext in counts:
            counts[ext] += 1
            try:
                sizes[ext] += f.stat().st_size
            except OSError:
                pass

    return {"counts": counts, "sizes": sizes}


def check_device() -> dict:
    result = {"connected": False, "model": None, "android": None, "root": False}
    try:
        out = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True, text=True, timeout=5
        )
        lines = [l for l in out.stdout.strip().split("\n")
                 if "device" in l and "List" not in l]
        if lines:
            result["connected"] = True
            model = subprocess.run(
                ["adb", "shell", "getprop", "ro.product.model"],
                capture_output=True, text=True, timeout=5
            )
            result["model"] = model.stdout.strip()
            android = subprocess.run(
                ["adb", "shell", "getprop", "ro.build.version.release"],
                capture_output=True, text=True, timeout=5
            )
            result["android"] = android.stdout.strip()
            root = subprocess.run(
                ["adb", "shell", "su", "-c", "id"],
                capture_output=True, text=True, timeout=5
            )
            result["root"] = "uid=0" in root.stdout
    except Exception:
        pass
    return result


def safe_content(m, maxlen=200):
    return (m.get("content", "") or "")[:maxlen]


def generate_report(save=False, as_json=False, short=False, analyze=False) -> str:
    router = MemoryRouter()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Collecte
    mem_stats = get_memory_stats(router)
    total_mem = mem_stats.get("total_memories", 0)

    facts = get_layer_items(router, "semantic", 20 if not short else 10)
    decisions = get_layer_items(router, "decision", 15 if not short else 5)
    episodic = get_layer_items(router, "episodic", 10 if not short else 5)
    actions = get_layer_items(router, "action", 10)
    learning = get_layer_items(router, "learning", 10)
    evidence = get_layer_items(router, "evidence", 20)
    graph_items = get_layer_items(router, "graph", 50)
    world_items = get_layer_items(router, "world", 20)
    strategies = get_strategies(router)
    recovery = get_recovery_active(router)

    fs = scan_filesystem()
    total_files = sum(fs["counts"].values())
    total_size = sum(fs["sizes"].values())

    device = check_device()
    llama = check_llama_health()

    # ── Construction ──
    lines = []
    lines.append("=" * 60)
    lines.append(f"  BILAN PROJET ONEPLUS — {now}")
    lines.append("=" * 60)

    # Device
    lines.append("")
    lines.append("## DEVICE")
    if device["connected"]:
        lines.append(f"  Statut     : [OK] Connecte")
        lines.append(f"  Modele     : {device['model']}")
        lines.append(f"  Android    : {device['android']}")
        lines.append(f"  Root       : {'[OK]' if device['root'] else '[NON]'}")
    else:
        lines.append("  Statut     : [!] Deconnecte")

    # Llama.cpp
    lines.append("")
    lines.append("## LLAMA.CPP")
    if llama["running"]:
        lines.append(f"  Statut     : [OK] En cours d'execution")
        lines.append(f"  Modele     : {llama['model'] or 'inconnu'}")
        lines.append(f"  Port       : {llama['port']}")
        if llama["context_size"]:
            lines.append(f"  Contexte   : {llama['context_size']} tokens")
    else:
        lines.append(f"  Statut     : [!] Arrete (port {LLAMA_BASE_URL})")

    # Memoire
    lines.append("")
    lines.append(f"## MEMOIRE ({total_mem} souvenirs)")
    for name in ["episodic", "semantic", "procedural", "decision", "graph",
                 "evidence", "action", "strategy", "learning", "recovery",
                 "world", "multimodal"]:
        c = mem_stats.get(name, 0)
        if c > 0:
            lines.append(f"  {name:15s} : {c}")

    # Faits cles
    if facts:
        lines.append("")
        lines.append(f"## FAITS CLES ({len(facts)})")
        for f in facts:
            conf = f.get("confidence", 0)
            marker = "*" if conf >= 0.9 else "~" if conf >= 0.7 else "."
            lines.append(f"  {marker} [{conf:.0%}] {safe_content(f, 120)}")

    # Decisions
    if decisions:
        lines.append("")
        lines.append(f"## DECISIONS ({len(decisions)})")
        for d in decisions:
            lines.append(f"  - {safe_content(d, 150)}")

    # Strategies
    if strategies:
        lines.append("")
        lines.append("## STRATEGIES")
        for s in strategies:
            rate = s.get("rate", 0)
            lines.append(f"  {s.get('name', '?'):20s} : {rate:.0%} "
                         f"({s.get('attempts', 0)} tentatives)")

    # Preuves
    if evidence:
        lines.append("")
        lines.append("## PREUVES")
        for e in evidence:
            status = e.get("status", "unknown")
            marker = "[OK]" if status == "verified" else "[FAIL]" if status == "rejected" else "[...]"
            lines.append(f"  {marker} [{status}] {safe_content(e, 100)}")

    # Recoveries actives
    if recovery:
        lines.append("")
        lines.append("## RECUPERATIONS ACTIVES")
        for r in recovery:
            meta = json.loads(r.get("metadata", "{}")) if isinstance(r.get("metadata"), str) else {}
            lines.append(f"  [!] {safe_content(r, 120)} "
                         f"(tentative {meta.get('attempt', '?')})")

    # World state
    if world_items:
        lines.append("")
        lines.append("## ETAT DU MONDE")
        for w in world_items:
            lines.append(f"  {safe_content(w, 80)}")

    # Apprentissages
    if learning:
        lines.append("")
        lines.append("## APPRENTISSAGES")
        for l in learning:
            score = l.get("confidence", 0)
            lines.append(f"  - score {score:.0%} - {safe_content(l, 100)}")

    # Actions recentes
    if actions:
        lines.append("")
        lines.append("## ACTIONS RECENTES")
        for a in actions:
            status = a.get("status", "unknown")
            marker = "[OK]" if status == "executed" else "[...]"
            lines.append(f"  {marker} [{status}] {safe_content(a, 100)}")

    # Graphe
    lines.append("")
    lines.append(f"## GRAPHE : {len(graph_items)} noeuds")

    # Filesystem
    lines.append("")
    lines.append(f"## FILESYSTEM ({total_files} fichiers, {format_size(total_size)})")
    for ext in [".py", ".md", ".sh", ".kt", ".json", ".so", ".gguf", ".log"]:
        c = fs["counts"].get(ext, 0)
        s = fs["sizes"].get(ext, 0)
        if c > 0:
            lines.append(f"  {ext:8s} : {c:6d} fichiers  {format_size(s):>10s}")

    lines.append("")
    lines.append("=" * 60)
    lines.append(f"  Rapport genere le {now}")
    lines.append(f"  Base memoire : {PKG_ROOT / 'jarvix_memory.db'}")
    if llama["running"]:
        lines.append(f"  LLM : {llama['model']} (port {llama['port']})")
    lines.append("=" * 60)

    report = "\n".join(lines)

    # ── Analyse LLM ──
    if analyze and llama["running"]:
        lines.append("")
        lines.append("## ANALYSE LLM")
        lines.append("")

        # Resume compact pour le LLM
        compact = (
            f"Device: {'connecte ' + device.get('model', '?') if device['connected'] else 'deconnecte'}\n"
            f"LLM: {llama.get('model', 'arrete')} (port {llama['port']})\n"
            f"Memoire: {total_mem} souvenirs\n"
            f"Strategies: {', '.join(s.get('name', '?') + ' ' + str(int(s.get('rate', 0)*100)) + '%' for s in strategies)}\n"
            f"Recuperations actives: {len(recovery)}\n"
            f"Preuves: {len(evidence)} ({sum(1 for e in evidence if e.get('status') == 'verified')} verifiees)\n"
            f"Filesystem: {total_files} fichiers, {format_size(total_size)}\n"
            f"GGUF: {fs['counts'].get('.gguf', 0)} fichiers, {format_size(fs['sizes'].get('.gguf', 0))}"
        )
        prompt = (
            "Bilan projet OnePlus. En 5 lignes max, donne "
            "3 points critiques et 1 recommandation.\n\n"
            f"{compact}"
        )
        analysis = query_llm(prompt, max_tokens=800)
        lines.append(analysis)
        report = "\n".join(lines)

    if as_json:
        data = {
            "timestamp": now,
            "device": device,
            "llama": llama,
            "memory": mem_stats,
            "total_memories": total_mem,
            "facts": [{"content": safe_content(f), "confidence": f.get("confidence", 0)} for f in facts],
            "decisions": [{"content": safe_content(d)} for d in decisions],
            "strategies": strategies,
            "evidence": [{"content": safe_content(e), "status": e.get("status")} for e in evidence],
            "recovery": [{"content": safe_content(r)} for r in recovery],
            "world": [{"content": safe_content(w)} for w in world_items],
            "learning": [{"content": safe_content(l)} for l in learning],
            "actions": [{"content": safe_content(a), "status": a.get("status")} for a in actions],
            "graph_nodes": len(graph_items),
            "filesystem": {"counts": fs["counts"], "total_files": total_files, "total_size": total_size},
        }
        report = json.dumps(data, indent=2, default=str)

    if save:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        ext = ".json" if as_json else ".md"
        path = REPORTS_DIR / f"bilan_{ts}{ext}"
        path.write_text(report, encoding="utf-8")
        print(f"Sauvegarde : {path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="BILAN — Rapport autonome projet OnePlus")
    parser.add_argument("--json", action="store_true", help="Sortie JSON")
    parser.add_argument("--save", action="store_true", help="Sauvegarder dans reports/")
    parser.add_argument("--short", action="store_true", help="Version condensee")
    parser.add_argument("--analyze", action="store_true", help="Analyse LLM du bilan")
    args = parser.parse_args()

    report = generate_report(save=args.save, as_json=args.json,
                             short=args.short, analyze=args.analyze)
    print(report)


if __name__ == "__main__":
    main()
