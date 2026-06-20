"""
MemoryManager — Mémoire persistante AION-Core.
Stockage JSON + mémoire temporaire session.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_FILE = Path(__file__).parent.parent.parent / "data" / "memory.json"


class MemoryManager:
    """Gestion de la mémoire persistante et temporaire."""

    def __init__(self, memory_file: Path | None = None) -> None:
        self.memory_file    = memory_file or MEMORY_FILE
        self.temp: dict[str, Any] = {}
        self.persistent     = self._load()
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if self.memory_file.exists():
            try:
                with open(self.memory_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self) -> None:
        with open(self.memory_file, "w", encoding="utf-8") as f:
            json.dump(self.persistent, f, indent=2, ensure_ascii=False)

    def remember(self, key: str, value: str, memory_type: str = "info") -> None:
        self.persistent[key] = {
            "value":      value,
            "type":       memory_type,
            "created_at": self.persistent.get(key, {}).get("created_at", datetime.now().isoformat()),
            "updated_at": datetime.now().isoformat(),
        }
        self._save()

    def recall(self, key: str) -> str | None:
        item = self.persistent.get(key)
        return item["value"] if item else None

    def forget(self, key: str) -> bool:
        if key in self.persistent:
            del self.persistent[key]
            self._save()
            return True
        return False

    def list_memory(self, memory_type: str | None = None) -> dict:
        if memory_type is None:
            return self.persistent
        return {k: v for k, v in self.persistent.items() if v.get("type") == memory_type}

    def remember_temp(self, key: str, value: Any) -> None:
        self.temp[key] = value

    def recall_temp(self, key: str) -> Any:
        return self.temp.get(key)

    def stats(self) -> dict:
        by_type: dict[str, int] = {}
        for item in self.persistent.values():
            t = item.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total":          len(self.persistent),
            "temporary_total": len(self.temp),
            "by_type":        by_type,
        }
