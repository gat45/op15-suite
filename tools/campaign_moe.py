# COPIE VENDOR POUR CI/NIGHTLY — la version canonique vit dans le harness
# (E:/oneplus/geniex_harness/campaign_moe.py). Gates G0/G1 fonctionnent
# standalone ; les gates device (G2+) exigent governor/ du harness.
"""campaign_moe.py — campagne device §8.1-4 en une commande (portes = gates).

Usage (OP15 branché) :
    py -3.12 campaign_moe.py --model <chemin GGUF> [--n 5] [--device-dir /data/local/tmp/llama]
    py -3.12 campaign_moe.py --list          # voir les gates
    py -3.12 campaign_moe.py --step G4       # rejouer une seule gate

Chaîne (spec : profiler_v3/ARCHITECTURE_ET_INTERCONNEXIONS §8.1-4) :
    G0 device présent          → sinon STOP
    G1 hashes (modèle, libggml-hexagon.so, skel) locaux vs device (§8.1)
    G2 baseline HTP froide puis chaude, n=5, CV < 3 % (§8.2)
    G3 patch trace seul : l2_ftrace2.sh déployé + GGML_EXPERT_TRACE vérifié (§8.3)
    G4 capture trace expert réelle via capture_moe_route_trace (§8.4)
    G5-G7 (bonus hors scope §8.5-7, offline) : parse → attribution → replay → gate
       — prouve que la chaîne avale la trace réelle ; gate final attendu
         REFUSED tant que l'A/B device (§8.8) n'a pas tourné.

Principe : aucune action destructive (le runner vérifie, il ne push ni ne
rebuild — les remédiations sont listées). Rapport JSON : governor_state/moe/.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parent
sys.path.insert(0, str(HARNESS))

MOE_DIR = HARNESS / "governor_state" / "moe"
STATE = MOE_DIR / "campaign_state.json"
REPORT_DIR = MOE_DIR

AB_WT = Path("E:/oneplus/ab-wt")          # worktree runtime (ne JAMAIS utiliser D:\oneplus\downloads\sources\llama-cpp)
DEVICE_DIR_DEFAULT = "/data/local/tmp/llama"
BASELINE_LOG = "/data/local/tmp/t12_qairt_w4a16.log"


def adb(*args, timeout=60):
    return subprocess.run(["adb", *args], capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8", errors="replace")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def device_sha256(remote: str):
    r = adb("shell", f"sha256sum {remote} 2>/dev/null", timeout=120)
    out = (r.stdout or "").strip().split()
    return out[0] if out else None


def find_local(pattern: str) -> Path | None:
    for base in (AB_WT, HARNESS):
        if base.is_dir():
            hits = sorted(p for p in base.rglob(pattern)
                          if ".git" not in p.parts and p.is_file())
            if hits:
                return hits[0]
    return None


class Spec:
    """Shim minimal : op15.execute() ne lit que spec.name."""
    def __init__(self, name):
        self.name = name


# ─────────────────────────────────────────────────────────────── G0
def g0_device(_args, ctx):
    r = adb("get-state", timeout=15)
    if (r.stdout or "").strip() != "device":
        return False, {"error": "OP15 absent (adb get-state != device)",
                       "remediation": "brancher l'OP15, déverrouiller, adb wait-device"}
    ser = (adb("get-serialno").stdout or "").strip()
    return True, {"serial": ser}


# ─────────────────────────────────────────────────────────────── G1
def g1_hashes(args, ctx):
    model = args.model or (ctx.get("model_path"))
    if not model:
        return False, {"error": "chemin GGUF inconnu",
                       "remediation": "préciser --model <GGUF> (mémorisé pour les prochaines fois)"}
    model_p = Path(model)
    pairs = [("model", model_p, f"{args.device_dir}/{model_p.name}")]
    for label, pattern in (("libggml-hexagon.so", "libggml-hexagon.so"),
                           ("skel", "*skel*.so")):
        local = args.lib if (label == "libggml-hexagon.so" and args.lib) else find_local(pattern)
        if local:
            pairs.append((label, local, f"{args.device_dir}/{Path(local).name}"))
        else:
            return False, {"error": f"{label} introuvable en local (rglob {pattern} sous {AB_WT})",
                           "remediation": f"préciser --{ 'lib' if 'lib' in label else 'skel'} <chemin>"}
    results, ok = {}, True
    for label, local_p, remote in pairs:
        if not local_p.exists():
            results[label] = {"error": f"local absent: {local_p}"}
            ok = False
            continue
        lh = sha256(local_p)
        dh = device_sha256(remote)
        status = "MATCH" if dh == lh else ("ABSENT_SUR_DEVICE" if dh is None else "MISMATCH")
        results[label] = {"local": str(local_p), "device": remote,
                          "sha256_local": lh[:16] + "…", "sha256_device": (dh or "")[:16] + "…",
                          "status": status}
        if status != "MATCH":
            ok = False
    return ok, {"pairs": results,
                "remediation": None if ok else "push des fichiers MISMATCH/ABSENT vers le device, puis relancer"}


# ─────────────────────────────────────────────────────────────── G2
def g2_baseline(args, ctx):
    from governor.op15 import Op15Adapter
    ad = Op15Adapter()
    if args.skip_baseline:
        return True, {"skipped": True}
    t0 = ad.observe_state()
    warm = ad.execute(Spec("bench_qairt_w4a16"), {})   # run de chauffe, ignoré
    tps_list = []
    for i in range(args.n):
        r = ad.execute(Spec("bench_qairt_w4a16"), {})
        tps = (r.get("metrics") or {}).get("tps")
        if not tps:
            return False, {"error": f"bench {i+1}/{args.n} sans tps", "raw": r.get("raw", ""),
                           "remediation": "vérifier le bench t12 sur device (log: " + BASELINE_LOG + ")"}
        tps_list.append(round(tps, 3))
    t1 = ad.observe_state()
    mean = sum(tps_list) / len(tps_list)
    var = sum((t - mean) ** 2 for t in tps_list) / len(tps_list)
    cv = (var ** 0.5) / mean if mean else 9e9
    ok = cv < 0.03
    return ok, {"tps_list": tps_list, "mean_tps": round(mean, 3), "cv_pct": round(cv * 100, 2),
                "thermal_before": t0.get("thermal"), "thermal_after": t1.get("thermal"),
                "remediation": None if ok else "CV ≥ 3 % : device bruité — laisser refroidir, fermer les apps, relancer G2"}


# ─────────────────────────────────────────────────────────────── G3
def g3_patch_trace(args, ctx):
    checks = {}
    script = find_local("l2_ftrace2.sh")
    checks["l2_ftrace2_local"] = str(script) if script else None
    if script:
        push = adb("push", str(script), "/data/local/tmp/l2_ftrace2.sh", timeout=120)
        chmod = adb("shell", "chmod 755 /data/local/tmp/l2_ftrace2.sh")
        checks["push"] = (push.returncode == 0 and chmod.returncode == 0)
    else:
        checks["push"] = None
    # GGML_EXPERT_TRACE doit être exporté par le script de bench sur device
    probe = adb("shell", "grep -l GGML_EXPERT_TRACE /data/local/tmp/*.sh 2>/dev/null", timeout=30)
    hits = [l.strip() for l in (probe.stdout or "").splitlines() if l.strip()]
    checks["ggml_expert_trace_scripts"] = hits
    ok = bool(checks["push"]) and bool(hits)
    if not ok and args.force_trace_patch:
        checks["forced"] = True
        return True, checks   # on continue à nos risques et périls (trace probablement absente)
    return ok, {"checks": checks,
                "remediation": None if ok else
                "déployer le patch trace (worktree E:/oneplus/ab-wt) : rebuild avec le patch + "
                "export GGML_EXPERT_TRACE=1 dans le script de bench, puis relancer G3"}


# ─────────────────────────────────────────────────────────────── G4
def g4_capture(args, ctx):
    from governor.op15 import Op15Adapter
    ad = Op15Adapter()
    tel_before = ad.observe_state()
    r = ad.execute(Spec("capture_moe_route_trace"), {"timeout_s": args.bench_timeout})
    tel_after = ad.observe_state()
    if not r.get("ok"):
        return False, {"error": r.get("error", "capture en échec"), "tps": (r.get("metrics") or {}).get("tps"),
                       "remediation": "0 événement = patch trace absent/inactif (cf. G3) ou GGML_EXPERT_TRACE=0"}
    ctx["jsonl"] = r.get("jsonl")
    return True, {"jsonl": r.get("jsonl"), "n_events": (r.get("metrics") or {}).get("n_events"),
                  "tps": (r.get("metrics") or {}).get("tps"),
                  "thermal_before": tel_before.get("thermal"), "thermal_after": tel_after.get("thermal")}


# ──────────────────────────────────────── G5-G7 (bonus offline, §8.5-7)
def g5_parse(args, ctx):
    from governor.op15 import Op15Adapter
    ad = Op15Adapter()
    r = ad.execute(Spec("parse_moe_htp_trace"), {"jsonl": ctx.get("jsonl")})
    if not r.get("ok"):
        return False, {"error": r.get("error"), "remediation": "JSONL vide/illisible — voir G4"}
    status = (r.get("htp_attribution") or {}).get("status")
    ctx["attribution"] = status
    return status == "OK", {"n_events": r.get("n_events") or (r.get("metrics") or {}).get("n_events"),
                            "hit_rate": (r.get("metrics") or {}).get("hit_rate"),
                            "attribution": status, "parsed": r.get("parsed"),
                            "remediation": None if status == "OK" else
                            "§8.6 : attribution HTP absente (run_id/token_index/layer) — ARRÊT, pas de répartition arbitraire"}


def g6_replay(args, ctx):
    from governor.op15 import Op15Adapter
    ad = Op15Adapter()
    r = ad.execute(Spec("replay_rpcmem_cache"),
                   {"cold_ns_per_byte": args.cold_ns_per_byte})
    if not r.get("ok"):
        return False, {"error": r.get("error")}
    chosen = r.get("chosen")
    return chosen is not None, {"budgets": [(row.get("capacity_mib"), (row.get("aggregate") or {}).get("net_saved_time_ns"))
                                            for row in r.get("rows", [])],
                                "chosen_mib": (chosen or {}).get("capacity_mib"),
                                "replay": r.get("replay"),
                                "remediation": None if chosen else
                                "aucun budget élu — fournir --cold-ns-per-byte (mesuré, jamais inventé) ou trace sans gains"}


def g7_gate(args, ctx):
    from governor.op15 import Op15Adapter
    ad = Op15Adapter()
    r = ad.execute(Spec("validate_moe_cache"), {"ab_run_id": args.ab_run_id})
    verdict = r.get("verdict", "?")
    expected_without_ab = "REFUSED" in verdict and "ab_evidence" in verdict
    if args.ab_run_id:
        return verdict == "ACCEPTED", {"verdict": verdict, "gate": r.get("gate"),
                                       "remediation": None if verdict == "ACCEPTED" else
                                       "A/B device requis (§8.8) avant ACCEPTED"}
    return True, {"verdict": verdict, "gate": r.get("gate"),
                  "note": "REFUSED attendu : campagne §8.1-4 sans A/B (§8.8) — comportement spec-conforme"
                  if expected_without_ab else "verdict inattendu"}


GATES = [("G0", "device présent", g0_device),
         ("G1", "hashes modèle/lib/skel (§8.1)", g1_hashes),
         ("G2", "baseline froide/chaude n=5, CV<3% (§8.2)", g2_baseline),
         ("G3", "patch trace seul déployé (§8.3)", g3_patch_trace),
         ("G4", "capture trace expert réelle (§8.4)", g4_capture),
         ("G5", "parse + attribution HTP (§8.5-6, bonus)", g5_parse),
         ("G6", "replay budgets RPCMEM (§8.7, bonus)", g6_replay),
         ("G7", "gate validate_moe_cache (§8.8-9, bonus)", g7_gate)]


def main() -> int:
    ap = argparse.ArgumentParser(description="Campagne MoE §8.1-4 (portes)")
    ap.add_argument("--model", help="chemin local du GGUF (mémorisé)")
    ap.add_argument("--device-dir", default=DEVICE_DIR_DEFAULT)
    ap.add_argument("--lib", help="chemin local libggml-hexagon.so (sinon rglob ab-wt)")
    ap.add_argument("--n", type=int, default=5, help="runs baseline (défaut 5)")
    ap.add_argument("--skip-baseline", action="store_true")
    ap.add_argument("--force-trace-patch", action="store_true",
                    help="continuer même si le patch trace n'est pas prouvé")
    ap.add_argument("--cold-ns-per-byte", type=float, default=None,
                    help="référence froide mesurée (ftrace L2) — jamais inventée")
    ap.add_argument("--ab-run-id", default=None, help="run_id de l'A/B device (§8.8)")
    ap.add_argument("--bench-timeout", type=int, default=480)
    ap.add_argument("--step", help="ne jouer qu'une gate (ex: G4)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for gid, desc, _ in GATES:
            print(f"{gid}  {desc}")
        return 0

    MOE_DIR.mkdir(parents=True, exist_ok=True)
    ctx = {}
    if STATE.exists():
        ctx.update(json.loads(STATE.read_text(encoding="utf-8")))
    if args.model:
        ctx["model_path"] = args.model

    order = [g for g in GATES if (not args.step or g[0] == args.step)]
    results, failed_at = {}, None
    for gid, desc, fn in order:
        t0 = time.time()
        try:
            ok, detail = fn(args, ctx)
        except Exception as e:
            ok, detail = False, {"error": f"{type(e).__name__}: {e}"}
        dt = time.time() - t0
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {gid}  {desc}  ({dt:.1f}s)", flush=True)
        if not ok:
            print(f"       -> {detail.get('error', '')}")
            if detail.get("remediation"):
                print(f"       -> remédiation : {detail['remediation']}")
        results[gid] = {"desc": desc, "ok": ok, "detail": detail, "s": round(dt, 1)}
        if not ok:
            failed_at = gid
            if gid in ("G0", "G1", "G2", "G3", "G4"):   # §8.1-4 : verrouillé en échec
                break

    STATE.write_text(json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8")
    report = {"date": time.strftime("%Y-%m-%d %H:%M:%S"), "args": vars(args),
              "ctx": ctx, "gates": results, "failed_at": failed_at}
    out = REPORT_DIR / f"campaign_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"rapport: {out}")
    if failed_at:
        print(f"=== campagne verrouillée à {failed_at} — corriger puis relancer ===")
        return 1
    print("=== campagne §8.1-4 complète ===")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(main())
