"""Timer Connector — Compte à rebours avec notification."""
import logging
import re
import threading
import time

logger = logging.getLogger(__name__)


def _parse_duration(raw: str) -> int | None:
    raw = raw.strip().lower().replace(" ", "")
    if ":" in raw:
        parts = raw.split(":")
        try:
            return int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return None
    total = 0
    for val, unit in re.findall(r"(\d+)([hms]?)", raw):
        v = int(val)
        total += v * 3600 if unit == "h" else v * 60 if unit == "m" else v
    return total or None


class TimerConnector:
    """Connecteur Timer — compte à rebours avec bip."""

    _timers: dict[str, dict] = {}
    _lock = threading.Lock()

    def __init__(self, memory) -> None:
        self.memory = memory

    def execute(self, action: str, params: dict) -> str:
        actions = {
            "start":  self.start,
            "status": self.status,
            "cancel": self.cancel,
        }
        fn = actions.get(action, self.start)
        return fn(params)

    def start(self, params: dict) -> str:
        duration_raw = str(params.get("duration", "5m"))
        message      = params.get("message", "Temps ecoule !")
        seconds      = _parse_duration(duration_raw)
        if not seconds:
            return f"Duree invalide : {duration_raw}"
        timer_id = f"timer_{len(self._timers)+1}"
        def _run():
            with self._lock:
                self._timers[timer_id] = {"remaining": seconds, "message": message}
            remaining = seconds
            while remaining > 0:
                time.sleep(1); remaining -= 1
                with self._lock:
                    if timer_id not in self._timers:
                        return
                    self._timers[timer_id]["remaining"] = remaining
            with self._lock:
                self._timers.pop(timer_id, None)
            self._notify(timer_id, message, seconds)
        t = threading.Thread(target=_run, daemon=True, name=f"aion-{timer_id}")
        t.start()
        return f"Timer {duration_raw} demarre (id: {timer_id})"

    def status(self, params: dict = None) -> str:
        with self._lock:
            if not self._timers:
                return "Aucun timer actif."
            lines = []
            for tid, info in self._timers.items():
                rem = info.get("remaining", 0)
                m, s = divmod(rem, 60)
                lines.append(f"  {tid} : {m:02d}:{s:02d} restant — {info.get('message','')}")
            return "\n".join(lines)

    def cancel(self, params: dict) -> str:
        tid = params.get("timer_id", "")
        with self._lock:
            if tid in self._timers:
                del self._timers[tid]
                return f"Timer {tid} annule."
        return f"Timer {tid} introuvable."

    def _notify(self, timer_id: str, message: str, duration: int) -> None:
        try:
            import winsound
            for _ in range(3):
                winsound.Beep(880, 300); time.sleep(0.15)
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.MessageBeep(0)
            except Exception:
                print(f"\a⏰ {message}", flush=True)
        try:
            from plyer import notification
            m, s = divmod(duration, 60)
            notification.notify(title="⏰ AION Timer",
                                message=message, timeout=8)
        except Exception:
            pass
        logger.info("Timer terminé : %s", message)
