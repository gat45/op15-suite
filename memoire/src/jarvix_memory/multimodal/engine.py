from ..core.database import Database
from ..core.models import Memory, MemoryType
import json
import hashlib
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class ModalityType(str, Enum):
    TEXT = "text"
    CODE = "code"
    LOG = "log"
    IMAGE = "image"
    PDF = "pdf"
    VIDEO = "video"
    AUDIO = "audio"
    UI_DUMP = "ui_dump"
    BINARY = "binary"


class MultimodalEngine:
    """RAW ARTIFACT -> PERCEPTION -> STRUCTURED OBSERVATION -> MEMORY"""

    def __init__(self, db: Database, allowed_dirs: list = None):
        self.db = db
        self._perceptors = {}
        self._allowed_dirs = allowed_dirs

    def register_perceptor(self, modality: ModalityType, func):
        self._perceptors[modality.value] = func

    def _is_path_allowed(self, path: Path) -> bool:
        if self._allowed_dirs is None:
            return True
        try:
            resolved = path.resolve()
            return any(resolved.is_relative_to(d) for d in self._allowed_dirs)
        except Exception:
            return False

    def perceive_file(self, file_path: str, modality: ModalityType = None) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            return {"error": f"file not found: {file_path}"}
        if not self._is_path_allowed(path):
            logger.warning("Path traversal blocked: %s", file_path)
            return {"error": "path not in allowed directories"}

        if modality is None:
            modality = self._infer_modality(path.suffix)

        content_hash = self._hash_file(path)
        size_kb = path.stat().st_size / 1024

        perceptor = self._perceptors.get(modality.value)
        if perceptor:
            observation = perceptor(path)
        else:
            observation = self._default_perception(path, modality)

        observation.update({
            "file_path": str(path),
            "modality": modality.value,
            "content_hash": content_hash,
            "size_kb": round(size_kb, 2),
        })
        return observation

    def store_observation(
        self,
        observation: Dict[str, Any],
        source: str = None,
        confidence: float = 0.8,
    ) -> Memory:
        content = observation.get("summary", str(observation)[:500])
        meta = {
            "observation": observation,
            "source": source,
            "modality": observation.get("modality"),
            "file_path": observation.get("file_path"),
            "content_hash": observation.get("content_hash"),
        }
        memory = Memory(
            type=MemoryType.MULTIMODAL,
            content=content,
            confidence=confidence,
            source=source,
            metadata=meta,
        )
        self.db.insert_memory(memory)
        return memory

    def perceive_and_store(self, file_path: str, source: str = None) -> Memory:
        obs = self.perceive_file(file_path)
        return self.store_observation(obs, source=source)

    def find_by_hash(self, content_hash: str) -> Optional[Dict]:
        conn = self.db._connect()
        row = conn.execute(
            "SELECT * FROM memories WHERE type = 'multimodal' AND metadata LIKE ?",
            (f'%"content_hash": "{content_hash}"%',)
        ).fetchone()
        return dict(row) if row else None

    def _infer_modality(self, suffix: str) -> ModalityType:
        mapping = {
            ".py": ModalityType.CODE, ".js": ModalityType.CODE,
            ".kt": ModalityType.CODE, ".java": ModalityType.CODE,
            ".c": ModalityType.CODE, ".cpp": ModalityType.CODE,
            ".h": ModalityType.CODE, ".rs": ModalityType.CODE,
            ".log": ModalityType.LOG, ".txt": ModalityType.TEXT,
            ".md": ModalityType.TEXT,
            ".png": ModalityType.IMAGE, ".jpg": ModalityType.IMAGE,
            ".jpeg": ModalityType.IMAGE, ".gif": ModalityType.IMAGE,
            ".pdf": ModalityType.PDF,
            ".mp4": ModalityType.VIDEO, ".mkv": ModalityType.VIDEO,
            ".mp3": ModalityType.AUDIO, ".wav": ModalityType.AUDIO,
            ".xml": ModalityType.UI_DUMP, ".json": ModalityType.CODE,
        }
        return mapping.get(suffix.lower(), ModalityType.BINARY)

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    def _default_perception(self, path: Path, modality: ModalityType) -> Dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:2000]
        except Exception as e:
            logger.warning("Failed to read %s: %s", path, e)
            text = ""
        return {
            "summary": f"{modality.value} file: {path.name}",
            "text_preview": text[:500] if text else "",
            "line_count": text.count("\n") + 1 if text else 0,
        }
