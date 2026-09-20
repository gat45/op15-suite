"""JARVIX Memory UI v2 — dashboard, search, chat, filesystem, llama.cpp manager, device, layers, admin."""

import json
import sys
import threading
import time
import subprocess
import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

PKG_ROOT = Path(__file__).resolve().parents[3]  # memoire/
ROOT = PKG_ROOT.parent  # oneplus/
sys.path.insert(0, str(ROOT / "memoire" / "src"))
sys.path.insert(0, str(PKG_ROOT))

from jarvix_memory.router import MemoryRouter
from jarvix_memory.core.migration import get_version
from jarvix_memory.llm.reasoner import LLMReasoner
from jarvix_memory.core.models import Memory

app = Flask(__name__, template_folder="templates")
CORS(app)

# ── Config ─────────────────────────────────────────────────────
CONFIG_PATH = PKG_ROOT / "config.json"
DEFAULT_CONFIG = {
    "llama_exe": "",
    "gguf_dirs": [],
    "llama_port": 8080,
    "llama_ctx": 8192,
    "llama_ngl": 99,
    "bilan_default": "full",
}
if CONFIG_PATH.exists():
    try:
        _cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        DEFAULT_CONFIG.update({k: v for k, v in _cfg.items()})
    except Exception as e:
        app.logger.warning("config.json invalid: %s", e)
CONFIG = DEFAULT_CONFIG


def save_config():
    CONFIG_PATH.write_text(json.dumps(CONFIG, indent=2), encoding="utf-8")


# ── Components ─────────────────────────────────────────────────
DB_PATH = PKG_ROOT / "jarvix_memory.db"
router = MemoryRouter(db_path=str(DB_PATH))
vector_store = router.db.vector
if vector_store is not None:
    vector_store.warm()  # preload model in background
# Scheduled consolidation: every 6h
router.consolidation.start_scheduler(interval_hours=6.0)
llm = LLMReasoner(router.db, vector_store=vector_store,
                  base_url=f"http://127.0.0.1:{CONFIG['llama_port']}")

REPORTS_DIR = PKG_ROOT / "reports"
LLAMA_LOG = REPORTS_DIR / "llama_ui.log"

# bilan.py helpers (format_size, check_device, check_llama_health)
import importlib.util
_spec = importlib.util.spec_from_file_location("bilan", PKG_ROOT / "bilan.py")
bilan_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bilan_mod)

LLAMA_STATUS_LOCK = threading.Lock()
MODELS_CACHE = {"models": None, "ts": 0}


def set_cfg(**kw):
    CONFIG.update(kw)
    save_config()
    llm.base_url = f"http://127.0.0.1:{CONFIG['llama_port']}"


# ══ CORE (existing) ═════════════════════════════════════════════

@app.route("/")
def index():
    stats = router.stats()
    vec_stats = vector_store.stats() if vector_store else {"embeddings": 0, "model": "n/a", "dimensions": 384}
    llm_health = llm.health()
    db_version = get_version(router.db._connect())
    return render_template("index.html", stats=stats, vec_stats=vec_stats,
                           llm_health=llm_health, db_version=db_version, config=CONFIG)


@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.json or {}
    q, mode, limit = data.get("query", ""), data.get("mode", "hybrid"), data.get("limit", 10)
    if mode == "vector" and vector_store:
        results = vector_store.search(q, limit=limit)
    elif mode == "text":
        results = router.db.search_fts(q, limit=limit)
    elif mode == "semantic_like":
        results = router.db.search_fts(q, limit=limit)
    else:
        results = router.db.search_hybrid(q, limit=limit)
    # Filter internal 'hypothesis' noise by default
    return jsonify({"results": results, "count": len(results)})


@app.route("/api/reason", methods=["POST"])
def api_reason():
    d = request.json or {}
    if not d.get("query"):
        return jsonify({"error": "query required"}), 400
    return jsonify(llm.reason(d["query"]))


# ══ MEMORIES: browse / detail / edit ═══════════════════════════

