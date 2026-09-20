"""JARVIX Memory MCP Server — exposes all memory layers as MCP tools."""

import logging
import sys
import functools
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from jarvix_memory.router import MemoryRouter
import json
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("jarvix-mcp")

DB_PATH = str(Path(__file__).parent / "jarvix_memory.db")
logger.info("Using DB: %s", DB_PATH)

mcp = FastMCP("jarvix-memory", instructions="Persistent cognitive memory system for AI agents. Use tools to store, retrieve, verify, and learn from experiences.")

router = MemoryRouter(db_path=DB_PATH)
# Warm vector model in background — kill the 8s cold-start on first recall
if router.db.vector is not None:
    router.db.vector.warm()
# Scheduled consolidation: auto-archive stale actions / merge / decay every 6h
router.consolidation.start_scheduler(interval_hours=6.0)


def safe_tool(func):
    """Decorator: wraps MCP tool in try/except to prevent crashes."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error("Tool %s failed: %s", func.__name__, e)
            return json.dumps({"error": str(e), "tool": func.__name__})
    return wrapper


# ── Core Memory ────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def memory_add(content: str, memory_type: str = "semantic", confidence: float = 1.0, source: str = None) -> str:
    """Add a memory to any layer. Types: episodic, semantic, procedural, decision, graph, action, strategy, learning, recovery, world, evidence."""
    mem = router.db.insert_memory(
        __import__("jarvix_memory.core.models", fromlist=["Memory"]).Memory(
            type=memory_type, content=content, confidence=confidence, source=source
        )
    )
    return json.dumps({"id": mem.id, "type": memory_type, "status": "created"})


@mcp.tool()
@safe_tool
def memory_search(query: str, limit: int = 10) -> str:
    """Full-text search across all memory layers."""
    results = router.db.search_fts(query, limit=limit)
    return json.dumps(results, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def memory_get(memory_id: str) -> str:
    """Get a specific memory by ID."""
    result = router.db.get_memory(memory_id)
    if not result:
        return json.dumps({"error": "not found"})
    return json.dumps(result, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def memory_list(memory_type: str = None, limit: int = 20) -> str:
    """List memories, optionally filtered by type."""
    if memory_type:
        results = router.db.search_by_type(memory_type, limit=limit)
    else:
        results = router.db.list_all(limit=limit)
    return json.dumps(results, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def memory_stats() -> str:
    """Get memory statistics across all layers."""
    return json.dumps(router.stats(), ensure_ascii=False)


# ── Episodic ───────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def episodic_log(action: str, result: str, metadata: str = "{}") -> str:
    """Log an event (action + result) to episodic memory."""
    meta = json.loads(metadata) if metadata else {}
    mem = router.episodic.log_event(action, result, metadata=meta)
    return json.dumps({"id": mem.id, "type": "episodic"})


@mcp.tool()
@safe_tool
def episodic_recent(limit: int = 10) -> str:
    """Get recent episodic memories."""
    return json.dumps(router.episodic.recent(limit=limit), default=str, ensure_ascii=False)


# ── Semantic ───────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def semantic_add(fact: str, confidence: float = 1.0, source: str = None) -> str:
    """Store a fact in semantic memory."""
    mem = router.semantic.add_fact(fact, confidence=confidence, source=source)
    return json.dumps({"id": mem.id, "type": "semantic"})


@mcp.tool()
@safe_tool
def semantic_facts(min_confidence: float = 0.5) -> str:
    """Get facts above a confidence threshold."""
    return json.dumps(router.semantic.get_facts(min_confidence), default=str, ensure_ascii=False)


# ── Graph ──────────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def graph_relation(subject: str, predicate: str, obj: str) -> str:
    """Add a relation: subject --[predicate]--> object."""
    mem = router.graph.add_relation(subject, predicate, obj)
    return json.dumps({"id": mem.id, "type": "graph"})


@mcp.tool()
@safe_tool
def graph_entity(entity: str) -> str:
    """Get all relations for an entity."""
    return json.dumps(router.graph.get_relations_for_entity(entity), default=str, ensure_ascii=False)


# ── Decision ───────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def decision_log(decision: str, reasoning: str, alternatives: str = "[]") -> str:
    """Log a decision with reasoning and alternatives."""
    alts = json.loads(alternatives) if alternatives else []
    mem = router.decision.log_decision(decision, reasoning, alternatives=alts)
    return json.dumps({"id": mem.id, "type": "decision"})


@mcp.tool()
@safe_tool
def decision_recent(limit: int = 10) -> str:
    """Get recent decisions."""
    return json.dumps(router.decision.recent_decisions(limit=limit), default=str, ensure_ascii=False)


# ── Verification ───────────────────────────────────────────────

@mcp.tool()
@safe_tool
def verify_claim(content: str, source: str = None) -> str:
    """Create a claim to be verified. Returns claim ID for adding evidence."""
    claim = router.verification.claim(content, source=source)
    return json.dumps({"id": claim.id, "verdict": "claim", "status": "provisional"})


@mcp.tool()
@safe_tool
def verify_add_evidence(claim_id: str, evidence_type: str, description: str, passed: bool) -> str:
    """Add evidence to a claim. Types: file_exists, file_diff, git_diff, compile_ok, test_pass, command_output, measurement, manual."""
    result = router.verification.add_evidence(claim_id, evidence_type, description, passed)
    if not result:
        return json.dumps({"error": "claim not found"})
    return json.dumps(result, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def verify_resolve(claim_id: str) -> str:
    """Resolve a claim based on accumulated evidence. Returns verdict: verified/rejected/inconclusive."""
    return json.dumps(router.verification.resolve(claim_id), ensure_ascii=False)


@mcp.tool()
@safe_tool
def verify_claims(verdict: str = None, limit: int = 20) -> str:
    """List claims, optionally filtered by verdict."""
    return json.dumps(router.verification.get_claims(verdict=verdict, limit=limit), default=str, ensure_ascii=False)


# ── Action ─────────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def action_propose(description: str, based_on: str = "[]", priority: int = 5) -> str:
    """Propose a next action. Returns action ID for approval."""
    refs = json.loads(based_on) if based_on else []
    mem = router.action.propose(description, based_on=refs, priority=priority)
    return json.dumps({"id": mem.id, "status": "proposed"})


@mcp.tool()
@safe_tool
def action_approve(action_id: str) -> str:
    """Approve a proposed action."""
    ok = router.action.approve(action_id)
    return json.dumps({"approved": ok})


@mcp.tool()
@safe_tool
def action_execute(action_id: str, result: str = None, success: bool = True) -> str:
    """Mark an action as executed (success or failure)."""
    ok = router.action.execute(action_id, result=result, success=success)
    return json.dumps({"executed": ok})


@mcp.tool()
@safe_tool
def action_pending() -> str:
    """List pending proposed actions."""
    return json.dumps(router.action.pending(), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def action_next(context: str, limit: int = 5) -> str:
    """Suggest next actions based on current context (hypotheses, errors, evidence)."""
    return json.dumps(router.action.propose_next_actions(context, limit=limit), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def action_history(limit: int = 20) -> str:
    """Get executed action history."""
    return json.dumps(router.action.history(limit=limit), default=str, ensure_ascii=False)


# ── Strategy ───────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def strategy_add(name: str, situation: str, steps: str, rationale: str = None) -> str:
    """Add a strategy for a situation. Steps is a JSON array of strings."""
    step_list = json.loads(steps) if steps else []
    mem = router.strategy.add_strategy(name, situation, step_list, rationale=rationale)
    return json.dumps({"id": mem.id, "type": "strategy"})


@mcp.tool()
@safe_tool
def strategy_attempt(strategy_id: str, success: bool, cost_minutes: float = 0.0) -> str:
    """Record an attempt at a strategy."""
    ok = router.strategy.record_attempt(strategy_id, success=success, cost_minutes=cost_minutes)
    return json.dumps({"recorded": ok})


@mcp.tool()
@safe_tool
def strategy_rate(strategy_id: str) -> str:
    """Get success rate and stats for a strategy."""
    return json.dumps(router.strategy.success_rate(strategy_id), ensure_ascii=False)


@mcp.tool()
@safe_tool
def strategy_best(situation: str, limit: int = 3) -> str:
    """Find best strategies for a situation."""
    results = router.strategy.best_for_situation(situation, limit=limit)
    for r in results:
        r["strategy"] = r["strategy"]["content"][:200] if "content" in r["strategy"] else str(r["strategy"])
    return json.dumps(results, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def strategy_leaderboard(limit: int = 10) -> str:
    """Get strategy leaderboard ranked by success rate."""
    return json.dumps(router.strategy.leaderboard(limit=limit), default=str, ensure_ascii=False)


# ── Learning ───────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def learning_record(experience_id: str, evaluation: str, score: float, what_was_learned: str, policy_update: str = "{}") -> str:
    """Record a learning outcome from an experience."""
    pu = json.loads(policy_update) if policy_update else {}
    mem = router.learning.record_outcome(experience_id, evaluation, score, what_was_learned, policy_update=pu)
    return json.dumps({"id": mem.id, "type": "learning"})


@mcp.tool()
@safe_tool
def learning_policies() -> str:
    """Get all accumulated policies from learnings."""
    return json.dumps(router.learning.get_policies(), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def learning_abandon(strategy_id: str, threshold: float = 0.3) -> str:
    """Check if a strategy should be abandoned based on learning history."""
    return json.dumps(router.learning.should_abandon(strategy_id, threshold=threshold), ensure_ascii=False)


# ── Recovery ───────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def recovery_fail(action_id: str, error: str, hypothesis: str = None) -> str:
    """Record a failure and start recovery tracking."""
    mem = router.recovery.record_failure(action_id, error, hypothesis=hypothesis)
    return json.dumps({"id": mem.id, "status": "failed"})


@mcp.tool()
@safe_tool
def recovery_diagnose(recovery_id: str, diagnosis: str, new_hypothesis: str = None) -> str:
    """Diagnose a failure and optionally update hypothesis."""
    ok = router.recovery.diagnose(recovery_id, diagnosis, new_hypothesis=new_hypothesis)
    return json.dumps({"diagnosed": ok})


@mcp.tool()
@safe_tool
def recovery_retry(recovery_id: str) -> str:
    """Retry a failed action (max 5 attempts)."""
    return json.dumps(router.recovery.retry(recovery_id), ensure_ascii=False)


@mcp.tool()
@safe_tool
def recovery_recovered(recovery_id: str) -> str:
    """Mark a recovery as successful."""
    ok = router.recovery.mark_recovered(recovery_id)
    return json.dumps({"recovered": ok})


@mcp.tool()
@safe_tool
def recovery_active() -> str:
    """List active (unresolved) recoveries."""
    return json.dumps(router.recovery.active_recoveries(), default=str, ensure_ascii=False)


# ── Proactive ──────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def proactive_inject(context: str) -> str:
    """Check if any memory should be proactively injected into this context. Returns reminder or null."""
    result = router.proactive.inject(context)
    return json.dumps({"reminder": result, "injected": result is not None})


@mcp.tool()
@safe_tool
def proactive_should(context: str) -> str:
    """List memories that should be injected into context (without injecting)."""
    return json.dumps(router.proactive.should_inject(context), default=str, ensure_ascii=False)


# ── World Model ────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def world_state() -> str:
    """Get current world model state (beliefs about the world)."""
    return json.dumps(router.world.get_state(), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def world_beliefs() -> str:
    """Get all beliefs in the world model."""
    return json.dumps(router.world.get_beliefs(), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def world_update(key: str, value: str, confidence: float = 0.8) -> str:
    """Update a world state belief."""
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        parsed = value
    mem = router.world.update_state(key, parsed, confidence=confidence)
    return json.dumps({"id": mem.id, "key": key, "value": parsed})


@mcp.tool()
@safe_tool
def world_predict(hypothesis: str, expected_result: str = None, expected_risk: float = 0.0) -> str:
    """Make a prediction to be tested against reality."""
    try:
        expected = json.loads(expected_result) if expected_result else None
    except (json.JSONDecodeError, TypeError):
        expected = expected_result
    mem = router.world.predict(hypothesis, expected_result=expected, expected_risk=expected_risk)
    return json.dumps({"id": mem.id, "status": "pending"})


@mcp.tool()
@safe_tool
def world_observe(prediction_id: str, actual_result: str) -> str:
    """Observe the actual result of a prediction."""
    try:
        actual = json.loads(actual_result)
    except (json.JSONDecodeError, TypeError):
        actual = actual_result
    return json.dumps(router.world.observe(prediction_id, actual_result=actual), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def world_accuracy() -> str:
    """Get prediction accuracy stats."""
    return json.dumps(router.world.accuracy(), ensure_ascii=False)


@mcp.tool()
@safe_tool
def world_predictions(status: str = "pending", limit: int = 20) -> str:
    """List predictions by status (pending/observed)."""
    return json.dumps(router.world.get_predictions(status=status, limit=limit), default=str, ensure_ascii=False)


# ── Consolidation ──────────────────────────────────────────────

@mcp.tool()
@safe_tool
def consolidation_run() -> str:
    """Run memory consolidation (decay, merge, archive)."""
    router.consolidation.run_sleep_cycle()
    return json.dumps({"status": "complete", "stats": router.consolidation.stats()}, ensure_ascii=False)


# ── Procedural ─────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def procedural_skill(name: str, procedure: str, success_rate: float = 1.0) -> str:
    """Store a skill/procedure."""
    mem = router.procedural.add_skill(name, procedure, success_rate=success_rate)
    return json.dumps({"id": mem.id, "type": "procedural", "name": name})


@mcp.tool()
@safe_tool
def procedural_get(name: str) -> str:
    """Get a skill by name."""
    result = router.procedural.get_skill(name)
    return json.dumps(result if result else {"error": "not found"}, default=str, ensure_ascii=False)


# ── Proactive Rules ────────────────────────────────────────────

@mcp.tool()
@safe_tool
def proactive_add_rule(name: str, trigger_condition: str, memory_type: str = None,
                       max_age_hours: int = 24, min_importance: float = 0.5,
                       priority: int = 5) -> str:
    """Add a proactive injection rule (persisted in DB)."""
    try:
        rule = router.proactive.add_rule(
            name=name, trigger_condition=trigger_condition,
            memory_type=memory_type, max_age_hours=max_age_hours,
            min_importance=min_importance, priority=priority,
        )
        return json.dumps({"id": rule["id"], "name": rule["name"]})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@safe_tool
def proactive_remove_rule(rule_id: str) -> str:
    """Remove a proactive rule by ID."""
    try:
        router.proactive.remove_rule(rule_id)
        return json.dumps({"removed": True})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
@safe_tool
def proactive_list_rules() -> str:
    """List all active proactive rules."""
    rules = router.proactive.list_rules()
    return json.dumps(rules, default=str, ensure_ascii=False)


# ── Bilan ──────────────────────────────────────────────────────

@mcp.tool()
@safe_tool
def bilan(short: bool = False, save: bool = False, analyze: bool = False) -> str:
    """Generate autonomous project status report (memory + filesystem + device + llama.cpp + LLM analysis)."""
    import importlib.util
    bilan_path = Path(__file__).parent / "bilan.py"
    spec = importlib.util.spec_from_file_location("bilan", bilan_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.generate_report(save=save, as_json=False, short=short, analyze=analyze)


# ── Vector Search + LLM Reasoning ──────────────────────────────

def _get_vector():
    return router.db.vector


def _get_llm():
    from jarvix_memory.llm.reasoner import LLMReasoner
    if not hasattr(router, "_llm"):
        router._llm = LLMReasoner(router.db, vector_store=router.db.vector)
    return router._llm


@mcp.tool()
@safe_tool
def memory_search_semantic(query: str, limit: int = 10, min_score: float = 0.2) -> str:
    """Semantic search via embeddings (vector RAG). Falls back to text search if unavailable."""
    v = _get_vector()
    if v is None:
        return json.dumps({"error": "vector search unavailable (sentence-transformers not installed)"})
    results = v.search(query, limit=limit, min_score=min_score)
    return json.dumps(results, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def memory_search_hybrid(query: str, limit: int = 10) -> str:
    """Hybrid search: vector + text merged and deduplicated."""
    results = router.db.search_hybrid(query, limit=limit)
    return json.dumps(results, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def llm_reason(query: str, max_tokens: int = 1024) -> str:
    """RAG pipeline: retrieve relevant memories + LLM reasoning. Requires llama.cpp on port 8080."""
    llm = _get_llm()
    result = llm.reason(query, max_tokens=max_tokens)
    return json.dumps(result, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def llm_summarize(text: str, max_tokens: int = 256) -> str:
    """Summarize text with the local LLM."""
    llm = _get_llm()
    return llm.summarize(text, max_tokens=max_tokens)


@mcp.tool()
@safe_tool
def llm_connections(memory_id: str) -> str:
    """Find connections between a memory and related memories (LLM-powered)."""
    llm = _get_llm()
    result = llm.find_connections(memory_id)
    return json.dumps(result, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def llm_health() -> str:
    """Check local LLM server health (llama.cpp port 8080)."""
    llm = _get_llm()
    return json.dumps(llm.health())


@mcp.tool()
@safe_tool
def embeddings_rebuild() -> str:
    """Re-embed all memories (after model change or DB import)."""
    v = _get_vector()
    if v is None:
        return json.dumps({"error": "vector search unavailable"})
    count = v.rebuild()
    return json.dumps({"embedded": count, "model": v.stats()["model"]})


@mcp.tool()
@safe_tool
def embeddings_stats() -> str:
    """Vector store statistics (count, model, dimensions)."""
    v = _get_vector()
    if v is None:
        return json.dumps({"error": "vector search unavailable", "embeddings": 0})
    return json.dumps(v.stats())


# ── P0: Auto-Verification / Environment / Experiment ───────────

@mcp.tool()
@safe_tool
def verify_auto(claim_content: str, checks: str, permanent: bool = False) -> str:
    """Create claim and run automatic checks. checks = JSON array of
    {"type":"file_exists"|"file_contains"|"command"|"git_diff"|"measurement", "description":..., ...params}.
    Types: file_exists {path} ; file_contains {path,needle} ; command {cmd,expect_rc,expect_stdout} ;
    git_diff {repo,contains,since_ref} ; measurement {actual,op,expected} (op: gt/gte/lt/lte/eq/ne)."""
    claim = router.verification.claim(claim_content, source="auto_verify")
    checks_list = json.loads(checks) if checks else []
    result = router.auto_verify.verify_auto(claim.id, checks_list, auto_resolve=True)
    result["claim_id"] = claim.id
    return json.dumps(result, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def env_capture(extra_json: str = "{}") -> str:
    """Capture an environment snapshot (OS/python/git/device). Returns env_id to reference in hypotheses/experiments."""
    extra = json.loads(extra_json) if extra_json else {}
    result = router.environment.capture(extra)
    return json.dumps(result, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def env_diff(env_a: str, env_b: str) -> str:
    """Compare two environment snapshots — changed keys mean results are no longer comparable."""
    return json.dumps(router.environment.diff(env_a, env_b), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def env_get(env_id: str) -> str:
    """Get a stored environment snapshot by env_id."""
    result = router.environment.get(env_id)
    return json.dumps(result or {"error": "not found"}, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def hyp_propose(statement: str, env_id: str = None, rationale: str = None) -> str:
    """Propose a testable hypothesis. Returns hypothesis id for experiments."""
    result = router.experiment.propose_hypothesis(statement, env_id=env_id, rationale=rationale)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
@safe_tool
def hyp_repeat_guard(statement: str) -> str:
    """Check if an experiment path was already REFUTED (do_not_repeat). Call BEFORE re-testing anything."""
    return json.dumps(router.experiment.repeat_guard(statement), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def hyp_run(hyp_id: str, name: str, result: str, success: bool, env_id: str = None, measurements: str = "{}") -> str:
    """Record an experiment run against a hypothesis."""
    meas = json.loads(measurements) if measurements else {}
    out = router.experiment.run_experiment(hyp_id, name, result, success, env_id=env_id, measurements=meas)
    return json.dumps(out, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def hyp_conclude(hyp_id: str, verdict: str) -> str:
    """Conclude a hypothesis: confirmed | refuted | inconclusive | superseded. refuted sets do_not_repeat=true."""
    out = router.experiment.conclude(hyp_id, verdict)
    return json.dumps(out, ensure_ascii=False)


@mcp.tool()
@safe_tool
def hyp_pending() -> str:
    """List hypotheses still to be tested (PROPOSED/TESTING)."""
    return json.dumps(router.experiment.pending_hypotheses(), default=str, ensure_ascii=False)


# ── P1: Cost-aware / Strategy recommend / Recovery guards / Proactive monitor ──

@mcp.tool()
@safe_tool
def recall_cost(query: str, limit: int = 10, budget_tokens: int = None) -> str:
    """P1.4 — hybrid recall ranked by value/cost (relevance*confidence*utility per token). Optional token budget."""
    return json.dumps(router.db.recall_cost_aware(query, limit=limit, budget_tokens=budget_tokens),
                      default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def memory_usage_record(memory_id: str) -> str:
    """Reinforce a memory (+utility) after it proved useful in context."""
    return json.dumps({"recorded": router.db.record_usage(memory_id)})


@mcp.tool()
@safe_tool
def strategy_recommend(situation: str, min_samples: int = 1, cost_weight: float = 0.2) -> str:
    """P1.5 — best strategies for a situation by value/cost: rate*relevance/(1+cost*avg_minutes). Unproven listed separately."""
    return json.dumps(router.strategy.recommend(situation, min_samples=min_samples, cost_weight=cost_weight),
                      default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def recovery_history(limit: int = 20) -> str:
    """List recovered failure cycles (amount of learning from errors)."""
    return json.dumps(router.recovery.recovery_history(limit=limit), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def proactive_monitor(context: str) -> str:
    """P1.7 — should memory interrupt NOW? rules + refuted-experiment guard + active failures. Default: silence."""
    result = router.proactive.monitor(context,
                                      experiment_tracker=router.experiment,
                                      recovery_layer=router.recovery)
    return json.dumps(result, default=str, ensure_ascii=False)


# ── P2: Perception / Predictive world / JEV ────────────────────

@mcp.tool()
@safe_tool
def perceive_file(path: str, note: str = None) -> str:
    """P2.8 — artifact -> observation + evidence (sha256, signaux log, OCR si dispo)."""
    return json.dumps(router.perception.perceive(path, note=note), ensure_ascii=False)


@mcp.tool()
@safe_tool
def world_predict_quant(key: str, range_min: float, range_max: float, env_id: str = None) -> str:
    """P2.9 — predict a numeric range (tok/s, RAM, temp). Observe later with world_observe_quant."""
    m = router.world.predict_quant(key, range_min, range_max, env_id=env_id)
    return json.dumps({"id": m.id, "status": "pending"})


@mcp.tool()
@safe_tool
def world_observe_quant(prediction_id: str, actual: float, env_id: str = None) -> str:
    """P2.9 — observe the real measurement; updates calibration of the belief (exponential smoothing)."""
    return json.dumps(router.world.observe_quant(prediction_id, actual, env_id=env_id))


@mcp.tool()
@safe_tool
def world_calibration(limit: int = 100) -> str:
    """P2.9 — prediction quality per key: hit_rate + MAPE (mean absolute percentage error)."""
    return json.dumps(router.world.calibration(limit=limit))


@mcp.tool()
@safe_tool
def jev_route(query: str) -> str:
    """P2.10 — JEV Noul: which memory layer(s) matter for this query (typed distribution)."""
    return json.dumps(router.jev.route(query))


@mcp.tool()
@safe_tool
def jev_gate(action: str, destructive_threshold: float = 0.85) -> str:
    """P2.10 — JEV gate: ALLOW/REVIEW/BLOCK for a proposed action (destructive check)."""
    return json.dumps(router.jev.gate(action, destructive_threshold))


@mcp.tool()
@safe_tool
def jev_score(subject: str, grid: str) -> str:
    """P2.10 — JEV Score: grid = JSON {criterion: 0..1, "_weights": {...optional}}."""
    g = json.loads(grid) if grid else {}
    return json.dumps(router.jev.score(g, subject=subject))


@mcp.tool()
@safe_tool
def jev_decide(context: str, options: str) -> str:
    """P2.10 — JEV Choice: options = JSON array of strings. Returns winner + distribution."""
    opts = json.loads(options) if options else []
    return json.dumps(router.jev.decide(context, opts))


# ── Git autopilot ──────────────────────────────────────────────

@mcp.tool()
@safe_tool
def autopush(project_id: str = None, message: str = None, confirm: bool = False) -> str:
    """Export memories by project_id to docs/memoire_<project>.md. DRY-RUN by default; confirm=True required for actual commit+push (data repo from config.json autolog_dir)."""
    from jarvix_memory.core.autopush import push_project, autolog_dir
    result = push_project(router.db, str(autolog_dir()),
                          project_id=project_id, message=message, confirm=confirm)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
@safe_tool
def ingest_directory(path: str, note: str = None) -> str:
    """Scan a directory (bounded 5000 files, depth 4) and store a semantic inventory in memory (files, types, sizes, subdirs). Push influence via config scan_dirs."""
    from jarvix_memory.core.ingest import ingest_directory
    result = ingest_directory(router.db, path, note=note)
    return json.dumps(result, default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def scan_directory_info(path: str, max_files: int = 5000) -> str:
    """Dry inventory of a directory (no memory written): file counts per type, sizes, subdirs."""
    from jarvix_memory.core.ingest import scan_directory
    return json.dumps(scan_directory(path, max_files=max_files), default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def jev_status() -> str:
    """JEV remote provider health + monthly decision quota (jev-agent/TypeSafe)."""
    provider = router.jev.provider
    if hasattr(provider, "status"):
        return json.dumps(provider.status())
    return json.dumps({"provider": "rules", "available": True})


# ── Live context (real-time LLM feeding + watcher) ─────────────

@mcp.tool()
@safe_tool
def live_context(query: str = "", max_tokens: int = 4000) -> str:
    """One payload for the LLM: fresh inventories + facts + open hypotheses + active recoveries. THE thing to call before working the project."""
    return json.dumps(router.live.bundle(query, max_tokens=max_tokens),
                      default=str, ensure_ascii=False)


@mcp.tool()
@safe_tool
def live_watch(action: str = "start") -> str:
    """start/stop the realtime watcher: periodic re-ingest of config scan_dirs + autopush to private repo (default 30min, config live_interval_min)."""
    if action == "stop":
        return json.dumps({"stopped": router.live.stop_watch()})
    return json.dumps({"started": router.live.start_watch(),
                      "interval_min": router.live.interval_s() // 60})


if __name__ == "__main__":
    mcp.run()
