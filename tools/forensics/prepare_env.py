"""
prepare_env.py — prépare et vérifie l'environnement d'exécution après
téléchargement. Actions sûres uniquement : extraction, tests binaires,
vérifications d'intégrité. Aucun flash n'est déclenché ici.

Usage :
    python prepare_env.py            # tout
    python prepare_env.py --check    # seulement vérifier l'existant
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "downloads.json"
STATE = ROOT / "downloads" / "state.json"
REPORT = ROOT / "downloads" / "PREPARE_REPORT.txt"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_platform_tools():
    z = ROOT / "downloads" / "tools" / "platform-tools.zip"
    out = ROOT / "downloads" / "tools" / "platform-tools"
    if not z.exists():
        return "platform-tools.zip absent"
    if out.exists():
        return "déjà extrait"
    with zipfile.ZipFile(z) as arc:
        arc.extractall(ROOT / "downloads" / "tools")
    return "extrait"


def extract_payload_dumper():
    import tarfile
    z = ROOT / "downloads" / "tools" / "payload-dumper-go.tar.gz"
    out = ROOT / "downloads" / "tools" / "payload-dumper"
    if not z.exists():
        return "payload-dumper-go.tar.gz absent"
    if out.exists():
        return "déjà extrait"
    out.mkdir(parents=True, exist_ok=True)
    with tarfile.open(z, "r:gz") as arc:
        try:
            arc.extractall(out, filter="data")
        except TypeError:
            arc.extractall(out)
    return "extrait"

def extract_fastboot_enhance():
    z = ROOT / "downloads" / "tools" / "FastbootEnhance.zip"
    out = ROOT / "downloads" / "tools" / "fastboot-enhance"
    if not z.exists():
        return "FastbootEnhance.zip absent"
    if out.exists() and (out / "FastbootEnhance.exe").exists():
        return "déjà extrait"
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(z) as arc:
        arc.extractall(out)
    return "extrait"

def find_tool(name: str) -> Path | None:
    pt = ROOT / "downloads" / "tools" / "platform-tools" / name
    if pt.exists():
        return pt
    for p in (ROOT / "downloads" / "tools").rglob(name):
        return p
    return None


def run_tool(exe: Path, args: list[str]) -> str:
    try:
        r = subprocess.run([str(exe), *args], capture_output=True, text=True,
                           timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (r.stdout + r.stderr).strip()
    except FileNotFoundError:
        return "introuvable"
    except Exception as e:  # noqa: BLE001
        return f"erreur : {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}

    lines = []
    lines.append("=== PREPARE REPORT — OnePlus 15 CPH2747_16.0.0.204(EX01) ===")

    if not args.check:
        lines.append("\n[extraction]")
        lines.append("  " + extract_platform_tools())
        lines.append("  " + extract_payload_dumper())
        lines.append("  " + extract_fastboot_enhance())

    lines.append("\n[artefacts téléchargés]")
    for art in manifest["artifacts"]:
        dest = Path(art["dest"])
        st = state.get(art["id"], {})
        if dest.exists():
            size = dest.stat().st_size if dest.is_file() else sum(
                f.stat().st_size for f in dest.rglob("*") if f.is_file())
            lines.append(f"  {art['id']:<18} OK   {size/1e6:8.1f} Mo   sha256={sha256_of(dest)[:16]}…")
        elif art.get("large") and art.get("method") == "http":
            lines.append(f"  {art['id']:<18} GROS FICHIER — downloader.py --only {art['id']}")
        elif art.get("method") != "http":
            lines.append(f"  {art['id']:<18} ATTENTE browser_fetch")
        else:
            lines.append(f"  {art['id']:<18} MANQUANT ({st.get('status', '?')})")

    lines.append("\n[outils]")
    for name in ("adb.exe", "fastboot.exe"):
        exe = find_tool(name)
        if exe:
            ver = run_tool(exe, ["--version"]).splitlines()[:1]
            ver_txt = ver[0] if ver else "(version non lue — normal sans appareil branché)"
            lines.append(f"  {name:<12} {exe}  —  {ver_txt}")
        else:
            lines.append(f"  {name:<12} introuvable dans downloads/tools/")

    magisk = ROOT / "downloads" / "tools" / "Magisk.apk"
    if magisk.exists():
        lines.append(f"  Magisk.apk  présent ({magisk.stat().st_size/1e6:.1f} Mo)")

    payload = find_tool("payload-dumper-go*.exe")
    lines.append(f"  payload-dumper  {'présent' if payload else 'manquant'}")

    fbe = find_tool("FastbootEnhance.exe")
    lines.append(f"  FastbootEnhance  {'présent' if fbe else 'manquant (préparation requise)'}")

    lines.append("\n[appareil]")
    adb = find_tool("adb.exe")
    if adb:
        devs = run_tool(adb, ["devices", "-l"])
        lines.append("  " + devs.replace("\n", "\n  "))
    else:
        lines.append("  adb absent — impossibilité de lister l'appareil")

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nRapport écrit : {REPORT}")


if __name__ == "__main__":
    main()