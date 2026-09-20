"""op15-suite — CLI unifié du projet OnePlus 15 (mémoires, RAG, diagnostics, campagne)."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # racine du repo op15-suite
TOOLS = ROOT / "tools"
FORENSICS = TOOLS / "forensics"
MEMOIRE = ROOT / "memoire"

PY = sys.executable or "python"


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


def cmd_campaign(args):
    script = Path(args.harness) / "campaign_moe.py"
    if not script.exists():
        print(f"campaign_moe.py introuvable : {script}\n"
              "(le harness geniex_harness reste hors repo — passer --harness <chemin>)")
        return 2
    cmd = [PY, str(script)]
    if args.model:
        cmd += ["--model", args.model]
    if args.list:
        cmd += ["--list"]
    return run(cmd)


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

    p = sub.add_parser("campaign", help="campagne MoE §8.1-4 (device requis)")
    p.add_argument("--model", help="chemin du GGUF")
    p.add_argument("--harness", default="E:/oneplus/geniex_harness")
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
