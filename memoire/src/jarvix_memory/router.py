from .core.database import Database
from .episodic.layer import EpisodicMemory
from .semantic.layer import SemanticMemory
from .procedural.layer import ProceduralMemory
from .decision.layer import DecisionMemory
from .graph.layer import GraphMemory
from .verification.engine import VerificationEngine
from .action.layer import ActionMemory
from .strategy.layer import StrategyMemory
from .learning.layer import LearningLayer
from .recovery.layer import RecoveryLayer
from .proactive.layer import ProactiveMemory
from .multimodal.engine import MultimodalEngine
from .world.model import WorldModel
from .consolidation.service import ConsolidationService
from .verification.auto_verify import AutoVerifier
from .core.environment import EnvironmentStore
from .experiment.tracker import ExperimentTracker
from .multimodal.perception import PerceptionEngine
from .decision.jev import JEV
from .core.livectl import LiveContext


class MemoryRouter:
    def __init__(self, db_path: str = "jarvix_memory.db"):
        self.db = Database(db_path)

        self.episodic = EpisodicMemory(self.db)
        self.semantic = SemanticMemory(self.db)
        self.procedural = ProceduralMemory(self.db)
        self.decision = DecisionMemory(self.db)
        self.graph = GraphMemory(self.db)

        self.verification = VerificationEngine(self.db)
        self.auto_verify = AutoVerifier(self.verification)
        self.environment = EnvironmentStore(self.db)
        self.experiment = ExperimentTracker(self.db)
        self.perception = PerceptionEngine(self.db)
        self.jev = JEV(self.db)
        self.live = LiveContext(self.db)
        self.action = ActionMemory(self.db)
        self.strategy = StrategyMemory(self.db)
        self.learning = LearningLayer(self.db)
        self.recovery = RecoveryLayer(self.db)
        self.proactive = ProactiveMemory(self.db)
        self.multimodal = MultimodalEngine(self.db)
        self.world = WorldModel(self.db)
        self.consolidation = ConsolidationService(self.db)

    def query(self, text: str, limit: int = 10):
        return self.db.search_fts(text)[:limit]

    def stats(self) -> dict:
        return {
            "total_memories": self.db.count(),
            "episodic": self.db.count("episodic"),
            "semantic": self.db.count("semantic"),
            "procedural": self.db.count("procedural"),
            "decision": self.db.count("decision"),
            "graph": self.db.count("graph"),
            "evidence": self.db.count("evidence"),
            "action": self.db.count("action"),
            "strategy": self.db.count("strategy"),
            "learning": self.db.count("learning"),
            "recovery": self.db.count("recovery"),
            "world": self.db.count("world"),
            "multimodal": self.db.count("multimodal"),
        }
