"""
AppLauncher -- Module de demarrage automatique des apps.

Lance les apps configurees avec autostart.enabled=true.
Lit apps.json (built-in) ET apps.local.json (apps perso).
Supporte les modes : fastapi, docker, desktop.

Usage :
    launcher = AppLauncher()
    launcher.start_all()
    launcher.stop_app("quickmind")
"""
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import requests as _http

logger = logging.getLogger(__name__)


def _merge_registries() -> dict:
    """
    Fusionne apps.json (built-in) + apps.local.json (perso, git-ignore).
    apps.local.json a priorite sur apps.json pour les cles communes.
    """
    merged = {"apps": {}}
    for reg_file in [Path("apps.json"), Path("apps.local.json")]:
        if reg_file.exists():
            try:
                with open(reg_file, encoding="utf-8") as f:
                    data = json.load(f)
                merged["apps"].update(data.get("apps", {}))
            except Exception as e:
                logger.warning("Erreur lecture %s: %s", reg_file, e)
    return merged


def _detect_launch_command(install_path: str) -> list[str] | None:
    """
    Detecte automatiquement la commande de lancement d'une app.
    Priorite : start_<app>.bat > run_api.py > main.py > app.py
    Utilise le venv si present.

    Returns:
        Liste de strings ex: ["C:/path/.venv/Scripts/python.exe", "run_api.py"]
        ou None si rien trouve
    """
    root = Path(install_path)
    if not root.exists():
        return None

    venv_python = root / ".venv" / "Scripts" / "python.exe"
    python_exe  = str(venv_python) if venv_python.exists() else sys.executable

    # Scripts Python candidats par ordre de priorite
    for script in ["run_api.py", "main.py", "app.py", "server.py", "run.py"]:
        if (root / script).exists():
            return [python_exe, script]

    return None


