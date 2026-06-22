"""
AppLauncher -- Module de demarrage automatique des apps.

Lance les apps configurees avec autostart=true au demarrage d AION.
Supporte les modes : fastapi, docker, desktop.

Usage :
    launcher = AppLauncher(registry_path="apps.json")
    launcher.start_all()   # au demarrage AION
    launcher.stop_all()    # a l arret AION
"""
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)


class AppLauncher:
    """Lance et surveille les apps au demarrage d AION."""

    def __init__(self, registry_path: str = "apps.json") -> None:
        self.registry_path = Path(registry_path)
        self._processes: dict[str, subprocess.Popen] = {}
        self._registry   = self._load_registry()

    def _load_registry(self) -> dict:
        if not self.registry_path.exists():
            return {"apps": {}}
        try:
            with open(self.registry_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Impossible de lire apps.json: %s", e)
            return {"apps": {}}

    # -- API publique ----------------------------------------------------------

    def start_all(self) -> dict:
        """Lance toutes les apps avec autostart enabled, dans l ordre."""
        apps = self._registry.get("apps", {})

        # Trier par startup_order
        autostart_apps = [
            (app_id, cfg)
            for app_id, cfg in apps.items()
            if cfg.get("autostart", {}).get("enabled", False)
        ]
        autostart_apps.sort(
            key=lambda x: x[1].get("autostart", {}).get("startup_order", 99)
        )

        results = {}
        for app_id, cfg in autostart_apps:
            result = self.start_app(app_id)
            results[app_id] = result
            logger.info("Autostart %s: %s", app_id, result.get("message", ""))

        return results

    def stop_all(self) -> None:
        """Arrete tous les processus lances par AION."""
        for app_id in list(self._processes.keys()):
            self.stop_app(app_id)

    def start_app(self, app_id: str) -> dict:
        """Lance une app specifique."""
        app_cfg    = self._registry.get("apps", {}).get(app_id, {})
        autostart  = app_cfg.get("autostart", {})
        mode       = autostart.get("mode", "fastapi")
        app_status = app_cfg.get("status", "")

        if not autostart.get("enabled", False):
            return {"success": False, "message": "Autostart desactive pour " + app_id}

        # Verifier si deja en cours
        if self._is_already_running(app_id, app_cfg):
            return {"success": True, "message": app_id + " deja actif", "already_running": True}

        if mode == "fastapi":
            return self._start_fastapi(app_id, app_cfg, autostart)
        if mode == "docker":
            return self._start_docker(app_id, app_cfg, autostart)
        if mode == "desktop":
            return self._start_desktop(app_id, app_cfg, autostart)

        return {"success": False, "message": "Mode inconnu: " + mode}

    def stop_app(self, app_id: str) -> dict:
        """Arrete une app specifique."""
        proc = self._processes.get(app_id)
        if not proc:
            return {"success": False, "message": app_id + " non gere par AION"}
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        del self._processes[app_id]
        logger.info("App arretee: %s", app_id)
        return {"success": True, "message": app_id + " arrete"}

    def status(self) -> list:
        """Retourne le statut de toutes les apps geries."""
        apps    = self._registry.get("apps", {})
        results = []
        for app_id, cfg in apps.items():
            autostart  = cfg.get("autostart", {})
            is_managed = app_id in self._processes
            is_running = self._is_already_running(app_id, cfg)
            results.append({
                "app_id":    app_id,
                "name":      cfg.get("name", app_id),
                "autostart": autostart.get("enabled", False),
                "mode":      autostart.get("mode", "none"),
                "managed":   is_managed,
                "running":   is_running,
                "url":       cfg.get("url", ""),
                "icon":      cfg.get("icon", "package"),
            })
        return results

    def configure_autostart(self, app_id: str, enabled: bool,
                             mode: str = "fastapi", path: str = "",
                             port: int = 0, order: int = 99) -> dict:
        """
        Configure l autostart d une app (appele par l IA ou l UI).

        Args:
            app_id:  ID de l app
            enabled: Activer ou desactiver l autostart
            mode:    "fastapi" | "docker" | "desktop"
            path:    Chemin du projet
            port:    Port d ecoute
            order:   Ordre de demarrage
        """
        apps = self._registry.setdefault("apps", {})
        if app_id not in apps:
            return {"success": False, "message": "App " + app_id + " introuvable dans le registre"}

        autostart_cfg = apps[app_id].setdefault("autostart", {})
        autostart_cfg["enabled"] = enabled
        if mode:    autostart_cfg["mode"]          = mode
        if path:    autostart_cfg["path"]          = path
        if port:    autostart_cfg["port"]          = port
        if order:   autostart_cfg["startup_order"] = order
        autostart_cfg["health_check"]          = True
        autostart_cfg["health_timeout_seconds"] = 15

        # Commande par defaut selon le mode
        if mode == "fastapi" and not autostart_cfg.get("command"):
            autostart_cfg["command"] = ["python", "run_api.py"]
        if mode == "docker" and not autostart_cfg.get("command"):
            autostart_cfg["command"] = ["docker-compose", "up", "-d"]

        # Sauvegarder
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=2, ensure_ascii=False)

        status = "active" if enabled else apps[app_id].get("status", "pending")
        apps[app_id]["status"] = status

        action = "active" if enabled else "desactive"
        return {
            "success": True,
            "message": "Autostart " + action + " pour " + app_id + " (mode: " + mode + ")",
            "config":  autostart_cfg,
        }

    # -- Modes de demarrage ----------------------------------------------------

    def _start_fastapi(self, app_id: str, app_cfg: dict, autostart: dict) -> dict:
        """Lance un service FastAPI via subprocess."""
        path    = autostart.get("path", "")
        command = autostart.get("command", ["python", "run_api.py"])
        port    = autostart.get("port", 8765)
        timeout = autostart.get("health_timeout_seconds", 30)  # 30s par defaut
        env_extra = autostart.get("env", {})

        if not path or not Path(path).exists():
            return {
                "success": False,
                "message": "Chemin introuvable: " + str(path) + ". Configure avec: autostart " + app_id + " path=C:\\ton\\chemin"
            }

        # Env variables
        env = os.environ.copy()
        env.update(env_extra)

        try:
            # Trouver l executable Python du venv si present
            venv_python = Path(path) / ".venv" / "Scripts" / "python.exe"
            if venv_python.exists() and command[0] == "python":
                command = [str(venv_python)] + command[1:]

            proc = subprocess.Popen(
                command,
                cwd           = path,
                env           = env,
                stdout        = subprocess.DEVNULL,   # les apps ont leurs propres logs
                stderr        = subprocess.DEVNULL,   # evite UnicodeDecodeError cp1252
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self._processes[app_id] = proc
            logger.info("Processus lance: %s (pid=%d)", app_id, proc.pid)

        except Exception as e:
            return {"success": False, "message": "Erreur lancement " + app_id + ": " + str(e)}

        # Health check
        if autostart.get("health_check", True):
            url          = app_cfg.get("url", "http://localhost:" + str(port))
            health_ep    = app_cfg.get("health_endpoint", "/health")
            health_url   = url.rstrip("/") + health_ep
            ok = self._wait_for_health(health_url, timeout)
            if ok:
                return {"success": True, "message": app_id + " demarre et pret (" + url + ")"}
            else:
                return {
                    "success": False,
                    "message": app_id + " lance mais health check echoue apres " + str(timeout) + "s. Verifie les logs."
                }

        return {"success": True, "message": app_id + " lance (pid=" + str(proc.pid) + ")"}

    def _start_docker(self, app_id: str, app_cfg: dict, autostart: dict) -> dict:
        """Lance un service Docker Compose."""
        path    = autostart.get("path", "")
        timeout = autostart.get("health_timeout_seconds", 30)

        if not path or not Path(path).exists():
            return {"success": False, "message": "Chemin Docker introuvable: " + str(path)}

        try:
            result = subprocess.run(
                ["docker-compose", "up", "-d", app_id],
                cwd     = path,
                capture_output = True,
                text    = True,
                timeout = 60,
            )
            if result.returncode != 0:
                return {"success": False, "message": "docker-compose failed: " + result.stderr[:200]}
        except Exception as e:
            return {"success": False, "message": "Docker error: " + str(e)}

        # Health check
        url       = app_cfg.get("url", "")
        health_ep = app_cfg.get("health_endpoint", "/health")
        if url and autostart.get("health_check", True):
            ok = self._wait_for_health(url.rstrip("/") + health_ep, timeout)
            if ok:
                return {"success": True, "message": app_id + " Docker demarre et pret"}
            return {"success": False, "message": app_id + " Docker lance mais non accessible"}

        return {"success": True, "message": app_id + " Docker lance"}

    def _start_desktop(self, app_id: str, app_cfg: dict, autostart: dict) -> dict:
        """Lance une app desktop (Tkinter etc.) en arriere-plan."""
        path    = autostart.get("path", "")
        command = autostart.get("command", ["python", "main.py"])

        if not path or not Path(path).exists():
            return {"success": False, "message": "Chemin introuvable: " + str(path)}

        try:
            venv_python = Path(path) / ".venv" / "Scripts" / "python.exe"
            if venv_python.exists() and command[0] == "python":
                command = [str(venv_python)] + command[1:]

            proc = subprocess.Popen(command, cwd=path)
            self._processes[app_id] = proc
            return {"success": True, "message": app_id + " desktop lance (pid=" + str(proc.pid) + ")"}
        except Exception as e:
            return {"success": False, "message": "Erreur: " + str(e)}

    # -- Helpers ---------------------------------------------------------------

    def _wait_for_health(self, url: str, timeout: int = 15) -> bool:
        """Attend qu un service soit disponible (health check)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = requests.get(url, timeout=2)
                if r.status_code < 400:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def _is_already_running(self, app_id: str, app_cfg: dict) -> bool:
        """Verifie si l app est deja active (port occupe ou processus vivant)."""
        # Verifier le processus AION-gere
        proc = self._processes.get(app_id)
        if proc and proc.poll() is None:
            return True

        # Verifier via health check
        url       = app_cfg.get("url", "")
        health_ep = app_cfg.get("health_endpoint", "/health")
        if url:
            try:
                r = requests.get(url.rstrip("/") + health_ep, timeout=2)
                return r.status_code < 400
            except Exception:
                pass
        return False
