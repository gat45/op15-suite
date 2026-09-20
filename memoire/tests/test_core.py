import pytest
import os
import tempfile
from jarvix_memory.router import MemoryRouter


@pytest.fixture
def router(tmp_path):
    db_path = str(tmp_path / "test.db")
    return MemoryRouter(db_path)


class TestDatabase:
    def test_insert_and_get(self, router):
        mem = router.episodic.add_memory("test content")
        got = router.db.get_memory(mem.id)
        assert got is not None
        assert got["content"] == "test content"

    def test_search_fts(self, router):
        router.semantic.add_fact("Qwen3 works on SM8850")
        results = router.db.search_fts("Qwen3")
        assert len(results) >= 1

    def test_search_by_type(self, router):
        router.episodic.add_memory("episode 1")
        router.episodic.add_memory("episode 2")
        results = router.db.search_by_type("episodic")
        assert len(results) == 2

    def test_count(self, router):
        router.episodic.add_memory("a")
        router.semantic.add_fact("b")
        assert router.db.count() == 2
        assert router.db.count("episodic") == 1

    def test_delete_memory(self, router):
        mem = router.episodic.add_memory("to delete")
        assert router.db.delete_memory(mem.id) is True
        assert router.db.get_memory(mem.id) is None

    def test_update_memory(self, router):
        mem = router.episodic.add_memory("original")
        router.db.update_memory(mem.id, content="updated")
        got = router.db.get_memory(mem.id)
        assert got["content"] == "updated"


class TestEpisodic:
    def test_log_event(self, router):
        mem = router.episodic.log_event("ran test", "passed")
        assert "ran test" in mem.content
        assert "passed" in mem.content

    def test_recent(self, router):
        router.episodic.add_memory("old")
        router.episodic.add_memory("new")
        recent = router.episodic.recent(limit=1)
        assert len(recent) == 1


class TestSemantic:
    def test_add_fact(self, router):
        mem = router.semantic.add_fact("fact 1", confidence=0.9)
        assert mem.content == "fact 1"


class TestProcedural:
    def test_add_skill(self, router):
        mem = router.procedural.add_skill("build", "run gradle", success_rate=0.95)
        assert "build" in mem.metadata.get("name", "")


class TestGraph:
    def test_add_relation(self, router):
        mem = router.graph.add_relation("A", "uses", "B")
        assert "A" in mem.content
        assert "B" in mem.content


class TestDecision:
    def test_log_decision(self, router):
        mem = router.decision.log_decision("use NPU", "faster", alternatives=["GPU"])
        assert "use NPU" in mem.content


class TestVerification:
    def test_claim_and_resolve(self, router):
        claim = router.verification.claim("Fixed the bug")
        assert claim.status == "provisional"

        router.verification.add_evidence(claim.id, "file_exists", "file exists", True)
        router.verification.add_evidence(claim.id, "test_pass", "tests pass", True)
        result = router.verification.resolve(claim.id)
        assert result["verdict"] == "verified"

    def test_rejected_claim(self, router):
        claim = router.verification.claim("Will work")
        router.verification.add_evidence(claim.id, "test_pass", "failed", False)
        router.verification.add_evidence(claim.id, "compile_ok", "failed", False)
        result = router.verification.resolve(claim.id)
        assert result["verdict"] == "rejected"

    def test_inconclusive_claim(self, router):
        claim = router.verification.claim("Maybe")
        router.verification.add_evidence(claim.id, "test_pass", "passed", True)
        router.verification.add_evidence(claim.id, "compile_ok", "failed", False)
        result = router.verification.resolve(claim.id)
        assert result["verdict"] == "inconclusive"


class TestAction:
    def test_propose_approve_execute(self, router):
        action = router.action.propose("Fix crash", priority=8)
        assert action.metadata["status"] == "proposed"
        router.action.approve(action.id)
        router.action.execute(action.id, result="fixed", success=True)
        pending = router.action.pending()
        assert len(pending) == 0

    def test_propose_next_actions(self, router):
        router.decision.log_decision("test", "reason")
        actions = router.action.propose_next_actions("test")
        assert isinstance(actions, list)


class TestStrategy:
    def test_add_and_record(self, router):
        s = router.strategy.add_strategy("debug", "QNN crash", ["check mem", "check alloc"])
        router.strategy.record_attempt(s.id, success=True, cost_minutes=2.0)
        stats = router.strategy.success_rate(s.id)
        assert stats["attempts"] == 1
        assert stats["successes"] == 1

    def test_best_for_situation(self, router):
        s = router.strategy.add_strategy("fix", "memory issue", ["step1"])
        router.strategy.record_attempt(s.id, success=True, cost_minutes=1.0)
        best = router.strategy.best_for_situation("memory issue")
        assert len(best) >= 1


class TestLearning:
    def test_record_outcome(self, router):
        s = router.strategy.add_strategy("test", "ctx", ["s1"])
        l = router.learning.record_outcome(s.id, "worked", 0.9, "always check first")
        assert l.metadata["score"] == 0.9

    def test_get_policies(self, router):
        s = router.strategy.add_strategy("test", "ctx", ["s1"])
        router.learning.record_outcome(s.id, "ok", 0.8, "learned", {"check_first": True})
        policies = router.learning.get_policies()
        assert "check_first" in policies


class TestRecovery:
    def test_failure_diagnose_retry(self, router):
        rec = router.recovery.record_failure("act_1", "OOM", hypothesis="leak")
        assert rec.metadata["status"] == "failed"
        router.recovery.diagnose(rec.id, "buffer overflow", new_hypothesis="htp issue")
        result = router.recovery.retry(rec.id)
        assert result["retrying"] is True

    def test_max_attempts_abandon(self, router):
        rec = router.recovery.record_failure("act_2", "crash")
        for _ in range(5):
            router.recovery.diagnose(rec.id, "diag", new_hypothesis="h")
            result = router.recovery.retry(rec.id)
        assert result["abandoned"] is True


class TestProactive:
    def test_should_inject(self, router):
        router.proactive.add_recent_episode_reminder(hours=1)
        router.episodic.add_memory("recent event")
        reminders = router.proactive.should_inject("test context")
        assert isinstance(reminders, list)

    def test_inject_returns_none(self, router):
        result = router.proactive.inject("empty context")
        assert result is None


class TestWorldModel:
    def test_update_and_get_state(self, router):
        router.world.update_state("temp", 65.0)
        state = router.world.get_state()
        assert state["beliefs"]["temp"]["value"] == 65.0

    def test_predict_and_observe(self, router):
        pred = router.world.predict("X causes Y", expected_result="Y happened")
        result = router.world.observe(pred.id, actual_result="Y happened")
        assert result["match"] is True

    def test_accuracy(self, router):
        p1 = router.world.predict("p1", expected_result="yes")
        router.world.observe(p1.id, actual_result="yes")
        acc = router.world.accuracy()
        assert acc["accuracy"] == 1.0


class TestConsolidation:
    def test_stats(self, router):
        router.episodic.add_memory("e1")
        router.semantic.add_fact("s1")
        stats = router.consolidation.stats()
        assert "episodic/provisional" in stats