@app.route("/api/memories", methods=["GET"])
def api_memories():
    t = request.args.get("type")
    limit = int(request.args.get("limit", 50))
    res = router.db.search_by_type(t, limit=limit) if t else router.db.list_all(limit=limit)
    return jsonify({"memories": res, "count": len(res)})


@app.route("/api/memories", methods=["POST"])
def api_add_memory():
    d = request.json or {}
    content = d.get("content", "")
    if not content:
        return jsonify({"error": "content required"}), 400
    m = Memory(type=d.get("type", "semantic"), content=content,
               confidence=float(d.get("confidence", 1.0)), source=d.get("source"))
    router.db.insert_memory(m)
    return jsonify({"id": m.id, "type": m.type, "status": "created"})


@app.route("/api/memories/<mid>", methods=["GET"])
def api_get_memory(mid):
    m = router.db.get_memory(mid)
    return (jsonify(m), 200) if m else (jsonify({"error": "not found"}), 404)


@app.route("/api/memories/<mid>", methods=["PUT"])
def api_update_memory(mid):
    d = request.json or {}
    allowed = ("content", "type", "status", "confidence", "importance", "metadata")
    fields = {k: v for k, v in d.items() if k in allowed}
    if not fields:
        return jsonify({"error": "nothing to update"}), 400
    ok = router.db.update_memory(mid, **fields)
    # re-embed if content changed
    if ok and "content" in fields and vector_store:
        try:
            vector_store.embed_and_store(mid, fields["content"])
        except Exception as e:
            app.logger.warning("re-embed failed: %s", e)
    return jsonify({"updated": bool(ok)})


@app.route("/api/memories/<mid>", methods=["DELETE"])
def api_delete_memory(mid):
    ok = router.db.delete_memory(mid)
    return jsonify({"deleted": bool(ok)})


@app.route("/api/layers")
def api_layers():
    return jsonify(router.stats())


# ══ ACTIONS / CLAIMS / STRATEGIES / RECOVERY / WORLD / GRAPH ═══

@app.route("/api/actions/pending")
def api_actions_pending():
    return jsonify({"actions": router.action.pending()})


@app.route("/api/actions/history")
def api_actions_history():
    return jsonify({"actions": router.action.history(int(request.args.get("limit", 20)))})


@app.route("/api/actions/<aid>/approve", methods=["POST"])
def api_action_approve(aid):
    ok = router.action.approve(aid)
    return jsonify({"approved": bool(ok)})


@app.route("/api/actions/<aid>/execute", methods=["POST"])
def api_action_execute(aid):
    d = request.json or {}
    ok = router.action.execute(aid, result=d.get("result"), success=bool(d.get("success", True)))
    return jsonify({"executed": bool(ok)})


@app.route("/api/actions", methods=["POST"])
def api_action_propose():
    d = request.json or {}
    m = router.action.propose(d.get("description", ""), priority=int(d.get("priority", 5)))
    return jsonify({"id": m.id, "status": "proposed"})


@app.route("/api/claims")
def api_claims():
    v = request.args.get("verdict")
    return jsonify({"claims": router.verification.get_claims(verdict=v, limit=int(request.args.get("limit", 30)))})


@app.route("/api/claims/<cid>/resolve", methods=["POST"])
def api_claim_resolve(cid):
    return jsonify(router.verification.resolve(cid))


@app.route("/api/strategies")
def api_strategies():
    return jsonify({"strategies": router.strategy.leaderboard(int(request.args.get("limit", 10)))})


@app.route("/api/strategies/<sid>/attempt", methods=["POST"])
def api_strategy_attempt(sid):
    d = request.json or {}
    ok = router.strategy.record_attempt(sid, success=bool(d.get("success", True)),
                                        cost_minutes=float(d.get("cost_minutes", 0)))
    return jsonify({"recorded": bool(ok)})


@app.route("/api/recovery/active")
def api_recovery_active():
    return jsonify({"recoveries": router.recovery.active_recoveries()})


@app.route("/api/world/beliefs")
def api_world_beliefs():
    return jsonify({"beliefs": router.world.get_beliefs()})


