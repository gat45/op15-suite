"""Test client MCP stdio pour tools/upia_mcp_server.py.

Usage:
    py -3.12 tools/test_upia_mcp.py status events graph unknown
    py -3.12 tools/test_upia_mcp.py ask "question" update research

Spawns the real server (same interpreter as opencode.json registration),
performs initialize/tools-list, then calls each tool given on the command
line, printing a compact result (first 500 chars + duration + status).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

PY = r"C:\Users\videl\AppData\Local\Programs\Python\Python312\python.exe"
import os
import sys
from pathlib import Path

# serveur local au repo d'abord, fallback production D:\oneplus\tools
_LOCAL = Path(__file__).resolve().parent / "upia_mcp_server.py"
_PROD = r"D:\oneplus\tools\upia_mcp_server.py"
SERVER = str(_LOCAL if _LOCAL.exists() else _PROD)
PER_TOOL_TIMEOUT = {
    "upia_status": 60, "upia_events": 90, "upia_graph": 90,
    "upia_unknown": 90, "upia_ask": 240, "upia_update": 300,
    "upia_research": 120,
}

HARNESS = r"E:\oneplus\geniex_harness"


class McpClient:
    def __init__(self) -> None:
        self._err = open(r"D:\oneplus\tools\upia_srv_stderr.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [PY, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._err, text=True, encoding="utf-8",
        )
        self._id = 0

    def _send(self, obj: dict) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def _recv(self, want_id: int, timeout: float) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("server closed stdout")
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and msg.get("id") == want_id:
                return msg
        raise TimeoutError(f"no response for id={want_id} in {timeout}s")

    def request(self, method: str, params: dict, timeout: float = 30) -> dict:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method,
                    "params": params})
        return self._recv(self._id, timeout)

    def call_tool(self, name: str, arguments: dict, timeout: float) -> tuple[str, bool]:
        t0 = time.time()
        resp = self.request("tools/call",
                            {"name": name, "arguments": arguments}, timeout)
        dur = time.time() - t0
        result = resp.get("result", {})
        texts = [c.get("text", "") for c in result.get("content", [])
                 if isinstance(c, dict)]
        return f"[{dur:.1f}s] " + "\n".join(texts)[:500], result.get("isError", False)

    def close(self) -> None:
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        self.proc.terminate()


def main() -> int:
    tools = sys.argv[1:]
    if tools == ["smoke"]:
        # Test de non-régression : 4 outils rapides, sans dépendance LLM (~2-5 s).
        # Boucle standard (AGENTS.md, Commandes rapides) : py -3.12 tools/test_upia_mcp.py smoke
        tools = ["status", "events", "graph", "unknown"]
    if not tools:
        print("usage: test_upia_mcp.py <tool> [tool ...]  (args: ask takes next argv as question)")
        return 2

    c = McpClient()
    try:
        init = c.request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "0.1"},
        })
        name = init.get("result", {}).get("serverInfo", {}).get("name", "?")
        print(f"== serveur OK: {name}")
        c._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        lst = c.request("tools/list", {})
        listed = [t["name"] for t in lst.get("result", {}).get("tools", [])]
        print(f"== tools/list: {len(listed)} -> {sorted(listed)}")

        exit_code = 0
        pending = list(tools)
        while pending:
            raw = pending.pop(0)
            if raw == "ask":
                q = pending.pop(0) if pending else "état du projet en une phrase"
                name_t, args = "upia_ask", {"question": q}
            elif raw == "research":
                q = pending.pop(0) if pending else "Snapdragon 8 Elite Gen 5 NPU"
                name_t, args = "upia_research", {"query": q}
            elif raw == "events":
                name_t, args = "upia_events", {"since": "2026-09-19"}
            elif raw == "updatefull":
                name_t, args = "upia_update", {}  # commits=0 → défaut = mise à jour complète
            elif raw == "update":
                name_t, args = "upia_update", {"commits": 5}
            else:
                name_t, args = f"upia_{raw}", {}
            timeout = PER_TOOL_TIMEOUT[name_t]
            print(f"\n== {name_t} {json.dumps(args, ensure_ascii=False)[:120]} (timeout {timeout}s)")
            try:
                text, is_err = c.call_tool(name_t, args, timeout)
                print(("ERREUR " if is_err else "OK     ") + text.replace("\n", " | ")[:500])
                if is_err:
                    exit_code = 1
            except Exception as e:
                print(f"FAIL   {type(e).__name__}: {e}")
                exit_code = 1
        return exit_code
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main())
