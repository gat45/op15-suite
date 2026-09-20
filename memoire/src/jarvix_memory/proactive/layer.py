from ..core.database import Database
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import uuid

logger = logging.getLogger(__name__)


class ProactiveMemory:
    """CURRENT STATE -> MEMORY POLICY -> 'this memory is important now' -> REMINDER"""

    def __init__(self, db: Database):
        self.db = db
        self._load_rules()

    def _load_rules(self):
        """Load rules from database into memory."""
        conn = self.db._connect()
        rows = conn.execute("SELECT * FROM proactive_rules WHERE enabled = 1").fetchall()
        self._rules = [dict(row) for row in rows]

    def add_rule(
        self,
        name: str,
        trigger_condition: str,
        memory_type: str = None,
        max_age_hours: int = 24,
        min_importance: float = 0.5,
        priority: int = 5,
    ) -> Dict[str, Any]:
        rule_id = str(uuid.uuid4())
        rule = {
            "id": rule_id,
            "name": name,
            "trigger_condition": trigger_condition,
            "memory_type": memory_type,
            "max_age_hours": max_age_hours,
            "min_importance": min_importance,
            "priority": priority,
            "enabled": 1,
            "created_at": datetime.utcnow().isoformat(),
        }
        conn = self.db._connect()
        conn.execute(
            "INSERT INTO proactive_rules (id, name, trigger_condition, memory_type, "
            "max_age_hours, min_importance, priority, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rule_id, name, trigger_condition, memory_type,
             max_age_hours, min_importance, priority, 1, rule["created_at"]),
        )
        conn.commit()
        self._rules.append(rule)
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        conn = self.db._connect()
        conn.execute("DELETE FROM proactive_rules WHERE id = ?", (rule_id,))
        conn.commit()
        self._rules = [r for r in self._rules if r["id"] != rule_id]
        return True

    def list_rules(self) -> List[Dict[str, Any]]:
        return list(self._rules)

    def should_inject(self, current_context: str) -> List[Dict[str, Any]]:
        reminders = []
        for rule in self._rules:
            candidates = self._find_matching(rule, current_context)
            for c in candidates:
                reminders.append({
                    "memory": c,
                    "rule": rule["name"],
                    "priority": rule["priority"],
                    "reason": rule["trigger_condition"],
                })
        reminders.sort(key=lambda r: r["priority"], reverse=True)
        return reminders[:5]

    def inject(self, current_context: str) -> Optional[str]:
        reminders = self.should_inject(current_context)
        if not reminders:
            return None
        best = reminders[0]
        mem = best["memory"]
        return f"[Reminder: {best['rule']}] {mem.get('content', '')[:200]}"

    def add_recent_episode_reminder(self, hours: int = 2, min_importance: float = 0.6):
        self.add_rule(
            name="recent_episode",
            trigger_condition="recent event relevant to current task",
            memory_type="episodic",
            max_age_hours=hours,
            min_importance=min_importance,
            priority=6,
        )

    def add_unresolved_error_reminder(self):
        self.add_rule(
            name="unresolved_error",
            trigger_condition="active error or failure in context",
            memory_type="error",
            max_age_hours=72,
            min_importance=0.4,
            priority=8,
        )

    def add_hypothesis_reminder(self):
        self.add_rule(
            name="pending_hypothesis",
            trigger_condition="untested hypothesis matching context",
            memory_type="hypothesis",
            max_age_hours=48,
            min_importance=0.5,
            priority=7,
        )

    def _find_matching(self, rule: Dict[str, Any], context: str) -> List[Dict]:
        memory_type = rule.get("memory_type")
        if memory_type:
            rows = self.db.search_by_type(memory_type, limit=20)
        else:
            rows = self.db.search_fts(context, limit=20)

        cutoff = datetime.utcnow() - timedelta(hours=rule.get("max_age_hours", 24))
        matches = []
        for r in rows:
            meta = json.loads(r.get("metadata", "{}"))
            importance = r.get("importance", 0.5) or meta.get("importance", 0.5)
            if importance < rule.get("min_importance", 0.5):
                continue
            created = r.get("created_at", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    if dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            matches.append(r)
        return matches

    def stats(self) -> Dict[str, Any]:
        return {
            "rules": len(self._rules),
            "rule_names": [r["name"] for r in self._rules],
        }

    def monitor(self, context: str, experiment_tracker=None, recovery_layer=None,
                max_reminders: int = 3) -> Dict[str, Any]:
        """P1.7 — selective injection: should this context get a memory RIGHT NOW?
        Combines: rules matching + refuted-experiment warnings + active recoveries.
        Silence is the default — only warn when it matters."""
        # 1. Rule-based reminders (quiet unless matched)
        rule_reminders = []
        try:
            rule_reminders = self.should_inject(context)
        except Exception as e:
            logger.warning("proactive rules failed: %s", e)
        # 2. Experiment guard: is the user about to redo a refuted path?
        guard = None
        if experiment_tracker:
            guard = experiment_tracker.repeat_guard(context)
        # 3. Active recoveries related to context
        recoveries = []
        if recovery_layer and context.strip():
            words = [w for w in context.lower().split() if len(w) > 2]
            try:
                for r in recovery_layer.active_recoveries():
                    hay = (r.get("content", "") + " " + (r.get("metadata", "") or "")).lower()
                    if any(w in hay for w in words):
                        recoveries.append(r)
            except Exception:
                pass
        if recoveries and rule_reminders:
            recoveries = recoveries[:1]
        return {
            "inject": rule_reminders[:max_reminders],
            "refuted_path_warning": guard["refuted_paths"][:max_reminders] if guard and guard["blocked"] else [],
            "active_failures": recoveries[:max_reminders],
            "silent": not (rule_reminders or (guard and guard["blocked"]) or recoveries),
        }
