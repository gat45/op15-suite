from jarvix_memory.router import MemoryRouter


def main():
    router = MemoryRouter()

    print("=== JARVIX Memory v0.3.0 ===\n")

    # --- Base layers ---
    print("[1/5] Logging episodic event...")
    router.episodic.log_event("Tested Qwen3.5-9B", "Success on SM8850")

    print("[2/5] Adding semantic fact...")
    router.semantic.add_fact("Qwen3.5-9B works on SM8850", confidence=0.95)

    print("[3/5] Adding graph relation...")
    router.graph.add_relation("Qwen3.5-9B", "uses", "Q4_K_M")

    # --- Verification ---
    print("[4/5] Verification engine...")
    claim = router.verification.claim("Fixed crash in build.cpp")
    router.verification.add_evidence(claim.id, "file_exists", "build.cpp exists", True)
    router.verification.add_evidence(claim.id, "compile_ok", "compilation succeeded", True)
    verdict = router.verification.resolve(claim.id)
    print(f"  Verdict: {verdict['verdict']}")

    # --- Action ---
    print("[5a/5] Action layer...")
    action = router.action.propose(
        "Test mmap configuration", based_on=[claim.id], priority=7
    )
    router.action.approve(action.id)
    router.action.execute(action.id, result="mmap test passed", success=True)

    # --- Strategy ---
    print("[5b/5] Strategy memory...")
    strat = router.strategy.add_strategy(
        name="QNN debug",
        situation="QNN crash on memory allocation",
        steps=["check allocation", "measure RSS", "verify mmap"],
        rationale="Memory issues are most common cause",
    )
    router.strategy.record_attempt(strat.id, success=True, cost_minutes=3.2)
    best = router.strategy.best_for_situation("QNN crash")
    print(f"  Best strategy: {best[0]['strategy']['content'][:60] if best else 'none'}")

    # --- Learning ---
    print("[5c/5] Learning layer...")
    router.learning.record_outcome(
        experience_id=strat.id,
        evaluation="mmap was indeed the issue",
        score=0.9,
        what_was_learned="Always check mmap before modifying backend",
        policy_update={"check_mmap_first": True},
    )

    # --- Recovery ---
    print("[5d/5] Recovery layer...")
    rec = router.recovery.record_failure(
        action_id="test_001", error="OOM during HTP load", hypothesis="memory leak"
    )
    router.recovery.diagnose(rec.id, "HTP session too large", new_hypothesis="HTP buffer overflow")
    router.recovery.retry(rec.id)

    # --- Proactive ---
    print("[5e/5] Proactive memory...")
    router.proactive.add_unresolved_error_reminder()
    router.proactive.add_recent_episode_reminder(hours=1)
    reminder = router.proactive.inject("QNN crash context")
    print(f"  Reminder: {reminder or '(none)'}")

    # --- World Model ---
    print("[5f/5] World model...")
    router.world.update_state("device_temp", 65.0)
    pred = router.world.predict("MBUF=3500 improves throughput", expected_result="+24%")
    router.world.observe(pred.id, actual_result="+24.2%")
    acc = router.world.accuracy()
    print(f"  Prediction accuracy: {acc['accuracy']:.1%}")

    # --- Stats ---
    print("\n=== Stats ===")
    for k, v in router.stats().items():
        print(f"  {k}: {v}")

    # --- Consolidation ---
    print("\nRunning consolidation...")
    router.consolidation.run_sleep_cycle()
    print("Done.")


if __name__ == "__main__":
    main()