class AppLauncher:
    """Lance et surveille les apps au demarrage d'AION."""

    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen] = {}
        self._registry  = _merge_registries()

    def reload(self) -> None:
        """Recharge le registre (apres install d'une nouvelle app)."""
        self._registry = _merge_registries()

    # ── API publique ──────────────────────────────────────────────

    def start_all(self) -> dict:
        """Lance toutes les apps avec autostart.enabled=True, dans l'ordre."""
        apps = self._registry.get("apps", {})
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
        """Arrete tous les processus geres par AION."""
        for app_id in list(self._processes.keys()):
            self.stop_app(app_id)

    def start_app(self, app_id: str) -> dict:
        """
        Lance une app specifique.
        Detecte automatiquement la commande si non configuree.
        """
        # Recharger le registre pour voir les apps fraichement installees
        self._registry = _merge_registries()

        app_cfg   = self._registry.get("apps", {}).get(app_id, {})
        autostart = app_cfg.get("autostart", {})

        if not autostart.get("enabled", False):
            return {"success": False, "message": f"Autostart desactive pour {app_id}"}

        if self._is_already_running(app_id, app_cfg):
            return {"success": True, "message": f"{app_id} deja actif", "already_running": True}

        mode = autostart.get("mode", "fastapi")

        if mode == "fastapi":
            return self._start_fastapi(app_id, app_cfg, autostart)
        if mode == "docker":
            return self._start_docker(app_id, app_cfg, autostart)
        if mode == "desktop":
            return self._start_desktop(app_id, app_cfg, autostart)

        return {"success": False, "message": f"Mode inconnu: {mode}"}

    def stop_app(self, app_id: str) -> dict:
        """Arrete une app via son processus AION ou son port."""
        # 1. Tuer le processus AION-gere
        proc = self._processes.get(app_id)
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            del self._processes[app_id]
            logger.info("App arretee (process): %s", app_id)
            return {"success": True, "message": f"{app_id} arrete"}

        # 2. Tuer via le port (process lance en dehors d'AION)
        app_cfg = self._registry.get("apps", {}).get(app_id, {})
        port    = app_cfg.get("autostart", {}).get("port", 0)
        if port:
            killed = self._kill_port(port)
            if killed:
                return {"success": True, "message": f"{app_id} arrete (port {port} libere)"}

        return {"success": False, "message": f"{app_id} non gere par AION (pas de processus actif)"}

    def status(self) -> list:
        """Statut de toutes les apps du registre."""
        self._registry = _merge_registries()
        results = []
        for app_id, cfg in self._registry.get("apps", {}).items():
            autostart  = cfg.get("autostart", {})
            is_running = self._is_already_running(app_id, cfg)
            is_managed = app_id in self._processes and self._processes[app_id].poll() is None
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

    # ── Modes de demarrage ────────────────────────────────────────

    def _start_fastapi(self, app_id: str, app_cfg: dict, autostart: dict) -> dict:
        """
        Lance un service FastAPI/uvicorn.

        Logique de commande (par priorite) :
        1. autostart.command si defini et valide
        2. Detection automatique via _detect_launch_command()
        3. Erreur explicite
        """
        install_path = autostart.get("path", "")
        store_path   = app_cfg.get("store", {}).get("install_path", "")
        path         = install_path or store_path

        if not path or not Path(path).exists():
            return {
                "success": False,
                "message": f"Repertoire introuvable pour {app_id}: {path!r}. "
                           f"Verifie autostart.path dans apps.local.json"
            }

        # Determiner la commande
        command = autostart.get("command", [])

        # Valider que le premier element (python/exe) existe
        if command and Path(command[0]).exists():
            logger.info("Commande configuree pour %s: %s", app_id, command)
        else:
            # Auto-detection
            detected = _detect_launch_command(path)
            if not detected:
                return {
                    "success": False,
                    "message": f"Aucun script de lancement trouve dans {path} "
                               f"(run_api.py, main.py, app.py...)"
                }
            command = detected
            logger.info("Commande auto-detectee pour %s: %s", app_id, command)

        env = os.environ.copy()
        env.update(autostart.get("env", {}))

        try:
            proc = subprocess.Popen(
                command,
                cwd           = str(path),
                env           = env,
                stdout        = subprocess.DEVNULL,
                stderr        = subprocess.DEVNULL,
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self._processes[app_id] = proc
            logger.info("Process lance: %s PID=%d  cmd=%s", app_id, proc.pid, command)
        except Exception as e:
            return {"success": False, "message": f"Erreur lancement {app_id}: {e}"}

        # Health check (optionnel, non bloquant par defaut)
        if autostart.get("health_check", False):
            url       = app_cfg.get("url", f"http://localhost:{autostart.get('port', 8000)}")
            health_ep = app_cfg.get("health_endpoint", "/health")
            timeout   = autostart.get("health_timeout_seconds", 30)
            ok = self._wait_for_health(url.rstrip("/") + health_ep, timeout)
            status = "pret" if ok else f"lance mais pas repond apres {timeout}s"
            return {"success": True, "message": f"{app_id} {status} ({url})", "pid": proc.pid}

        return {"success": True, "message": f"{app_id} lance (PID {proc.pid})", "pid": proc.pid}

    def _start_docker(self, app_id: str, app_cfg: dict, autostart: dict) -> dict:
        """Lance via docker-compose."""
        path    = autostart.get("path", "")
        timeout = autostart.get("health_timeout_seconds", 30)

        if not path or not Path(path).exists():
            return {"success": False, "message": f"Chemin Docker introuvable: {path}"}

        compose_file = None
        for f in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
            if (Path(path) / f).exists():
                compose_file = f
                break

        if not compose_file:
            return {"success": False, "message": f"Aucun docker-compose.yml trouve dans {path}"}

        try:
            result = subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd=path, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120
            )
            if result.returncode != 0:
                return {"success": False, "message": f"docker compose failed: {result.stderr[:300]}"}
        except FileNotFoundError:
            return {"success": False, "message": "Docker non installe ou pas dans le PATH"}
        except Exception as e:
            return {"success": False, "message": f"Docker error: {e}"}

        url       = app_cfg.get("url", "")
        health_ep = app_cfg.get("health_endpoint", "/health")
        if url and autostart.get("health_check", False):
            ok = self._wait_for_health(url.rstrip("/") + health_ep, timeout)
            status = "pret" if ok else "lance mais pas accessible"
            return {"success": True, "message": f"{app_id} Docker {status}"}

        return {"success": True, "message": f"{app_id} Docker lance"}

    def _start_desktop(self, app_id: str, app_cfg: dict, autostart: dict) -> dict:
        """Lance une app desktop."""
        path    = autostart.get("path", "")
        command = autostart.get("command", [])
        if not path or not Path(path).exists():
            return {"success": False, "message": f"Chemin introuvable: {path}"}
        if not command:
            detected = _detect_launch_command(path)
            if not detected:
                return {"success": False, "message": f"Commande non trouvee pour {app_id}"}
            command = detected
        try:
            proc = subprocess.Popen(command, cwd=str(path))
            self._processes[app_id] = proc
            return {"success": True, "message": f"{app_id} desktop lance (PID {proc.pid})"}
        except Exception as e:
            return {"success": False, "message": f"Erreur: {e}"}

    # ── Helpers ───────────────────────────────────────────────────

    def _wait_for_health(self, url: str, timeout: int = 30) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                r = _http.get(url, timeout=2)
                if r.status_code < 400:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False

    def _kill_port(self, port: int) -> bool:
        """Tue le processus qui ecoute sur un port donne."""
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            for line in (result.stdout or "").splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    pid = line.split()[-1]
                    subprocess.run(["taskkill", "/PID", pid, "/F"],
                                   capture_output=True)
                    logger.info("Port %d libere (PID %s)", port, pid)
                    return True
        except Exception as e:
            logger.warning("_kill_port %d: %s", port, e)
        return False

    def _is_already_running(self, app_id: str, app_cfg: dict) -> bool:
        """Verifie si l'app tourne deja."""
        proc = self._processes.get(app_id)
        if proc and proc.poll() is None:
            return True
        url       = app_cfg.get("url", "")
        health_ep = app_cfg.get("health_endpoint", "/health")
        if url:
            try:
                r = _http.get(url.rstrip("/") + health_ep, timeout=2)
                return r.status_code < 400
            except Exception:
                pass
        return False
