"""
downloader.py — téléchargement HTTP fiable des artefacts du manifest.

Traite les entrées downloads.json en method="http" (dont github_repo).
Emprunte les en-têtes d'un navigateur Chromium pour éviter le blocage naïf,
reprend les téléchargements interrompus et vérifie les empreintes SHA-256.
L'état de chaque artefact est persisté dans downloads/state.json.

Usage :
    python downloader.py                 # tout le manifest http
    python downloader.py --only magisk   # un artefact précis
    python downloader.py --verify        # re-vérifie ce qui est déjà là
"""

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import requests

from artifact_registry import ArtifactRegistry, mime_of

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "downloads.json"
STATE = ROOT / "downloads" / "state.json"

UA_CHROMIUM = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")
HEADERS = {
    "User-Agent": UA_CHROMIUM,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr-FR;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def resolve_github_latest(repo: str, pattern: str) -> str:
    api = f"https://api.github.com/repos/{repo}/releases/latest"
    r = requests.get(api, headers={"User-Agent": "op15-agent", "Accept": "application/vnd.github+json"}, timeout=30)
    r.raise_for_status()
    tag = r.json().get("tag_name", "")
    rx = re.compile(pattern, re.I)
    for a in r.json().get("assets", []):
        if rx.search(a["name"]):
            return a["browser_download_url"]
    raise FileNotFoundError(f"aucun asset {pattern!r} dans {repo} tag={tag}")


def download_url(url: str, dest: Path, timeout: int = 1800) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    mode = "ab" if tmp.exists() else "wb"
    resume_from = tmp.stat().st_size if mode == "ab" else 0
    headers = dict(HEADERS)  # copie locale : jamais de header résiduel d'un autre artefact
    if resume_from:
        headers["Range"] = f"bytes={resume_from}-"
    with requests.get(url, headers=headers, stream=True, timeout=60,
                      allow_redirects=True) as r:
        if resume_from and r.status_code == 416:
            tmp.rename(dest)
            return dest.stat().st_size
        r.raise_for_status()
        if resume_from and r.status_code != 206:
            mode = "wb"
            resume_from = 0
            tmp.write_bytes(b"")
        total = 0
        last = time.time()
        deadline = time.time() + timeout
        with open(tmp, mode) as f:
            for chunk in r.iter_content(1 << 20):
                if time.time() > deadline:
                    raise TimeoutError(
                        f"téléchargement annulé après {timeout}s (reprise possible : "
                        f"relancez --only)")
                f.write(chunk)
                total += len(chunk)
                if time.time() - last > 2:
                    sys.stdout.write(f"\r  {total/1e6:.1f} Mo")
                    sys.stdout.flush()
                    last = time.time()
        print()
        tmp.rename(dest)
    return dest.stat().st_size


def process_artifact(art: dict, state: dict) -> None:
    aid = art["id"]
    dest = Path(art["dest"])
    print(f"[{aid}] {art['name']}")
    try:
        if art.get("method") != "http":
            print("  (method != http — délégué à browser_fetch.py)")
            state[aid] = {"status": "browser", "dest": str(dest)}
            return
        url = art.get("url") or resolve_github_latest(art["github_repo"], art["asset_pattern"])
        print(f"  URL : {url}")
        size = download_url(url, dest)
        sha = sha256_of(dest) if dest.is_file() else ""
        expected = art.get("sha256", "")
        if expected and expected.lower() != sha:
            state[aid] = {"status": "checksum_mismatch", "size": size,
                          "sha256": sha, "expected": expected}
            print(f"  !! SHA-256 mismatch : attendu {expected} / obtenu {sha}")
            return
        state[aid] = {"status": "ok", "size": size, "sha256": sha,
                      "url": url, "dest": str(dest)}
        reg = ArtifactRegistry()
        try:
            reg.register(url=url, path=dest, sha256=sha, size=size,
                         mime=mime_of(dest), aspect=art.get("aspect", ""),
                         source="manifest")
        finally:
            reg.close()
        print(f"  OK : {size} octets, sha256={sha[:16]}…")
    except Exception as e:  # noqa: BLE001
        state[aid] = {"status": "error", "error": str(e)}
        print(f"  ERREUR : {e}")


def main():
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=str, default=None)
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    state = load_state()

    if args.verify:
        reg = ArtifactRegistry()
        try:
            for art in manifest["artifacts"]:
                dest = Path(art["dest"])
                if dest.exists() and dest.is_file():
                    sha = sha256_of(dest)
                    reg.register(url=art.get("url", "") or dest.name, path=dest,
                                 sha256=sha, size=dest.stat().st_size,
                                 mime=mime_of(dest), aspect=art.get("aspect", ""),
                                 source="manifest")
                    state[art["id"]] = {"status": "ok", "size": dest.stat().st_size,
                                        "sha256": sha, "dest": str(dest)}
                    print(f"[{art['id']}] {art['name']} — {dest.stat().st_size} octets, "
                          f"sha256={sha[:16]}…")
                elif dest.exists() and dest.is_dir():
                    # dossier (clone git, driver manuel) : présent sans hash
                    state[art["id"]] = {"status": "ok", "dest": str(dest)}
                    print(f"[{art['id']}] {art['name']} — dossier présent")
                else:
                    status = "absent"
                    if art.get("large"):
                        status = "absent_large"
                    state[art["id"]] = {"status": status, "dest": str(dest)}
                    print(f"[{art['id']}] absent : {dest}")
        finally:
            reg.close()
            save_state(state)
        return

    for art in manifest["artifacts"]:
        if args.only and art["id"] != args.only:
            continue
        if art.get("large") and not args.only:
            print(f"[{art['id']}] GROS FICHIER ({art.get('size_hint', '?')}) — "
                  f"non téléchargé automatiquement. Lancer : python downloader.py --only {art['id']}")
            continue
        if Path(art["dest"]).exists() and state.get(art["id"], {}).get("status") == "ok":
            print(f"[{art['id']}] déjà téléchargé — skip")
            continue
        process_artifact(art, state)
        save_state(state)
    print("\nÉtat : downloads/state.json")


if __name__ == "__main__":
    main()