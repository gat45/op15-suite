"""Auto-verifier — runs deterministic checks (file/git/command/measurement) against claims.

No LLM involved: every check produces hard evidence that is attached to the
claim, then the verdict is computed by the existing VerificationEngine.
"""

import json
import os
import subprocess
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional

from .engine import VerificationEngine

logger = logging.getLogger(__name__)


class CheckError(Exception):
    pass


def check_file_exists(path: str) -> Dict:
    p = Path(path)
    return {"passed": p.exists(), "details": {"path": str(p)}}


def check_file_contains(path: str, needle: str) -> Dict:
    p = Path(path)
    if not p.exists():
        return {"passed": False, "details": {"path": str(p), "error": "file not found"}}
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        return {"passed": needle in text, "details": {"path": str(p), "needle": needle}}
    except OSError as e:
        return {"passed": False, "details": {"path": str(p), "error": str(e)}}


# Thresholds (kept in code — probabilities are not proof)
PASS_RATIO_VERIFIED = 0.8
PASS_RATIO_REJECTED = 0.2

# Allowlist for commands reachable through MCP (verify_auto "command" checks).
# No shell (list argv only). Overridable via JARVIX_ALLOW_CMDS (comma-separated).
DEFAULT_ALLOW_CMDS = ["git", "python", "pytest", "adb", "cmake", "ninja", "rg", "uv"]


def _allowed_exes() -> set:
    raw = os.environ.get("JARVIX_ALLOW_CMDS", ",".join(DEFAULT_ALLOW_CMDS))
    allowed = {x.strip().lower() for x in raw.split(",") if x.strip()}
    return allowed


def check_command(cmd: List[str], expect_rc: int = 0, expect_stdout: str = None,
                  timeout: int = 60, cwd: str = None) -> Dict:
    """Run an actual command — the strongest form of evidence. SANDBOXED:
    argv-list only (no shell), executable must be allowlisted, timeout capped."""
    try:
        if not cmd or not isinstance(cmd[0], str):
            return {"passed": False, "details": {"error": "cmd vide"}}
        exe = Path(cmd[0]).stem.lower()
        if exe not in _allowed_exes():
            return {"passed": False, "details": {
                "cmd": cmd, "error": f"commande non allowlistee: {cmd[0]}. "
                f"ajouter via JARVIX_ALLOW_CMDS"}}  # policy is in code/config, not in the caller
        timeout = min(timeout, 120)
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                             cwd=cwd, shell=False)
        ok_rc = out.returncode == expect_rc
        ok_stdout = expect_stdout in (out.stdout or "") if expect_stdout else True
        return {"passed": ok_rc and ok_stdout, "details": {
            "cmd": cmd, "returncode": out.returncode,
            "stdout_tail": (out.stdout or "")[-400:],
            "stderr_tail": (out.stderr or "")[-400:],
        }}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"passed": False, "details": {"cmd": cmd, "error": str(e)}}


def check_git_diff(repo: str, contains: str = None, since_ref: str = "HEAD~1") -> Dict:
    """Verify a claim about code changes by inspecting the actual diff."""
    base = ["git", "-C", repo]
    diff = check_command(base + ["diff", since_ref], timeout=15)
    if not diff["passed"]:
        # No diff vs HEAD~1 may be legitimate; check ref exists first
        exists = check_command(base + ["rev-parse", "--verify", since_ref], timeout=5)
        if not exists["passed"]:
            return {"passed": False, "details": {"error": f"ref {since_ref} introuvable", "repo": repo}}
        diff = {"passed": True, "details": {"note": "pas de changement vs ref"}}
    if contains:
        stdout = diff["details"].get("stdout_tail", "")
        # re-run to get full stdout for matching
        out = subprocess.run(base + ["diff", since_ref], capture_output=True, text=True, timeout=15)
        return {"passed": contains in (out.stdout or ""), "details": {"repo": repo, "matched": contains}}
    return diff


def check_measurement(actual: float, op: str, expected: float) -> Dict:
    """Numeric comparison: op in {gt, gte, lt, lte, eq, ne}."""
    ops = {
        "gt": lambda: actual > expected,
        "gte": lambda: actual >= expected,
        "lt": lambda: actual < expected,
        "lte": lambda: actual <= expected,
        "eq": lambda: abs(actual - expected) < 1e-9,
        "ne": lambda: abs(actual - expected) >= 1e-9,
    }
    if op not in ops:
        raise CheckError(f"op inconnu: {op}")
    return {"passed": bool(ops[op]()), "details": {"actual": actual, "op": op, "expected": expected}}


class AutoVerifier:
    """verify_auto(claim_id, checks) -> runs checks, attaches evidence, resolves."""

    def __init__(self, engine: VerificationEngine):
        self.engine = engine

    def verify_auto(self, claim_id: str, checks: List[Dict],
                    auto_resolve: bool = True) -> Dict:
        """checks: list of {"type": "file_exists"|"file_contains"|"command"|"git_diff"|"measurement",
                           "description": str, ...params}"""
        c = self.engine.db.get_memory(claim_id)
        if not c:
            return {"error": "claim not found"}

        results = []
        for chk in checks:
            ctype = chk.get("type")
            desc = chk.get("description", ctype)
            try:
                if ctype == "file_exists":
                    res = check_file_exists(chk["path"])
                elif ctype == "file_contains":
                    res = check_file_contains(chk["path"], chk["needle"])
                elif ctype == "command":
                    res = check_command(chk["cmd"], expect_rc=chk.get("expect_rc", 0),
                                        expect_stdout=chk.get("expect_stdout"),
                                        timeout=chk.get("timeout", 60),
                                        cwd=chk.get("cwd"))
                elif ctype == "git_diff":
                    res = check_git_diff(chk["repo"], contains=chk.get("contains"),
                                         since_ref=chk.get("since_ref", "HEAD~1"))
                elif ctype == "measurement":
                    res = check_measurement(float(chk["actual"]), chk["op"], float(chk["expected"]))
                else:
                    res = {"passed": False, "details": {"error": f"type inconnu: {ctype}"}}
            except (KeyError, CheckError, ValueError) as e:
                res = {"passed": False, "details": {"error": str(e)}}
            self.engine.add_evidence(claim_id, ctype, desc, res["passed"], details=res["details"])
            results.append({**res, "type": ctype, "description": desc})

        summary = {
            "claim_id": claim_id,
            "checks": results,
            "passed": sum(1 for r in results if r["passed"]),
            "failed": sum(1 for r in results if not r["passed"]),
        }
        if auto_resolve:
            verdict = self.engine.resolve(claim_id)
            summary["verdict"] = verdict["verdict"]
        return summary
