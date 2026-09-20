# Inventaire complet (auto-genere)

CLASS ActionMemory  (jarvix_memory.action.layer)
    (module jarvix_memory.action.layer)
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def approve(self, action_id: str) -> bool
    def count(self) -> int
    def execute(self, action_id: str, result: str = None, success: bool = True) -> bool
    def get(self, memory_id: str) -> dict | None
    def history(self, limit: int = 20) -> List[Dict]
    def list_all(self, limit: int = 50) -> List[dict]
    def pending(self) -> List[Dict]
    def propose(self, description: str, based_on: List[str] = None, priority: int = 5, metadata: Dict[str, Any] = None) -> jarvix_memory.core.models.Memory
    def propose_next_actions(self, context: str, limit: int = 5) -> List[Dict]
    def search(self, query: str, limit: int = 20) -> List[dict]
    def skip(self, action_id: str, reason: str = None) -> bool
CLASS ActionStatus  (jarvix_memory.action.layer)
CLASS ConsolidationService  (jarvix_memory.consolidation.service)
    (module jarvix_memory.consolidation.service)
    def archive_old_provisional(self, max_age_days: int = 30)
    def archive_stale_actions(self, max_age_hours: int = 72, max_utility: float = 0.2) -> int
    def decay_importance(self, decay_factor: float = 0.95, min_importance: float = 0.1)
    def merge_episodic_to_semantic(self, min_repeat: int = 3)
    def run_sleep_cycle(self)
    def start_scheduler(self, interval_hours: float = 6.0)
    def stats(self) -> dict
    def stop_scheduler(self)
FN    autolog_dir  (jarvix_memory.core.autopush)
FN    export_project  (jarvix_memory.core.autopush)
FN    push_project  (jarvix_memory.core.autopush)
FN    cost_report  (jarvix_memory.core.cost)
FN    estimate_cost  (jarvix_memory.core.cost)
FN    record_usage  (jarvix_memory.core.cost)
FN    rerank  (jarvix_memory.core.cost)
FN    score  (jarvix_memory.core.cost)
CLASS Database  (jarvix_memory.core.database)
    (module jarvix_memory.core.database)
    def _connect(self) -> sqlite3.Connection
    def _init_db(self)
    def close(self)
    def count(self, memory_type: str | None = None) -> int
    def delete_memory(self, memory_id: str) -> bool
    def get_memory(self, memory_id: str) -> Dict | None
    def insert_memory(self, memory: jarvix_memory.core.models.Memory) -> None
    def list_all(self, limit: int = 100) -> List[Dict]
    def recall_cost_aware(self, query: str, limit: int = 10, budget_tokens: int = None, min_value: float = 0.0005, abstain_below: float = 0.35) -> List[Dict]
    def record_usage(self, memory_id: str, used: bool = True) -> bool
    def search_by_type(self, memory_type: str, limit: int = 50) -> List[Dict]
    def search_fts(self, query: str, limit: int = 50) -> List[Dict]
    def search_hybrid(self, query: str, limit: int = 10) -> List[Dict]
    def search_vector(self, query: str, limit: int = 10, min_score: float = 0.2) -> List[Dict]
    def update_memory(self, memory_id: str, **fields) -> bool
CLASS EnvironmentStore  (jarvix_memory.core.environment)
    (module jarvix_memory.core.environment)
    def capture(self, extra: Dict = None) -> Dict
    def diff(self, env_a: str, env_b: str) -> Dict
    def get(self, env_id: str) -> Dict | None
FN    get_scan_roots  (jarvix_memory.core.ingest)
FN    ingest_directory  (jarvix_memory.core.ingest)
FN    scan_directory  (jarvix_memory.core.ingest)
CLASS MemoryLayer  (jarvix_memory.core.layer)
    (module jarvix_memory.core.layer)
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def count(self) -> int
    def get(self, memory_id: str) -> dict | None
    def list_all(self, limit: int = 50) -> List[dict]
    def search(self, query: str, limit: int = 20) -> List[dict]
CLASS LiveContext  (jarvix_memory.core.livectl)
    (module jarvix_memory.core.livectl)
    def bundle(self, query: str = '', max_tokens: int = 4000) -> Dict
    def interval_s(self) -> int
    def start_watch(self) -> bool
    def stop_watch(self) -> bool