@app.route("/api/world/predictions")
def api_world_predictions():
    return jsonify({"predictions": router.world.get_predictions(
        status=request.args.get("status", "pending"), limit=int(request.args.get("limit", 20)))})


@app.route("/api/graph")
def api_graph():
    items = router.db.search_by_type("graph", limit=int(request.args.get("limit", 200)))
    edges = []
    for it in items:
        meta = json.loads(it.get("metadata", "{}")) if isinstance(it.get("metadata"), str) else {}
        subj, pred, obj = meta.get("subject"), meta.get("predicate"), meta.get("object")
        if not (subj and pred and obj):
            content = it.get("content", "") or ""
            if "--" in content and "-->" in content:
                try:
                    left, obj = content.split("-->", 1)
                    subj, pred = left.split("--", 1)
                except ValueError:
                    continue
            else:
                continue
        edges.append({"from": subj.strip(), "predicate": pred.strip(), "to": obj.strip(), "id": it.get("id")})
    return jsonify({"edges": edges, "count": len(edges)})


@app.route("/api/graph", methods=["POST"])
def api_graph_add():
    d = request.json or {}
    m = router.graph.add_relation(d.get("subject", ""), d.get("predicate", ""), d.get("object", ""))
    return jsonify({"id": m.id})


# ══ PROACTIVE RULES / CONSOLIDATION ════════════════════════════

@app.route("/api/rules")
def api_rules():
    return jsonify({"rules": router.proactive.list_rules()})


@app.route("/api/rules", methods=["POST"])
def api_rules_add():
    d = request.json or {}
    rule = router.proactive.add_rule(
        name=d.get("name", "rule"), trigger_condition=d.get("trigger", ""),
        memory_type=d.get("memory_type"), max_age_hours=int(d.get("max_age_hours", 24)),
        min_importance=float(d.get("min_importance", 0.5)), priority=int(d.get("priority", 5)))
    return jsonify({"id": rule["id"]})


@app.route("/api/rules/<rid>", methods=["DELETE"])
def api_rules_del(rid):
    router.proactive.remove_rule(rid)
    return jsonify({"removed": True})


@app.route("/api/consolidation", methods=["POST"])
def api_consolidation():
    router.consolidation.run_sleep_cycle()
    return jsonify(router.consolidation.stats())


@app.route("/api/consolidation/stats")
def api_consolidation_stats():
    return jsonify(router.consolidation.stats())


# ══ FILESYSTEM ═════════════════════════════════════════════════

