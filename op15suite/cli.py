"""op15-suite — CLI unifié du projet OnePlus 15 (mémoires, RAG, diagnostics, campagne)."""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # racine du repo op15-suite
TOOLS = ROOT / "tools"
FORENSICS = TOOLS / "forensics"
MEMOIRE = ROOT / "memoire"

PY = sys.executable or "python"
LLM_URL = "http://127.0.0.1:18181"  # serveur llama.cpp (synthèse upia)


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd or ROOT, encoding="utf-8", errors="replace")
    return r.returncode


def cmd_doctor(args):
    cmd = [PY, str(TOOLS / "mcp_doctor.py")]
    if args.json:
        cmd += ["--json"]
    if args.out:
        cmd += ["--out", args.out]
    return run(cmd)


def cmd_smoke(args):
    return run([PY, str(TOOLS / "test_upia_mcp.py"), "smoke"])


def cmd_rag(args):
    return run([PY, str(FORENSICS / "rag_bm25.py"), args.question, "--top", str(args.top)],
               cwd=FORENSICS)


def cmd_learn(args):
    return run([PY, str(FORENSICS / "run.py"), "--learn", "--local", args.folder],
               cwd=FORENSICS)


def cmd_report(args):
    return run([PY, str(TOOLS / "report_pipeline.py"), args.file])


def cmd_gguf(args):
    return run([PY, str(TOOLS / "gguf_arch.py"), args.path])


def cmd_bilan(args):
    return run([PY, str(MEMOIRE / "bilan.py")], cwd=MEMOIRE)


GATES_DOC = """Gates de la campagne MoE §8.1-4 (campaign_moe.py du harness) :
G0  device présent
G1  hashes modèle/lib/skel (§8.1)
G2  baseline froide/chaude n=5, CV<3% (§8.2)
G3  patch trace seul déployé (§8.3)
G4  capture trace expert réelle (§8.4)
G5  parse + attribution HTP (§8.5-6, bonus)
G6  replay budgets RPCMEM (§8.7, bonus)
G7  gate validate_moe_cache (§8.8-9, bonus)
"""


def cmd_campaign(args):
    script = Path(args.harness) / "campaign_moe.py"
    if not script.exists():
        # --list est de la doc pure : ne dépend pas du harness
        if args.list:
            print(GATES_DOC)
            print(f"(harness introuvable : {script} — exécution réelle requiert "
                  "le harness local, cf. --harness)")
            return 0
        print(f"campaign_moe.py introuvable : {script}\n"
              "(le harness geniex_harness reste hors repo — passer --harness <chemin>)")
        return 2
    cmd = [PY, str(script)]
    if args.model:
        cmd += ["--model", args.model]
    if args.list:
        cmd += ["--list"]
    return run(cmd)


