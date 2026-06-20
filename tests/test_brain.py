"""Tests — AionBrain."""
import os
import pytest


def test_brain_init():
    from aion_core.ai.brain import AionBrain
    brain = AionBrain()
    assert brain.model is not None
    assert isinstance(brain.history, list)


def test_brain_no_key():
    """Sans clé API → réponse d erreur propre."""
    from aion_core.ai.brain import AionBrain
    brain = AionBrain()
    brain.api_key = ""
    result = brain.think("test")
    assert "GROQ_API_KEY" in result


def test_parse_json_valid():
    from aion_core.ai.brain import AionBrain
    brain = AionBrain()
    resp = '{"action": "test", "params": {}}\`\``json
{"action": "test"}
\`\`\`'
    # Test avec bloc ```json
    raw = '```json\n{"app": "quickmind"}\n```'
    result = brain.parse_json_response(raw)
    assert result == {"app": "quickmind"}


def test_parse_json_invalid():
    from aion_core.ai.brain import AionBrain
    brain = AionBrain()
    result = brain.parse_json_response("texte non JSON")
    assert result is None
