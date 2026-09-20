"""mcp_doctor — vérifie que les 4 MCP du registre canonique se chargent réellement.

À lancer au démarrage d'une session (avant de faire confiance aux outils MCP) :
    py -3.12 tools/mcp_doctor.py

Chaque serveur est lancé exactement comme opencode le fait (commande + args de
opencode.json), reçoit un handshake JSON-RPC `initialize`, et doit répondre un
serverInfo. Un serveur qui ne répond pas = il sera down dans opencode aussi.
Sortie : exit 0 si tout est vert, 1 sinon (scriptable en non-régression).

Robuste par construction : lecture en thread + hard timeout — un serveur qui
hang ne bloque jamais le docteur.
"""
import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# registre overridable : variable d'env MCP_DOCTOR_REGISTRY > opencode.json du repo
_CFG_PATH = Path(os.environ.get("MCP_DOCTOR_REGISTRY") or (ROOT / "opencode.json"))
CFG = json.loads(_CFG_PATH.read_text(encoding="utf-8"))

HANDSHAKE_TIMEOUT = 30.0   # npx froid peut être lent, mais pas illimité
TOOLS_TIMEOUT = 15.0
PROBE_TIMEOUT = 20.0

# Ce que le serveur DOIT exposer pour être déclaré utile (au-delà du handshake)
REQUIRED_TOOLS = {
    "jarvix-memory": {"memory_search", "semantic_add", "episodic_log", "procedural_skill"},
    "upia": {"update", "ask"},  # noms tolérés en sous-chaîne
    "unified_recall": set(),    # pas encore de contrat figé
    "graft": set(),
}

# Sonde RÉELLE par serveur : un appel d'outil lecture seule, exactement comme
# un client le ferait. tools/list prouve le contrat ; l'appel prouve que ça
# marche vraiment (config, permissions, chemins, dépendances).
PROBES = {
    "jarvix-memory": ("memory_search",
                      {"query": "deadlock stdin MCP", "limit": 3},
                      15.0),
    "upia": ("upia_status", {}, 20.0),
    "unified_recall": ("unified_recall",
                       {"query": "ggml-hexagon HTP", "top_k": 2},
                       45.0),  # cold-start index RAG : 15-25 s observés
    "graft": None,  # 0 outils exposés : rien à sonder (handshake seul)
}


class Reader:
    """Lit stdout du serveur dans un thread → queue (jamais de readline bloquant)."""

    def __init__(self, stream):
        self.q: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, args=(stream,), daemon=True).start()

    def _pump(self, stream):
        try:
            for line in iter(stream.readline, ""):
                self.q.put(line)
        except (OSError, ValueError):
            pass
        self.q.put(None)  # EOF


def rpc(reader: Reader, proc: subprocess.Popen, payload: dict, timeout: float) -> dict | None:
    """Envoie une requête JSON-RPC et attend la réponse au même id (avec deadline réelle)."""
    try:
        proc.stdin.write(json.dumps(payload) + "\n")
        proc.stdin.flush()
    except OSError:
        return None
    deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            return None
        try:
            line = reader.q.get(timeout=remaining)
        except queue.Empty:
            return None
        if line is None:
            return None
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue  # logs parasites sur stdout : on saute
        if msg.get("id") == payload.get("id"):
            return msg


def notify(proc: subprocess.Popen, method: str) -> None:
    """Notification fire-and-forget (jamais d'attente de réponse)."""
    try:
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        proc.stdin.flush()
    except OSError:
        pass


