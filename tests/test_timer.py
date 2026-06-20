"""Tests — TimerConnector."""


def test_timer_parse_duration():
    from aion_core.apps.timer.connector import _parse_duration
    assert _parse_duration("5m") == 300
    assert _parse_duration("1h") == 3600
    assert _parse_duration("1h30m") == 5400
    assert _parse_duration("90") == 90
    assert _parse_duration("2:30") == 150
    assert _parse_duration("invalid") is None


def test_timer_start():
    from aion_core.apps.timer.connector import TimerConnector

    class FakeMem:
        def recall(self, k): return None

    t = TimerConnector(FakeMem())
    result = t.start({"duration": "1s", "message": "Test !"})
    assert "timer" in result.lower()
    assert "demarre" in result.lower()


def test_timer_status_empty():
    from aion_core.apps.timer.connector import TimerConnector

    class FakeMem:
        def recall(self, k): return None

    t = TimerConnector(FakeMem())
    TimerConnector._timers.clear()
    result = t.status()
    assert "aucun" in result.lower()