def cmd_status(args):
    """État global de l'environnement en 1 commande — le point d'entrée d'un
    agent qui découvre la machine : repo, registre MCP, device, harness,
    LLM local, mémoires. Sortie : verdicts + « prochaine action » conseillée.
    """
    checks: list[tuple[str, str, str]] = []  # (état, sujet, note/hint)

    # 1. repo
    missing = [p for p in ("tools/mcp_doctor.py", "tools/forensics/rag_bm25.py",
                           "memoire/mcp_server.py", "opencode.json")
               if not (ROOT / p).exists()]
    checks.append(("OK" if not missing else "FAIL", "repo op15-suite",
                   "fichiers clés présents" if not missing
                   else f"manquants: {missing}"))

    # 2. registre MCP (qui devrait tourner)
    try:
        reg = json.loads((ROOT / "opencode.json").read_text(encoding="utf-8"))
        servers = reg.get("mcp") or reg.get("mcpServers") or {}
        enabled = [n for n, c in servers.items()
                   if isinstance(c, dict) and c.get("enabled", True)]
        checks.append(("OK", "registre MCP", f"{len(enabled)} serveurs: {', '.join(sorted(enabled))}"
                       " — test réel: op15 doctor"))
    except Exception as e:
        checks.append(("FAIL", "registre MCP", f"illisible: {e}"))

    # 3. device OP15
    device_ok = False
    try:
        r = subprocess.run(["adb", "get-state"], capture_output=True, text=True,
                           timeout=8, encoding="utf-8", errors="replace")
        # succès = stdout EXACTEMENT "device". Piège : l'échec renvoie sur
        # stderr "error: no devices/emulators found" — qui CONTIENT "device"
        # comme sous-chaîne. Ne jamais tester par inclusion.
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode == 0 and out == "device":
            device_ok = True
            checks.append(("OK", "device OP15", "branché (adb) — campagne possible: "
                           "op15 campaign --model <GGUF>"))
        else:
            checks.append(("WARN", "device OP15", f"adb: {(err or out or 'exit ' + str(r.returncode))[:60]}"
                           " — campagne §8 en attente de branchement"))
    except FileNotFoundError:
        checks.append(("WARN", "device OP15", "adb absent du PATH — "
                       "https://developer.android.com/tools/releases/platform-tools"))
    except subprocess.TimeoutExpired:
        checks.append(("WARN", "device OP15", "adb ne répond pas (daemon démondé ?)"))

    # 4. harness (campagne réelle)
    harness = Path(args.harness)
    ok_h = (harness / "campaign_moe.py").exists()
    checks.append(("OK" if ok_h else "WARN", "harness geniex",
                   str(harness) if ok_h else
                   f"campaign_moe.py introuvable sous {harness} — "
                   "dry-run possible sans (op15 campaign --list)"))

    # 5. LLM local (synthèse upia)
    try:
        with urllib.request.urlopen(f"{LLM_URL}/v1/models", timeout=2) as resp:
            checks.append(("OK" if resp.status == 200 else "WARN",
                           f"LLM local {LLM_URL}",
                           f"HTTP {resp.status} — upia_ask utilisable"))
    except Exception as e:
        checks.append(("WARN", f"LLM local {LLM_URL}",
                       f"absent ({type(e).__name__}) — synthèse upia en fallback "
                       "déterministe; démarrer llama-server si nécessaire"))

    # 6. mémoires (DB runtime dérivables)
    jarvix = MEMOIRE / "jarvix_memory.db"
    rag = FORENSICS / "memory.db"
    checks.append(("OK" if jarvix.exists() else "WARN", "JARVIX",
                   f"{jarvix.name} présent" if jarvix.exists() else
                   "DB absente — recréée à la première écriture (MCP ou bilan.py)"))
    checks.append(("OK" if rag.exists() else "WARN", "RAG forensics",
                   f"{rag.name} présent" if rag.exists() else
                   "DB absente — construire par ingestion: op15 learn <dossier>"))

    icons = {"OK": "[OK]  ", "WARN": "[WARN]", "FAIL": "[FAIL]"}
    print("=== op15 status — état de l'environnement ===")
    for st, subject, note in checks:
        print(f"{icons[st]} {subject:22s} {note}")
    n_fail = sum(1 for s, _, _ in checks if s == "FAIL")
    print("---")
    print("prochaine action conseillée :")
    if n_fail:
        print("  0. réparer les [FAIL] ci-dessus (repo incomplet ?)")
    print("  1. op15 doctor          # vérifier que les MCP répondent vraiment")
    if device_ok:
        print("  2. op15 campaign --model <GGUF>   # device branché : lancer §8.1-4")
    else:
        print("  2. (device absent) op15 campaign --list   # revoir les gates §8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="op15-suite",
                                 description="OnePlus 15 knowledge & MoE pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", help="santé des MCP (handshake + sonde réelle)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out", help="écrire le rapport JSON dans ce fichier")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("smoke", help="non-régression serveur MCP upia (4 outils, ~1s)")
    p.set_defaults(fn=cmd_smoke)

    p = sub.add_parser("rag", help="interroger le RAG forensics")
    p.add_argument("question")
    p.add_argument("--top", type=int, default=3)
    p.set_defaults(fn=cmd_rag)

    p = sub.add_parser("learn", help="ingérer un dossier de docs dans le RAG")
    p.add_argument("folder")
    p.set_defaults(fn=cmd_learn)

    p = sub.add_parser("report", help="passer un rapport .md dans le pipeline 3 mémoires")
    p.add_argument("file")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("gguf", help="lire l'arch d'un GGUF (diagnostic build)")
    p.add_argument("path")
    p.set_defaults(fn=cmd_gguf)

    p = sub.add_parser("bilan", help="bilan JARVIX (mémoire locale)")
    p.set_defaults(fn=cmd_bilan)

    p = sub.add_parser("status", help="état global : repo, MCP, device, harness, LLM, mémoires")
    p.add_argument("--harness", default=os.environ.get("OP15_HARNESS", "E:/oneplus/geniex_harness"),
                   help="chemin du harness (défaut: env OP15_HARNESS)")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("campaign", help="campagne MoE §8.1-4 (device requis)")
    p.add_argument("--model", help="chemin du GGUF")
    p.add_argument("--harness", default=os.environ.get("OP15_HARNESS", "E:/oneplus/geniex_harness"),
                   help="chemin du harness (défaut: env OP15_HARNESS)")
    p.add_argument("--list", action="store_true")
    p.set_defaults(fn=cmd_campaign)

    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
