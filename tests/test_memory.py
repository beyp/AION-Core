"""Tests — MemoryManager."""
import pytest
from pathlib import Path
import tempfile


@pytest.fixture
def tmp_memory():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)
    from aion_core.memory.manager import MemoryManager
    m = MemoryManager(memory_file=tmp)
    yield m
    tmp.unlink(missing_ok=True)


def test_remember_recall(tmp_memory):
    tmp_memory.remember("host", "192.168.1.1", "network")
    assert tmp_memory.recall("host") == "192.168.1.1"


def test_forget(tmp_memory):
    tmp_memory.remember("key", "value")
    assert tmp_memory.forget("key") is True
    assert tmp_memory.recall("key") is None


def test_forget_missing(tmp_memory):
    assert tmp_memory.forget("ghost") is False


def test_list_by_type(tmp_memory):
    tmp_memory.remember("k1", "v1", "path")
    tmp_memory.remember("k2", "v2", "info")
    paths = tmp_memory.list_memory("path")
    assert "k1" in paths
    assert "k2" not in paths


def test_temp_memory(tmp_memory):
    tmp_memory.remember_temp("session_key", "abc123")
    assert tmp_memory.recall_temp("session_key") == "abc123"
    assert tmp_memory.recall_temp("missing") is None


def test_stats(tmp_memory):
    tmp_memory.remember("a", "1", "info")
    tmp_memory.remember("b", "2", "path")
    tmp_memory.remember_temp("t", "tmp")
    stats = tmp_memory.stats()
    assert stats["total"] == 2
    assert stats["temporary_total"] == 1
    assert stats["by_type"]["info"] == 1