def tool_call(reader: Reader, proc: subprocess.Popen, name: str,
              arguments: dict, timeout: float) -> tuple[bool, str]:
    """tools/call réel. Retourne (ok, résumé court)."""
    resp = rpc(reader, proc, {"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                              "params": {"name": name, "arguments": arguments}},
               timeout)
    if resp is None:
        return False, f"{name} : pas de réponse en {timeout:.0f}s"
    if "error" in resp:
        return False, f"{name} : erreur RPC {str(resp['error'])[:80]}"
    result = resp.get("result", {})
    if result.get("isError"):
        parts = result.get("content") or []
        txt = " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return False, f"{name} : isError — {txt[:80]}"
    parts = result.get("content") or []
    txt = " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if not txt.strip():
        return False, f"{name} : réponse vide"
    return True, f"{name} → {txt[:60].replace(chr(10), ' ')}"


def resolve_cmd(cmd: list[str]) -> list[str]:
    """Résout les shims Windows : npx.cmd ne se lance pas via Popen direct.

    shutil.which trouve le .cmd ; CreateProcess ne l'exécute que via cmd.exe.
    """
    resolved = shutil.which(cmd[0])
    if resolved and resolved.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", resolved, *cmd[1:]]
    return [resolved or cmd[0], *cmd[1:]]


def check(name: str, cfg: dict) -> dict:
    """Vérifie un serveur. Retourne un résultat structuré (texte ET JSON)."""
    res = {"name": name, "ok": False, "server": None, "version": None,
           "tools": 0, "probe": None, "duration_s": 0.0, "detail": ""}
    t0 = time.time()
    cmd = resolve_cmd([str(c) for c in cfg["command"]])
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,  # jamais d'héritage du pipe RPC (deadlock)
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as e:
        res["detail"] = f"lancement impossible : {e}"
        res["duration_s"] = round(time.time() - t0, 1)
        return res
    reader = Reader(proc.stdout)
    try:
        init = rpc(reader, proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2024-11-05",
                                             "capabilities": {},
                                             "clientInfo": {"name": "mcp_doctor", "version": "1.0"}}},
                   HANDSHAKE_TIMEOUT)
        if init is None:
            if proc.poll() is not None:
                res["detail"] = f"process mort (exit {proc.returncode}) sans handshake"
            else:
                res["detail"] = f"pas de handshake en {HANDSHAKE_TIMEOUT:.0f}s (téléchargement ? serveur hang ?)"
            res["duration_s"] = round(time.time() - t0, 1)
            return res
        if "result" not in init:
            res["detail"] = f"handshake KO : {init.get('error', {}).get('message', '?')}"
            res["duration_s"] = round(time.time() - t0, 1)
            return res
        info = init["result"].get("serverInfo", {})
        res["server"] = info.get("name", "?")
        res["version"] = str(info.get("version", "?"))
        notify(proc, "notifications/initialized")

        tools: set[str] = set()
        if "tools" in init["result"].get("capabilities", {}):
            listing = rpc(reader, proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                          TOOLS_TIMEOUT)
            if listing and "result" in listing:
                tools = {t.get("name", "") for t in listing["result"].get("tools", [])}
        res["tools"] = len(tools)
        required = REQUIRED_TOOLS.get(name, set())
        missing = {r for r in required if not any(r == t or r in t for t in tools)}
        if missing:
            res["detail"] = f"{res['server']} v{res['version']}, {len(tools)} outils — outils manquants : {sorted(missing)}"
            res["duration_s"] = round(time.time() - t0, 1)
            return res
        # sonde réelle : appel d'un outil lecture seule (le contrat ne suffit pas)
        probe = PROBES.get(name)
        if probe and probe[0] in tools:
            pname, pargs, ptimeout = probe
            ok_p, msg_p = tool_call(reader, proc, pname, pargs, ptimeout)
            res["probe"] = {"tool": pname, "ok": ok_p, "msg": msg_p}
            res["detail"] = f"{res['server']} v{res['version']}, {len(tools)} outils | sonde: {msg_p}"
            if not ok_p:
                res["duration_s"] = round(time.time() - t0, 1)
                return res
        res["ok"] = True
        if not res["detail"]:
            res["detail"] = f"{res['server']} v{res['version']}, {len(tools)} outils"
        return res
    finally:
        res["duration_s"] = round(time.time() - t0, 1) if not res["duration_s"] else res["duration_s"]
        try:
            proc.kill()
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="mcp_doctor : handshakes + sondes réelles des MCP")
    ap.add_argument("--json", action="store_true",
                    help="sortie JSON structurée (pour intégration rapport/CI)")
    ap.add_argument("--out", help="écrire le JSON dans ce fichier (avec --json)")
    args = ap.parse_args()

    servers = {k: v for k, v in CFG.get("mcp", {}).items() if v.get("enabled", True)}
    results = [check(name, cfg) for name, cfg in sorted(servers.items())]
    failures = sum(1 for r in results if not r["ok"])
    report = {
        "tool": "mcp_doctor",
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "registry": str(ROOT / "opencode.json"),
        "servers": results,
        "ok_count": len(results) - failures,
        "fail_count": failures,
        "all_green": failures == 0,
    }
    if args.json or args.out:
        payload = json.dumps(report, ensure_ascii=False, indent=1)
        if args.out:
            Path(args.out).write_text(payload, encoding="utf-8")
            print(f"rapport: {args.out}")
        if args.json:
            print(payload)
    else:
        print(f"=== mcp_doctor : {len(servers)} serveurs du registre opencode.json ===")
        for r in results:
            mark = "OK " if r["ok"] else "FAIL"
            print(f"[{mark}] {r['name']:16s} {r['detail']}  ({r['duration_s']:.1f}s)", flush=True)
        print("=== tout vert ===" if not failures else f"=== {failures} serveur(s) en échec ===")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