FN    get_version  (jarvix_memory.core.migration)
FN    migrate  (jarvix_memory.core.migration)
FN    run_migrations  (jarvix_memory.core.migration)
FN    set_version  (jarvix_memory.core.migration)
CLASS Memory  (jarvix_memory.core.models)
    (module jarvix_memory.core.models)
    def copy(self, *, include: 'AbstractSetIntStr | MappingIntStrAny | None' = None, exclude: 'AbstractSetIntStr | MappingIntStrAny | None' = None, update: 'Dict[str, Any] | None' = None, deep: 'bool' = False) -> 'Self'
    def dict(self, *, include: 'IncEx | None' = None, exclude: 'IncEx | None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'
    def json(self, *, include: 'IncEx | None' = None, exclude: 'IncEx | None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] | None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'
    def model_copy(self, *, update: 'Mapping[str, Any] | None' = None, deep: 'bool' = False) -> 'Self'
    def model_dump(self, *, mode: "Literal['json', 'python'] | str" = 'python', include: 'IncEx | None' = None, exclude: 'IncEx | None' = None, context: 'Any | None' = None, by_alias: 'bool | None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool | Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] | None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'
    def model_dump_json(self, *, indent: 'int | None' = None, ensure_ascii: 'bool' = False, include: 'IncEx | None' = None, exclude: 'IncEx | None' = None, context: 'Any | None' = None, by_alias: 'bool | None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool | Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] | None' = None, serialize_as_any: 'bool' = False) -> 'str'
    def model_post_init(self, context: 'Any', /) -> 'None'
CLASS MemoryCost  (jarvix_memory.core.models)
    (module jarvix_memory.core.models)
    def copy(self, *, include: 'AbstractSetIntStr | MappingIntStrAny | None' = None, exclude: 'AbstractSetIntStr | MappingIntStrAny | None' = None, update: 'Dict[str, Any] | None' = None, deep: 'bool' = False) -> 'Self'
    def dict(self, *, include: 'IncEx | None' = None, exclude: 'IncEx | None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False) -> 'Dict[str, Any]'
    def json(self, *, include: 'IncEx | None' = None, exclude: 'IncEx | None' = None, by_alias: 'bool' = False, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, encoder: 'Callable[[Any], Any] | None' = PydanticUndefined, models_as_dict: 'bool' = PydanticUndefined, **dumps_kwargs: 'Any') -> 'str'
    def model_copy(self, *, update: 'Mapping[str, Any] | None' = None, deep: 'bool' = False) -> 'Self'
    def model_dump(self, *, mode: "Literal['json', 'python'] | str" = 'python', include: 'IncEx | None' = None, exclude: 'IncEx | None' = None, context: 'Any | None' = None, by_alias: 'bool | None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool | Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] | None' = None, serialize_as_any: 'bool' = False) -> 'dict[str, Any]'
    def model_dump_json(self, *, indent: 'int | None' = None, ensure_ascii: 'bool' = False, include: 'IncEx | None' = None, exclude: 'IncEx | None' = None, context: 'Any | None' = None, by_alias: 'bool | None' = None, exclude_unset: 'bool' = False, exclude_defaults: 'bool' = False, exclude_none: 'bool' = False, exclude_computed_fields: 'bool' = False, round_trip: 'bool' = False, warnings: "bool | Literal['none', 'warn', 'error']" = True, fallback: 'Callable[[Any], Any] | None' = None, serialize_as_any: 'bool' = False) -> 'str'
    def model_post_init(self, context: 'Any', /) -> 'None'
CLASS MemoryStatus  (jarvix_memory.core.models)
CLASS MemoryType  (jarvix_memory.core.models)
CLASS VectorStore  (jarvix_memory.core.vector_store)
    (module jarvix_memory.core.vector_store)
    def embed_and_store(self, memory_id: str, text: str) -> None
    def embed_batch(self, items: List[Tuple[str, str]]) -> int
    def rebuild(self) -> int
    def search(self, query: str, limit: int = 10, min_score: float = 0.0) -> List[Dict]
    def stats(self) -> Dict
    def warm(self) -> bool
CLASS DecisionProvider  (jarvix_memory.decision.jev)
    (module jarvix_memory.decision.jev)
    def filter(self, memory: Dict, context: str) -> Dict
    def gate(self, action: str, destructive_priority: float = 0.85) -> Dict
    def route(self, query: str) -> Dict
    def score(self, grid: Dict) -> Dict
    def verify(self, claim: str, evidence_stats: Dict) -> Dict
CLASS JEV  (jarvix_memory.decision.jev)
    (module jarvix_memory.decision.jev)
    def decide(self, context: str, options: List[str]) -> Dict
    def filter(self, memory: Dict, context: str, max_tokens: int = None, log: bool = False) -> Dict
    def gate(self, action: str, destructive_threshold: float = 0.85, log: bool = True) -> Dict
    def log_decision(self, kind: str, subject: str, result: Dict)
    def route(self, query: str, log: bool = True) -> Dict
    def score(self, grid: Dict, subject: str = None, log: bool = True) -> Dict
    def verify(self, claim: str, evidence_stats: Dict, log: bool = True) -> Dict
CLASS RuleBasedProvider  (jarvix_memory.decision.jev)
    (module jarvix_memory.decision.jev)
    def filter(self, memory: Dict, context: str, max_tokens: int = None) -> Dict
    def gate(self, action: str, destructive_threshold: float = 0.85) -> Dict
    def route(self, query: str) -> Dict
    def score(self, grid: Dict) -> Dict
    def verify(self, claim: str, evidence_stats: Dict) -> Dict
CLASS JevRemoteProvider  (jarvix_memory.decision.jev_remote)
    (module jarvix_memory.decision.jev_remote)
    def _request(self, state, questions: Dict, retries: int = 2) -> Dict
    def decide(self, context: str, options: list) -> Dict
    def filter(self, memory: Dict, context: str, max_tokens: int = None) -> Dict
    def gate(self, action: str, destructive_threshold: float = 0.85) -> Dict
    def route(self, query: str) -> Dict
    def score(self, grid: Dict) -> Dict
    def status(self) -> Dict
    def verify(self, claim: str, evidence_stats: Dict) -> Dict
CLASS DecisionMemory  (jarvix_memory.decision.layer)
    (module jarvix_memory.decision.layer)
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def count(self) -> int
    def get(self, memory_id: str) -> dict | None
    def list_all(self, limit: int = 50) -> List[dict]
    def log_decision(self, decision: str, reasoning: str, alternatives: list = None, **kwargs) -> 'Memory'
    def recent_decisions(self, limit: int = 10) -> List[dict]
    def search(self, query: str, limit: int = 20) -> List[dict]
CLASS EpisodicMemory  (jarvix_memory.episodic.layer)
    (module jarvix_memory.episodic.layer)
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def count(self) -> int
    def get(self, memory_id: str) -> dict | None
    def list_all(self, limit: int = 50) -> List[dict]
    def log_event(self, action: str, result: str, metadata: dict = None, **kwargs) -> 'Memory'
    def recent(self, limit: int = 10) -> List[dict]
    def search(self, query: str, limit: int = 20) -> List[dict]
CLASS ExperimentTracker  (jarvix_memory.experiment.tracker)
    (module jarvix_memory.experiment.tracker)
    def conclude(self, hyp_id: str, verdict: str) -> Dict
    def pending_hypotheses(self, limit: int = 20) -> List[Dict]
    def propose_hypothesis(self, statement: str, env_id: str | None = None, rationale: str = None) -> Dict
    def repeat_guard(self, statement: str, limit: int = 5) -> Dict
    def run_experiment(self, hyp_id: str, name: str, result: str, success: bool, env_id: str | None = None, measurements: Dict = None) -> Dict
CLASS GraphMemory  (jarvix_memory.graph.layer)
    (module jarvix_memory.graph.layer)
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def add_relation(self, subject: str, predicate: str, obj: str, metadata: Dict[str, Any] = None) -> 'Memory'
    def count(self) -> int
    def get(self, memory_id: str) -> dict | None
    def get_by_predicate(self, predicate: str) -> List[Dict]
    def get_relations_for_entity(self, entity: str) -> List[Dict]
    def list_all(self, limit: int = 50) -> List[dict]
    def search(self, query: str, limit: int = 20) -> List[dict]
CLASS LearningLayer  (jarvix_memory.learning.layer)
    (module jarvix_memory.learning.layer)
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def count(self) -> int
    def get(self, memory_id: str) -> dict | None
    def get_learnings(self, context: str, limit: int = 10) -> List[Dict]
    def get_policies(self) -> Dict[str, Any]
    def list_all(self, limit: int = 50) -> List[dict]
    def record_outcome(self, experience_id: str, evaluation: str, score: float, what_was_learned: str, policy_update: Dict[str, Any] = None) -> jarvix_memory.core.models.Memory
    def search(self, query: str, limit: int = 20) -> List[dict]
    def should_abandon(self, strategy_id: str, threshold: float = 0.3) -> Dict[str, Any]
CLASS LLMReasoner  (jarvix_memory.llm.reasoner)
    (module jarvix_memory.llm.reasoner)
    def find_connections(self, memory_id: str) -> Dict
    def health(self) -> Dict
    def reason(self, query: str, max_tokens: int = 1024, temperature: float = 0.3, live_max_tokens: int = 1200) -> Dict
    def summarize(self, text: str, max_tokens: int = 256) -> str
FN    main  (jarvix_memory.main)
CLASS ModalityType  (jarvix_memory.multimodal.engine)
CLASS MultimodalEngine  (jarvix_memory.multimodal.engine)
    (module jarvix_memory.multimodal.engine)
    def find_by_hash(self, content_hash: str) -> Dict | None
    def perceive_and_store(self, file_path: str, source: str = None) -> jarvix_memory.core.models.Memory
    def perceive_file(self, file_path: str, modality: jarvix_memory.multimodal.engine.ModalityType = None) -> Dict[str, Any]
    def register_perceptor(self, modality: jarvix_memory.multimodal.engine.ModalityType, func)
    def store_observation(self, observation: Dict[str, Any], source: str = None, confidence: float = 0.8) -> jarvix_memory.core.models.Memory
CLASS PerceptionEngine  (jarvix_memory.multimodal.perception)
    (module jarvix_memory.multimodal.perception)
    def perceive(self, path: str, note: str = None) -> Dict
CLASS ProactiveMemory  (jarvix_memory.proactive.layer)
    (module jarvix_memory.proactive.layer)
    def add_hypothesis_reminder(self)
    def add_recent_episode_reminder(self, hours: int = 2, min_importance: float = 0.6)
    def add_rule(self, name: str, trigger_condition: str, memory_type: str = None, max_age_hours: int = 24, min_importance: float = 0.5, priority: int = 5) -> Dict[str, Any]
    def add_unresolved_error_reminder(self)
    def inject(self, current_context: str) -> str | None
    def list_rules(self) -> List[Dict[str, Any]]
    def monitor(self, context: str, experiment_tracker=None, recovery_layer=None, max_reminders: int = 3) -> Dict[str, Any]
    def remove_rule(self, rule_id: str) -> bool
    def should_inject(self, current_context: str) -> List[Dict[str, Any]]
    def stats(self) -> Dict[str, Any]
CLASS ProceduralMemory  (jarvix_memory.procedural.layer)
    (module jarvix_memory.procedural.layer)
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def add_skill(self, name: str, procedure: str, success_rate: float = 1.0, **kwargs) -> 'Memory'
    def count(self) -> int
    def get(self, memory_id: str) -> dict | None
    def get_skill(self, name: str) -> dict
    def list_all(self, limit: int = 50) -> List[dict]
    def search(self, query: str, limit: int = 20) -> List[dict]
CLASS RecoveryLayer  (jarvix_memory.recovery.layer)
    (module jarvix_memory.recovery.layer)
    def active_recoveries(self) -> List[Dict]
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def count(self) -> int
    def diagnose(self, recovery_id: str, diagnosis: str, new_hypothesis: str = None) -> Dict[str, Any]
    def get(self, memory_id: str) -> dict | None
    def list_all(self, limit: int = 50) -> List[dict]
    def mark_recovered(self, recovery_id: str) -> bool
    def record_failure(self, action_id: str, error: str, hypothesis: str = None, metadata: Dict[str, Any] = None) -> jarvix_memory.core.models.Memory
    def recovery_history(self, limit: int = 20) -> List[Dict]
    def retry(self, recovery_id: str) -> Dict[str, Any]
    def search(self, query: str, limit: int = 20) -> List[dict]
CLASS RecoveryStatus  (jarvix_memory.recovery.layer)
CLASS MemoryRouter  (jarvix_memory.router)
    (module jarvix_memory.router)
    def query(self, text: str, limit: int = 10)
    def stats(self) -> dict
CLASS SemanticMemory  (jarvix_memory.semantic.layer)
    (module jarvix_memory.semantic.layer)
    def add_fact(self, fact: str, confidence: float = 1.0, source: str = None, **kwargs) -> 'Memory'
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def count(self) -> int
    def get(self, memory_id: str) -> dict | None
    def get_facts(self, min_confidence: float = 0.5) -> List[dict]
    def list_all(self, limit: int = 50) -> List[dict]
    def search(self, query: str, limit: int = 20) -> List[dict]
CLASS StrategyMemory  (jarvix_memory.strategy.layer)
    (module jarvix_memory.strategy.layer)
    def add_memory(self, content: str, **kwargs) -> jarvix_memory.core.models.Memory
    def add_strategy(self, name: str, situation: str, steps: List[str], rationale: str = None, metadata: Dict[str, Any] = None) -> jarvix_memory.core.models.Memory
    def best_for_situation(self, situation: str, limit: int = 3) -> List[Dict]
    def count(self) -> int
    def get(self, memory_id: str) -> dict | None
    def leaderboard(self, limit: int = 10) -> List[Dict]
    def list_all(self, limit: int = 50) -> List[dict]
    def recommend(self, situation: str, min_samples: int = 1, cost_weight: float = 0.2, limit: int = 3) -> List[Dict]
    def record_attempt(self, strategy_id: str, success: bool, cost_minutes: float = 0.0) -> bool
    def search(self, query: str, limit: int = 20) -> List[dict]
    def success_rate(self, strategy_id: str) -> Dict[str, Any]
FN    api_action_approve  (jarvix_memory.ui.app)
FN    api_action_execute  (jarvix_memory.ui.app)
FN    api_action_propose  (jarvix_memory.ui.app)
FN    api_actions_history  (jarvix_memory.ui.app)
FN    api_actions_pending  (jarvix_memory.ui.app)
FN    api_add_memory  (jarvix_memory.ui.app)
FN    api_autopush  (jarvix_memory.ui.app)
FN    api_bilan  (jarvix_memory.ui.app)
FN    api_claim_resolve  (jarvix_memory.ui.app)
FN    api_claims  (jarvix_memory.ui.app)
FN    api_config_get  (jarvix_memory.ui.app)
FN    api_config_set  (jarvix_memory.ui.app)
FN    api_consolidation  (jarvix_memory.ui.app)
FN    api_consolidation_stats  (jarvix_memory.ui.app)
FN    api_delete_memory  (jarvix_memory.ui.app)
FN    api_device  (jarvix_memory.ui.app)
FN    api_fs_important  (jarvix_memory.ui.app)
FN    api_fs_list  (jarvix_memory.ui.app)
FN    api_fs_view  (jarvix_memory.ui.app)
FN    api_get_memory  (jarvix_memory.ui.app)
FN    api_graph  (jarvix_memory.ui.app)
FN    api_graph_add  (jarvix_memory.ui.app)
FN    api_health  (jarvix_memory.ui.app)
FN    api_lab_env_capture  (jarvix_memory.ui.app)
FN    api_lab_hyp_conclude  (jarvix_memory.ui.app)
FN    api_lab_hyp_guard  (jarvix_memory.ui.app)
FN    api_lab_hyp_pending  (jarvix_memory.ui.app)
FN    api_lab_hyp_propose  (jarvix_memory.ui.app)
FN    api_lab_hyp_run  (jarvix_memory.ui.app)
FN    api_lab_jev_decide  (jarvix_memory.ui.app)
FN    api_lab_jev_gate  (jarvix_memory.ui.app)
FN    api_lab_jev_route  (jarvix_memory.ui.app)
FN    api_lab_jev_score  (jarvix_memory.ui.app)
FN    api_lab_perceive  (jarvix_memory.ui.app)
FN    api_lab_quant_calibration  (jarvix_memory.ui.app)
FN    api_lab_quant_observe  (jarvix_memory.ui.app)
FN    api_lab_quant_predict  (jarvix_memory.ui.app)
FN    api_lab_verify_auto  (jarvix_memory.ui.app)
FN    api_layers  (jarvix_memory.ui.app)
FN    api_live  (jarvix_memory.ui.app)
FN    api_live_watch  (jarvix_memory.ui.app)
FN    api_llama_log  (jarvix_memory.ui.app)
FN    api_llama_models  (jarvix_memory.ui.app)
FN    api_llama_scan  (jarvix_memory.ui.app)
FN    api_llama_start  (jarvix_memory.ui.app)
FN    api_llama_status  (jarvix_memory.ui.app)
FN    api_llama_stop  (jarvix_memory.ui.app)
FN    api_memories  (jarvix_memory.ui.app)
FN    api_reason  (jarvix_memory.ui.app)
FN    api_rebuild  (jarvix_memory.ui.app)
FN    api_recovery_active  (jarvix_memory.ui.app)
FN    api_rules  (jarvix_memory.ui.app)
FN    api_rules_add  (jarvix_memory.ui.app)
FN    api_rules_del  (jarvix_memory.ui.app)
FN    api_search  (jarvix_memory.ui.app)
FN    api_strategies  (jarvix_memory.ui.app)
FN    api_strategy_attempt  (jarvix_memory.ui.app)
FN    api_update_memory  (jarvix_memory.ui.app)
FN    api_world_beliefs  (jarvix_memory.ui.app)
FN    api_world_predictions  (jarvix_memory.ui.app)
FN    index  (jarvix_memory.ui.app)
FN    save_config  (jarvix_memory.ui.app)
FN    scan_gguf_dirs  (jarvix_memory.ui.app)
FN    set_cfg  (jarvix_memory.ui.app)
CLASS AutoVerifier  (jarvix_memory.verification.auto_verify)
    (module jarvix_memory.verification.auto_verify)
    def verify_auto(self, claim_id: str, checks: List[Dict], auto_resolve: bool = True) -> Dict
CLASS CheckError  (jarvix_memory.verification.auto_verify)
FN    check_command  (jarvix_memory.verification.auto_verify)
FN    check_file_contains  (jarvix_memory.verification.auto_verify)
FN    check_file_exists  (jarvix_memory.verification.auto_verify)
FN    check_git_diff  (jarvix_memory.verification.auto_verify)
FN    check_measurement  (jarvix_memory.verification.auto_verify)
CLASS VerificationEngine  (jarvix_memory.verification.engine)
    (module jarvix_memory.verification.engine)
    def add_evidence(self, claim_id: str, evidence_type: str, description: str, passed: bool, details: Dict[str, Any] = None) -> Dict | None
    def claim(self, content: str, source: str = None, metadata: Dict[str, Any] = None) -> jarvix_memory.core.models.Memory
    def get_claims(self, verdict: str = None, limit: int = 20) -> List[Dict]
    def resolve(self, claim_id: str) -> Dict[str, Any]
    def verified_count(self) -> int
CLASS WorldModel  (jarvix_memory.world.model)
    (module jarvix_memory.world.model)
    def accuracy(self, limit: int = 50) -> Dict[str, Any]
    def calibration(self, limit: int = 100) -> Dict[str, Any]
    def get_beliefs(self) -> Dict[str, Any]
    def get_predictions(self, status: str = 'pending', limit: int = 20) -> List[Dict]
    def get_state(self) -> Dict[str, Any]
    def observe(self, prediction_id: str, actual_result: Any, actual_cost: Dict[str, float] = None) -> Dict[str, Any]
    def observe_quant(self, prediction_id: str, actual: float, env_id: str = None) -> Dict[str, Any]
    def predict(self, hypothesis: str, expected_result: Any = None, expected_cost: Dict[str, float] = None, expected_risk: float = 0.0) -> jarvix_memory.core.models.Memory
    def predict_quant(self, key: str, range_min: float, range_max: float, env_id: str = None, hypothesis: str = None) -> jarvix_memory.core.models.Memory
    def update_state(self, key: str, value: Any, confidence: float = 0.8) -> jarvix_memory.core.models.Memory
FN    abs_error_safe  (jarvix_memory.world.model)

---
**Classes: 36 | Fonctions/modes publics: 288**
