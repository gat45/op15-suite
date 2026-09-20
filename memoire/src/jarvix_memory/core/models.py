from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
import uuid


class MemoryStatus(str, Enum):
    PROVISIONAL = "provisional"
    VERIFIED = "verified"
    CONTRADICTED = "contradicted"
    SUPERSEDED = "superseded"
    INVALID = "invalid"
    ARCHIVED = "archived"


class MemoryType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    DECISION = "decision"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    EVIDENCE = "evidence"
    WORLD = "world"
    ERROR = "error"
    GRAPH = "graph"
    ACTION = "action"
    STRATEGY = "strategy"
    LEARNING = "learning"
    RECOVERY = "recovery"
    PROACTIVE = "proactive"
    MULTIMODAL = "multimodal"
    ENVIRONMENT = "environment"


class MemoryCost(BaseModel):
    ram_mb: float = 0.0
    cpu_ms: float = 0.0
    tokens: int = 0
    storage_kb: float = 0.0


class Memory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: MemoryType
    status: MemoryStatus = MemoryStatus.PROVISIONAL
    content: str

    created_at: datetime = Field(default_factory=datetime.utcnow)
    observed_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None

    source: Optional[str] = None
    source_trust: float = 1.0
    confidence: float = 1.0
    importance: float = 0.5
    utility: float = 0.0

    agent_id: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    environment_id: Optional[str] = None

    metadata: Dict[str, Any] = Field(default_factory=dict)
    relations: List[Dict[str, Any]] = Field(default_factory=list)
    provenance_chain: List[str] = Field(default_factory=list)

    cost: MemoryCost = Field(default_factory=MemoryCost)
    embedding: Optional[List[float]] = None

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
