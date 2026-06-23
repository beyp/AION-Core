"""
system_power.py — Service AION : Contrôle alimentation Windows.

Actions :
  sleep    : mise en veille immédiate ou différée
  shutdown : arrêt immédiat ou différé
  reboot   : redémarrage immédiat ou différé
  cancel   : annuler un arrêt/redémarrage programmé
  status   : état du système (uptime, heure)
"""
from __future__ import annotations
import logging
import platform
import subprocess
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)
IS_WINDOWS = platform.system() == "Windows"


class Service:
    """Service AION — Contrôle alimentation Windows."""

    name        = "system_power"
    description = "Contrôle alimentation Windows — veille, arrêt, redémarrage, planification"
    actions     = ["sleep", "shutdown", "reboot", "cancel", "status"]

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        dispatch = {
            "sleep":    self._sleep,
            "shutdown": self._shutdown,
            "reboot":   self._reboot,
            "restart":  self._reboot,
            "cancel":   self._cancel,
            "abort":    self._cancel,
            "status":   self._status,
        }
        fn = dispatch.get(action.lower())
        if not fn:
            return {"success": False, "message": f"Action '{action}' inconnue. Disponibles : {self.actions}"}
        if not IS_WINDOWS:
            return {"success": False, "message": f"system_power ne supporte que Windows (détecté: {platform.system()})."}
        try:
            return fn(params)
        except Exception as e:
            logger.error("system_power.%s error: %s", action, e)
            return {"success": False, "message": str(e)}

    def _sleep(self, params: dict) -> dict:
        delay_min = self._get_delay(params)
        if delay_min and delay_min > 0:
            trigger = self._future_time_str(delay_min)
            task    = "AION_Sleep"
            cmd     = (f'schtasks /Create /TN "{task}" '
                       f'/TR "rundll32.exe powrprof.dll,SetSuspendState 0,1,0" '
                       f'/SC ONCE /ST {trigger} /F')
            r = self._run(cmd)
            if r["success"]:
                return {"success": True,
                        "message": f"💤 Veille planifiée dans {delay_min} min ({trigger})."}
            return r
        r = self._run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return {"success": r["success"],
                "message": "💤 Mise en veille en cours..." if r["success"] else r["message"]}

    def _shutdown(self, params: dict) -> dict:
        delay_min = self._get_delay(params)
        delay_sec = int(delay_min * 60) if delay_min else 0
        flag      = "/f" if params.get("force", True) else ""
        cmd       = f"shutdown /s /t {delay_sec} {flag}".strip()
        r = self._run(cmd)
        if r["success"]:
            if delay_sec > 0:
                return {"success": True,
                        "message": f"🔴 Arrêt dans {delay_min} min. Tapez cancel pour annuler.",
                        "delay_min": delay_min}
            return {"success": True, "message": "🔴 Arrêt immédiat en cours..."}
        return r

    def _reboot(self, params: dict) -> dict:
        delay_min = self._get_delay(params)
        delay_sec = int(delay_min * 60) if delay_min else 0
        flag      = "/f" if params.get("force", True) else ""
        cmd       = f"shutdown /r /t {delay_sec} {flag}".strip()
        r = self._run(cmd)
        if r["success"]:
            if delay_sec > 0:
                return {"success": True,
                        "message": f"🔄 Redémarrage dans {delay_min} min. Tapez cancel pour annuler.",
                        "delay_min": delay_min}
            return {"success": True, "message": "🔄 Redémarrage immédiat en cours..."}
        return r

    def _cancel(self, params: dict) -> dict:
        r = self._run("shutdown /a")
        self._run('schtasks /Delete /TN "AION_Sleep" /F')
        if r["success"]:
            return {"success": True, "message": "Arret/reboot annule."}
        return {"success": False, "message": "Aucun arret programme a annuler."}

    def _status(self, params: dict) -> dict:
        try:
            import psutil
            boot = datetime.fromtimestamp(psutil.boot_time())
            up   = datetime.now() - boot
            h    = int(up.total_seconds() // 3600)
            m    = int((up.total_seconds() % 3600) // 60)
            batt = ""
            try:
                b = psutil.sensors_battery()
                if b:
                    st   = "en charge" if b.power_plugged else "batterie"
                    batt = f"\n Batterie : {b.percent:.0f}% ({st})"
            except Exception:
                pass
            msg = (f" {platform.node()} — {platform.system()} {platform.release()}\n"
                   f" Uptime : {h}h {m}min (demarre {boot.strftime(chr(37)+'d/'+chr(37)+'m '+chr(37)+'H:'+chr(37)+'M')})\n"
                   f" {datetime.now().strftime(chr(37)+'d/'+chr(37)+'m/'+chr(37)+'Y '+chr(37)+'H:'+chr(37)+'M:'+chr(37)+'S')}{batt}")
        except ImportError:
            msg = f" {platform.node()} — {platform.system()} — {datetime.now()}"
        return {"success": True, "message": msg}

    @staticmethod
    def _get_delay(params: dict) -> float | None:
        for key in ("delay_min", "delay", "minutes", "min", "mins"):
            v = params.get(key)
            if v is not None:
                try:
                    f = float(v)
                    return f if f > 0 else None
                except (TypeError, ValueError):
                    pass
        return None

    @staticmethod
    def _future_time_str(minutes: float) -> str:
        return (datetime.now() + timedelta(minutes=minutes)).strftime("%H:%M")

    @staticmethod
    def _run(cmd: str) -> dict:
        try:
            r   = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            ok  = r.returncode == 0
            msg = (r.stdout or r.stderr or ("OK" if ok else f"Erreur code {r.returncode}")).strip()
            return {"success": ok, "message": msg, "returncode": r.returncode}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Timeout (10s)"}
        except Exception as e:
            return {"success": False, "message": str(e)}