@app.route("/api/fs/list")
def api_fs_list():
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path required"}), 400
    p = Path(path)
    try:
        if not p.exists():
            return jsonify({"error": "path not found"}), 404
        if p.is_file():
            p = p.parent
        items = []
        for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if e.name.startswith((".", "$")):
                continue
            try:
                st = e.stat()
                items.append({
                    "name": e.name, "path": str(e), "is_dir": e.is_dir(),
                    "size": st.st_size if e.is_file() else None,
                    "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                })
            except (OSError, PermissionError):
                continue
        return jsonify({"path": str(p), "parent": str(p.parent), "items": items, "count": len(items)})
    except (OSError, PermissionError) as e:
        return jsonify({"error": str(e)}), 403


@app.route("/api/fs/view")
def api_fs_view():
    path = request.args.get("path", "")
    limit = int(request.args.get("limit", 200))
    p = Path(path)
    try:
        if not p.exists() or not p.is_file():
            return jsonify({"error": "file not found"}), 404
        size = p.stat().st_size
        text = p.read_text(encoding="utf-8", errors="replace")[:5000]
        lines = text.splitlines()[:limit]
        return jsonify({"path": str(p), "size": size, "lines": lines,
                        "is_binary": "\x00" in text})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/fs/important")
def api_fs_important():
    """Key project file locations."""
    candidates = []
    def add(label, path, note=""):
        f = Path(path)
        candidates.append({"label": label, "path": str(path),
                           "exists": f.exists(),
                           "is_dir": f.is_dir(),
                           "size": f.stat().st_size if (f.exists() and f.is_file()) else None,
                           "note": note})
    add("Base memoire DB", DB_PATH, "SQLite/memory")
    add("llama-server.exe", CONFIG["llama_exe"], "llama.cpp")
    add("config.json", CONFIG_PATH, "config UI")
    add("reports/", REPORTS_DIR, "rapports")
    bilans = sorted(REPORTS_DIR.glob("bilan_*.md"))
    if bilans:
        add("Dernier bilan", bilans[-1])
    add("oneplus root", ROOT, "racine projet")
    # top 3 GGUF of first scan
    if MODELS_CACHE["models"] is None:
        MODELS_CACHE["models"] = scan_gguf_dirs(CONFIG)
        MODELS_CACHE["ts"] = time.time()
    for gg in MODELS_CACHE["models"][:5]:
        add("GGUF", gg["path"], gg["size_h"])
    return jsonify({"locations": candidates})


# ══ LLAMA.CPP MANAGER ══════════════════════════════════════════

def scan_gguf_dirs(config_obj):
    models = []
    seen = set()
    for gd in config_obj["gguf_dirs"]:
        gd_path = Path(gd)
        if not gd_path.exists():
            continue
        for gg in gd_path.rglob("*.gguf"):
            if gg in seen:
                continue
            seen.add(gg)
            try:
                st = gg.stat()
                models.append({"path": str(gg), "name": gg.name,
                               "dir": str(gg.parent),
                               "size": st.st_size,
                               "size_h": bilan_mod.format_size(st.st_size),
                               "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))})
            except OSError:
                continue
    return sorted(models, key=lambda m: m["name"].lower())


@app.route("/api/llama/models")
def api_llama_models():
    now = time.time()
    if MODELS_CACHE["models"] is None or now - MODELS_CACHE["ts"] > 120:
        MODELS_CACHE["models"] = scan_gguf_dirs(CONFIG)
        MODELS_CACHE["ts"] = now
    return jsonify({"models": MODELS_CACHE["models"], "count": len(MODELS_CACHE["models"])})


@app.route("/api/llama/scan", methods=["POST"])
def api_llama_scan():
    MODELS_CACHE["models"] = scan_gguf_dirs(CONFIG)
    MODELS_CACHE["ts"] = time.time()
    return jsonify({"models": MODELS_CACHE["models"], "count": len(MODELS_CACHE["models"])})


@app.route("/api/llama/status")
def api_llama_status():
    with LLAMA_STATUS_LOCK:
        status = bilan_mod.check_llama_health()
        status["port"] = CONFIG["llama_port"]
    # process info
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV"],
                             capture_output=True, text=True, timeout=5)
        procs = [l for l in out.stdout.splitlines()[3:] if "llama-server" in l]
        status["processes"] = len(procs)
        if procs:
            status["pid"] = procs[0].split(",")[1]
    except Exception:
        status["processes"] = None
    return jsonify(status)


@app.route("/api/llama/start", methods=["POST"])
def api_llama_start():
    d = request.json or {}
    model = d.get("model") or d.get("model_path")
    if not model:
        return jsonify({"error": "model required"}), 400
    if not Path(CONFIG["llama_exe"]).exists():
        return jsonify({"error": f"llama-server.exe introuvable : {CONFIG['llama_exe']}"}), 400
    if not Path(model).exists():
        return jsonify({"error": "model introuvable"}), 400

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    port = int(d.get("port", CONFIG["llama_port"]))
    ctx = int(d.get("ctx", CONFIG["llama_ctx"]))
    ngl = int(d.get("ngl", CONFIG["llama_ngl"]))
    cmd = [
        CONFIG["llama_exe"],
        "-m", model,
        "--host", "127.0.0.1",
        "--port", str(port),
        "--ctx-size", str(ctx),
        "-ngl", str(ngl),
    ]
    extra = (d.get("extra_args") or "").strip()
    if extra:
        cmd.extend(extra.split())
    log_handle = open(LLAMA_LOG, "w", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT,
                                cwd=str(Path(CONFIG["llama_exe"]).parent))
    except Exception as e:
        log_handle.close()
        return jsonify({"error": str(e)}), 500
    set_cfg(llama_port=port, llama_ctx=ctx, llama_ngl=ngl)
    # wait up to 8s for health
    for _ in range(16):
        time.sleep(0.5)
        h = bilan_mod.check_llama_health()
        if h["running"]:
            return jsonify({"started": True, "pid": proc.pid, "model": model,
                            "port": port, "loaded": h.get("model")})
    return jsonify({"started": True, "pid": proc.pid, "model": model, "port": port,
                    "note": "serveur lance mais pas encore up (voir log)"})


@app.route("/api/llama/stop", methods=["POST"])
def api_llama_stop():
    try:
        out = subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                             capture_output=True, text=True, timeout=8)
        success = out.returncode == 0
        return jsonify({"stopped": success, "output": out.stdout.strip() or out.stderr.strip()})
    except Exception as e:
        return jsonify({"stopped": False, "error": str(e)}), 500


@app.route("/api/llama/log")
def api_llama_log():
    if not LLAMA_LOG.exists():
        return jsonify({"log": "", "tail": [], "nbytes": 0})
    data = LLAMA_LOG.read_text(encoding="utf-8", errors="replace")
    limit = int(request.args.get("tail", 100))
    lines = data.splitlines()
    return jsonify({"nbytes": len(data), "tail": lines[-limit:]})


# ══ DEVICE / BILAN ═════════════════════════════════════════════

@app.route("/api/device")
def api_device():
    return jsonify(bilan_mod.check_device())


@app.route("/api/bilan", methods=["POST"])
def api_bilan():
    d = request.json or {}
    report = bilan_mod.generate_report(save=bool(d.get("save", False)),
                                       as_json=False,
                                       short=bool(d.get("short", False)),
                                       analyze=bool(d.get("analyze", False)))
    return jsonify({"report": report})


# ══ LAB: verify_auto / hypotheses / env / perception / JEV / quant ══

@app.route("/api/lab/verify-auto", methods=["POST"])
def api_lab_verify_auto():
    d = request.json or {}
    checks = d.get("checks", [])
    claim = router.verification.claim(d.get("claim", ""), source="ui")
    result = router.auto_verify.verify_auto(claim.id, checks, auto_resolve=True)
    result["claim_id"] = claim.id
    return jsonify(result)


@app.route("/api/lab/hyp/propose", methods=["POST"])
def api_lab_hyp_propose():
    d = request.json or {}
    m = router.experiment.propose_hypothesis(d.get("statement", ""),
                                             env_id=d.get("env_id"),
                                             rationale=d.get("rationale"))
    return jsonify(m)


@app.route("/api/lab/hyp/run", methods=["POST"])
def api_lab_hyp_run():
    d = request.json or {}
    result = router.experiment.run_experiment(
        d["hyp_id"], d.get("name", "exp"), d.get("result", ""),
        success=bool(d.get("success", False)), env_id=d.get("env_id"))
    return jsonify(result)


@app.route("/api/lab/hyp/conclude", methods=["POST"])
def api_lab_hyp_conclude():
    d = request.json or {}
    return jsonify(router.experiment.conclude(d["hyp_id"], d.get("verdict", "refuted")))


@app.route("/api/lab/hyp/guard")
def api_lab_hyp_guard():
    return jsonify(router.experiment.repeat_guard(request.args.get("q", "")))


@app.route("/api/lab/hyp/pending")
def api_lab_hyp_pending():
    return jsonify({"hypotheses": router.experiment.pending_hypotheses()})


@app.route("/api/lab/env/capture", methods=["POST"])
def api_lab_env_capture():
    d = request.json or {}
    return jsonify(router.environment.capture(d.get("extra", {})))


@app.route("/api/lab/perceive", methods=["POST"])
def api_lab_perceive():
    d = request.json or {}
    # sandbox roots = projet operator (config-driven enforced by PerceptionEngine)
    roots = CONFIG.get("perception_roots") or []
    if roots:
        router.perception._allowed_roots = [__import__("pathlib").Path(r).resolve() for r in roots if __import__("os").path.exists(r)]
    return jsonify(router.perception.perceive(d.get("path", ""), note=d.get("note")))


@app.route("/api/lab/jev/route", methods=["POST"])
def api_lab_jev_route():
    d = request.json or {}
    return jsonify(router.jev.route(d.get("query", ""), log=False))


@app.route("/api/lab/jev/gate", methods=["POST"])
def api_lab_jev_gate():
    d = request.json or {}
    return jsonify(router.jev.gate(d.get("action", ""), log=False))


@app.route("/api/lab/jev/score", methods=["POST"])
def api_lab_jev_score():
    d = request.json or {}
    grid = d.get("grid", {})
    return jsonify(router.jev.score(dict(grid), subject=d.get("subject")))


@app.route("/api/lab/jev/decide", methods=["POST"])
def api_lab_jev_decide():
    d = request.json or {}
    return jsonify(router.jev.decide(d.get("context", ""), d.get("options", [])))


@app.route("/api/lab/quant/predict", methods=["POST"])
def api_lab_quant_predict():
    d = request.json or {}
    m = router.world.predict_quant(d["key"], float(d["range_min"]), float(d["range_max"]),
                                   env_id=d.get("env_id"))
    return jsonify({"id": m.id, "status": "pending"})


@app.route("/api/lab/quant/observe", methods=["POST"])
def api_lab_quant_observe():
    d = request.json or {}
    return jsonify(router.world.observe_quant(d["prediction_id"], float(d["actual"]),
                                              env_id=d.get("env_id")))


@app.route("/api/lab/quant/calibration")
def api_lab_quant_calibration():
    return jsonify(router.world.calibration())


# ══ CONFIG + EMBEDDINGS + CONSOLIDATION ════════════════════════

@app.route("/api/config")
def api_config_get():
    return jsonify({"config": CONFIG, "config_path": str(CONFIG_PATH)})


@app.route("/api/config", methods=["PUT"])
def api_config_set():
    d = request.json or {}
    for k, v in d.items():
        if k in CONFIG:
            CONFIG[k] = v
    save_config()
    llm.base_url = f"http://127.0.0.1:{CONFIG['llama_port']}"
    MODELS_CACHE["models"] = None  # invalidate
    return jsonify({"config": CONFIG})


@app.route("/api/rebuild-embeddings", methods=["POST"])
def api_rebuild():
    if not vector_store:
        return jsonify({"error": "vector unavailable"}), 400
    def bg():
        vector_store.rebuild()
    threading.Thread(target=bg, daemon=True).start()
    return jsonify({"started": True, "note": "re-embed en arrière-plan"})


@app.route("/api/autopush", methods=["POST"])
def api_autopush():
    """Git autopilot: export + commit + push (data repo from config)."""
    from jarvix_memory.core.autopush import push_project, autolog_dir
    d = request.json or {}
    try:
        result = push_project(router.db, str(autolog_dir()),
                              project_id=d.get("project_id"),
                              message=d.get("message"),
                              confirm=bool(d.get("confirm", True)))  # click UI = intention explicite
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/live")
def api_live():
    """Real-time bundle for the LLM (query optional)."""
    return jsonify(router.live.bundle(request.args.get("query", "")))


@app.route("/api/live/watch", methods=["POST"])
def api_live_watch():
    d = request.json or {}
    if d.get("action", "start") == "stop":
        return jsonify({"stopped": router.live.stop_watch()})
    return jsonify({"started": router.live.start_watch(),
                    "interval_min": router.live.interval_s() // 60})


@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "memories": router.stats(),
        "vector_store": vector_store.stats() if vector_store else {"embeddings": 0},
        "llm": llm.health(),
        "device": bilan_mod.check_device(),
        "db_version": get_version(router.db._connect()),
    })


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="JARVIX Memory UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    print(f"JARVIX Memory UI -> http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
