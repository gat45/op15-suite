"""
pre_flight.py — Contrôle pré-vol avant chaque opération sur l'appareil.

Vérifie les prérequis critiques pour : déverrouillage, flash 400, root.
Bloque avec une erreur claire si un prérequis manque. Idéal avant toute
commande destructive (s'appuie sur les artefacts téléchargés et vérifiés).

Usage :
    python pre_flight.py --check unlock     # avant fastboot flashing unlock
    python pre_flight.py --check flash400   # avant le Regional Flasher
    python pre_flight.py --check root       # avant de flasher init_boot patché
    python pre_flight.py --check all        # tout vérifier
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLATFORM = ROOT / "downloads" / "tools" / "platform-tools"
FASTBOOT = PLATFORM / "fastboot.exe"
ADB = PLATFORM / "adb.exe"
STATE = ROOT / "downloads" / "state.json"
ROLLBACK = ROOT / "downloads" / "rollback"
B400 = ROOT / "downloads" / "firmware" / "build-400"


def ok(msg):
    print(f"  [OK] {msg}")


def warn(msg):
    print(f"  [!]  {msg}")


def err(msg):
    print(f"  [XX] {msg}")


def check_fastboot():
    if not FASTBOOT.exists():
        err("fastboot.exe absent")
        return False
    import subprocess
    r = subprocess.run([str(FASTBOOT), "devices"], capture_output=True, text=True,
                       timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    out = (r.stdout + r.stderr).strip()
    if any("fastboot" in line for line in out.splitlines()):
        ok("appareil visible en fastboot")
        return True
    err("aucun appareil en fastboot")
    return False


def check_artefact(aid, label):
    if not STATE.exists():
        err("state.json absent")
        return False
    s = json.loads(STATE.read_text(encoding="utf-8"))
    st = s.get(aid, {}).get("status")
    if st in ("ok", "ok_large"):
        ok(f"{label} ({st})")
        return True
    err(f"{label} : statut '{st}' — relancer downloader.py --only {aid}")
    return False


def check_rollback():
    missing = [f for f in ("boot_stock_400.img", "init_boot_stock_400.img")
               if not (ROLLBACK / f).exists()]
    if missing:
        err(f"backups stock manquants dans rollback/ : {', '.join(missing)}")
        return False
    ok("backups stock 400 présents (boot + init_boot)")
    return True


def check_initboot400():
    if not (B400 / "init_boot.img").exists():
        err("init_boot.img build 400 absent")
        return False
    ok("init_boot.img 400 présent (extrait du flasher)")
    return True


def check_unlock():
    checks = [check_fastboot()]
    checks.append(check_artefact("platform-tools", "platform-tools"))
    return all(checks)


def check_flash400():
    checks = [check_fastboot(),
              check_artefact("regional-flasher", "Regional Flasher GLO 400"),
              check_artefact("firmware-400", "firmware 400 extrait"),
              check_rollback()]
    ok_ = all(checks)
    warn("RAPPEL : le passage en 400 est IRREVERSIBLE (anti-rollback/eFuse).")
    warn("         Retour en 204 impossible après. Sauvegarde des données faite ?")
    return ok_


def check_root():
    checks = [check_fastboot(),
              check_artefact("magisk", "Magisk APK"),
              check_artefact("kernel-susfs-op15", "kernel SUSFS OP15"),
              check_initboot400(),
              check_rollback()]
    return all(checks)


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", required=True,
                    choices=["unlock", "flash400", "root", "all"])
    args = ap.parse_args()

    print(f"=== PRÉ-VOL : {args.check} ===")
    if args.check == "unlock":
        ok_ = check_unlock()
    elif args.check == "flash400":
        ok_ = check_flash400()
    elif args.check == "root":
        ok_ = check_root()
    else:
        ok_ = (check_unlock() and check_flash400() and check_root())

    print("\n=== RÉSULTAT ===")
    if ok_:
        print("Prérequis OK — opération autorisée.")
        return 0
    print("Prérequis NON satisfaits — corriger avant d'opérer.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
