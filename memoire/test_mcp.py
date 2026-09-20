"""Quick test of all MCP-backed memory layers."""
from mcp_server import router
import json

print("=== TEST MCP SERVER ===\n")
passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        print(f"  PASS {name}")
        passed += 1
    else:
        print(f"  FAIL {name}")
        failed += 1

# 1. Episodic
mem = router.episodic.log_event("test action", "test result")
check("episodic_log", mem.id is not None)
recent = router.episodic.recent(1)
check("episodic_recent", len(recent) >= 1)

# 2. Semantic
mem = router.semantic.add_fact("SM8850 has HTP v81", confidence=0.99)
check("semantic_add", mem.id is not None)
facts = router.semantic.get_facts(0.5)
check("semantic_facts", len(facts) >= 1)

# 3. Graph
mem = router.graph.add_relation("Qwen3.5-9B", "runs_on", "HTP v81")
check("graph_relation", "HTP v81" in mem.content)
rels = router.graph.get_relations_for_entity("HTP v81")
check("graph_entity", len(rels) >= 1)

# 4. Decision
mem = router.decision.log_decision("Use Q4_K_M", "best tradeoff", alternatives=["Q5_K_M"])
check("decision_log", mem.id is not None)
decs = router.decision.recent_decisions(1)
check("decision_recent", len(decs) >= 1)

# 5. Procedural
mem = router.procedural.add_skill("build_apk", "gradle assembleDebug", 0.95)
check("procedural_skill", mem.id is not None)
skill = router.procedural.get_skill("build_apk")
check("procedural_get", skill is not None)

# 6. Verification
claim = router.verification.claim("Fixed OOM crash")
check("verify_claim", claim.id is not None)
ev1 = router.verification.add_evidence(claim.id, "test_pass", "unit test passed", True)
check("verify_add_evidence_pass", ev1 is not None)
ev2 = router.verification.add_evidence(claim.id, "compile_ok", "build succeeded", True)
check("verify_add_evidence_pass2", ev2 is not None)
ev3 = router.verification.add_evidence(claim.id, "file_diff", "diff shows fix", False)
check("verify_add_evidence_fail", ev3 is not None)
result = router.verification.resolve(claim.id)
check("verify_resolve", result["verdict"] in ("verified", "rejected", "inconclusive"))

# 7. Action
action = router.action.propose("Test memory leak fix", priority=8)
check("action_propose", action.id is not None and action.metadata["status"] == "proposed")
ok = router.action.approve(action.id)
check("action_approve", ok)
ok = router.action.execute(action.id, result="no leak", success=True)
check("action_execute", ok)
pending = router.action.pending()
check("action_pending_empty", len(pending) == 0)
actions = router.action.propose_next_actions("test context")
check("action_next", isinstance(actions, list))
history = router.action.history(1)
check("action_history", len(history) >= 1)

# 8. Strategy
s = router.strategy.add_strategy("OOM debug", "QNN crash", ["check alloc", "check mmap"])
check("strategy_add", s.id is not None)
ok = router.strategy.record_attempt(s.id, success=True, cost_minutes=2.5)
check("strategy_attempt", ok)
rate = router.strategy.success_rate(s.id)
check("strategy_rate", rate["attempts"] == 1 and rate["successes"] == 1)
best = router.strategy.best_for_situation("QNN crash")
check("strategy_best", len(best) >= 1)
lb = router.strategy.leaderboard(5)
check("strategy_leaderboard", isinstance(lb, list))

# 9. Learning
l = router.learning.record_outcome(s.id, "mmap was root", 0.9, "check mmap first", {"check_mmap": True})
check("learning_record", l.id is not None)
policies = router.learning.get_policies()
check("learning_policies", "check_mmap" in policies)
abandon = router.learning.should_abandon(s.id, 0.3)
check("learning_abandon", abandon["abandon"] is False)

# 10. Recovery
rec = router.recovery.record_failure("build_001", "SIGSEGV", hypothesis="bad ptr")
check("recovery_fail", rec.id is not None and rec.metadata["status"] == "failed")
ok = router.recovery.diagnose(rec.id, "null ptr in skel", new_hypothesis="skel mismatch")
check("recovery_diagnose", ok)
result = router.recovery.retry(rec.id)
check("recovery_retry", result["retrying"] is True and result["attempt"] == 2)
ok = router.recovery.mark_recovered(rec.id)
check("recovered", ok)
active = router.recovery.active_recoveries()
check("recovery_active", isinstance(active, list))

# 11. Proactive
router.proactive.add_recent_episode_reminder(hours=1)
router.proactive.add_unresolved_error_reminder()
router.proactive.add_hypothesis_reminder()
check("proactive_rules", len(router.proactive._rules) >= 3)
reminders = router.proactive.should_inject("some context")
check("proactive_should", isinstance(reminders, list))
stats = router.proactive.stats()
check("proactive_stats", stats["rules"] >= 3)

# 12. World Model
mem = router.world.update_state("device_temp", 62.0)
check("world_update", mem.id is not None)
state = router.world.get_state()
check("world_state", state["beliefs"]["device_temp"]["value"] == 62.0)
beliefs = router.world.get_beliefs()
check("world_beliefs", "device_temp" in beliefs)
pred = router.world.predict("MBUF=3500 improves throughput", expected_result="+24%")
check("world_predict", pred.id is not None)
obs = router.world.observe(pred.id, actual_result="+24.2%")
check("world_observe", obs["match"] is False)
acc = router.world.accuracy()
check("world_accuracy", acc["total"] >= 1)
preds = router.world.get_predictions("observed")
check("world_predictions", len(preds) >= 1)

# 13. Consolidation
router.consolidation.run_sleep_cycle()
cstats = router.consolidation.stats()
check("consolidation_run", isinstance(cstats, dict))

# 14. Stats
stats = router.stats()
check("memory_stats", stats["total_memories"] > 0)

# 15. FTS search
results = router.db.search_fts("HTP")
check("fts_search", len(results) >= 1)

# 16. CRUD
mem = router.episodic.add_memory("to delete")
got = router.db.get_memory(mem.id)
check("db_get", got is not None)
ok = router.db.update_memory(mem.id, content="updated content")
check("db_update", ok)
got2 = router.db.get_memory(mem.id)
check("db_updated_content", got2["content"] == "updated content")
ok = router.db.delete_memory(mem.id)
check("db_delete", ok)
got3 = router.db.get_memory(mem.id)
check("db_deleted", got3 is None)

print(f"\n{'='*40}")
print(f"RESULTS: {passed} passed, {failed} failed out of {passed+failed}")
if failed == 0:
    print("ALL TESTS PASSED")
else:
    print(f"WARNING: {failed} TESTS FAILED")
