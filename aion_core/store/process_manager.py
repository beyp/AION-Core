"""
process_manager.py — Gestionnaire de processus pour les apps AION.

Responsabilites :
- Lancer une app (fastapi, docker, python script)
- Stopper une app proprement (via PID sauvegarde)
- Verifier si une app tourne (via port ou PID)
- Persister les PIDs dans data/pids.json pour survivre aux redemarrages

C'est LE point central pour start/stop — utilise par :
  - AppLauncher (autostart au demarrage)
  - store_routes (boutons Start/Stop dans /store)
  - Router IA (commandes vocales "lance quickmind", "arrete quickmind")
"""
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

PID_FILE = Path("data") / "pids.json"


class ProcessManager:
    """Gere le cycle de vie des processus d'apps AION."""

    def __init__(self) -> None:
        self._pids: dict[str, dict] = self._load_pids()

    # ── PID persistence ───────────────────────────────────────────

    def _load_pids(self) -> dict:
        if PID_FILE.exists():
            try:
                with open(PID_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_pids(self) -> None:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PID_FILE, "w", encoding="utf-8") as f:
            json.dump(self._pids, f, indent=2)

    def _register_pid(self, app_id: str, pid: int, port: int = 0,
                      cmd: list[str] = None) -> None:
        self._pids[app_id] = {
            "pid":     pid,
            "port":    port,
            "cmd":     cmd or [],
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save_pids()

    def _unregister_pid(self, app_id: str) -> None:
        self._pids.pop(app_id, None)
        self._save_pids()

    # ── Detection de commande ─────────────────────────────────────

    @staticmethod
    def detect_launch_type(install_path: str) -> dict:
        """
        Detecte automatiquement le type de lancement.

        Priorite :
          1. docker-compose.yml -> type "docker"
          2. Dockerfile seul   -> type "docker_build"
          3. run_api.py / main.py avec uvicorn -> type "uvicorn"
          4. run_api.py / main.py              -> type "python"

        Returns:
            {
                "type":        "docker"|"uvicorn"|"python"|"unknown",
                "command":     [...],
                "compose_file": str | None,
                "port":        int | None,
                "info":        str,
            }
        """
        root = Path(install_path)
        if not root.exists():
            return {"type": "unknown", "command": [], "compose_file": None,
                    "port": None,
                    "info": f"Dossier introuvable: {install_path}"}

        venv_py = root / ".venv" / "Scripts" / "python.exe"
        python  = str(venv_py) if venv_py.exists() else sys.executable

        # 1. Docker Compose (priorite si present)
        for dc in ["docker-compose.yml", "docker-compose.yaml",
                   "compose.yml", "compose.yaml"]:
            if (root / dc).exists():
                # Lire le port depuis le compose
                port = None
                try:
                    content = (root / dc).read_text(encoding="utf-8",
                                                      errors="replace")
                    import re
                    m = re.search(r'- ["']?(\d{4,5}):\d{4,5}["']?', content)
                    if m:
                        port = int(m.group(1))
                except Exception:
                    pass
                return {
                    "type":         "docker",
                    "command":      ["docker", "compose", "-f", dc, "up", "-d", "--build"],
                    "compose_file": str(root / dc),
                    "port":         port,
                    "info":         f"Docker Compose detecte ({dc}), port={port}",
                }

        # 2. Dockerfile seul (sans compose)
        if (root / "Dockerfile").exists():
            app_id = root.name.lower()
            return {
                "type":         "docker_build",
                "command":      ["docker", "build", "-t", app_id, "."],
                "compose_file": None,
                "port":         None,
                "info":         "Dockerfile detecte (sans compose) — build requis",
            }

        # 3. Scripts Python
        scripts = [
            "run_api.py", "run.py", "main.py", "app.py",
            "server.py",  "start.py",
        ]
        for script in scripts:
            if (root / script).exists():
                # Detecter si uvicorn est utilise
                stype = "python"
                try:
                    content = (root / script).read_text(encoding="utf-8",
                                                         errors="replace")
                    if "uvicorn" in content or "FastAPI" in content:
                        stype = "uvicorn"
                except Exception:
                    pass

                if stype == "uvicorn":
                    # Lancer via uvicorn directement pour plus de controle
                    # Chercher le nom du module app
                    app_var = "app"
                    try:
                        import re
                        m = re.search(r'(\w+)\s*=\s*FastAPI', content)
                        if m:
                            app_var = m.group(1)
                    except Exception:
                        pass
                    module = script.replace(".py", "")
                    cmd = [python, "-m", "uvicorn",
                           f"{module}:{app_var}",
                           "--host", "0.0.0.0",
                           "--port", "8000",
                           "--reload"]
                else:
                    cmd = [python, script]

                return {
                    "type":         stype,
                    "command":      cmd,
                    "compose_file": None,
                    "port":         None,
                    "info":         f"Script Python detecte: {script} (type={stype})",
                }

        return {
            "type":         "unknown",
            "command":      [],
            "compose_file": None,
            "port":         None,
            "info":         (
                "Aucun fichier de lancement detecte. "
                "Attendu: docker-compose.yml, Dockerfile, run_api.py, main.py..."
            ),
        }

    # ── Start ─────────────────────────────────────────────────────

    def start(self, app_id: str, install_path: str,
              app_type: str = "auto", command: list[str] = None,
              port: int = 0, env: dict = None) -> dict:
        """
        Lance une app et sauvegarde son PID.

        Args:
            app_id:       ID de l'app (ex: "quickmind")
            install_path: Chemin du repo
            app_type:     "auto" | "fastapi" | "docker" | "python"
            command:      Commande explicite (override auto-detection)
            port:         Port de l'app (pour health check + stop)
            env:          Variables d'environnement supplementaires

        Returns:
            {"success": bool, "pid": int, "message": str, "command": [...]}
        """
        # Verifier si deja en cours
        if self.is_running(app_id, port):
            return {
                "success":  True,
                "message":  f"{app_id} est deja en cours d'execution",
                "pid":      self._pids.get(app_id, {}).get("pid", 0),
                "already_running": True,
            }

        # Determiner commande + type
        if not command:
            detected = self.detect_launch_type(install_path)
            if detected["type"] == "unknown":
                return {"success": False, "message": detected["info"]}
            command  = detected["command"]
            app_type = detected["type"] if app_type == "auto" else app_type
            logger.info("Auto-detected %s: type=%s cmd=%s",
                        app_id, app_type, command)

        # Preparer l'environnement
        proc_env = os.environ.copy()
        if env:
            proc_env.update(env)

        # Lancement selon le type
        if app_type == "docker":
            return self._start_docker(app_id, install_path, command, port)

        # fastapi / python : subprocess
        try:
            proc = subprocess.Popen(
                command,
                cwd    = str(install_path),
                env    = proc_env,
                stdout = subprocess.DEVNULL,
                stderr = subprocess.DEVNULL,
                creationflags = (subprocess.CREATE_NO_WINDOW
                                 if sys.platform == "win32" else 0),
            )
        except FileNotFoundError as e:
            return {
                "success": False,
                "message": f"Executable introuvable: {command[0]}. "
                           f"Verifie que le venv est bien cree dans {install_path}",
            }
        except Exception as e:
            return {"success": False, "message": f"Erreur lancement: {e}"}

        self._register_pid(app_id, proc.pid, port, command)
        logger.info("Process lance: %s PID=%d cmd=%s", app_id, proc.pid, command)

        # Attente courte pour detecter crash immediat
        time.sleep(1.5)
        if proc.poll() is not None:
            self._unregister_pid(app_id)
            return {
                "success": False,
                "message": f"{app_id} a demarre puis crashe immediatement. "
                           f"Verifie les logs dans {install_path}",
                "command": command,
            }

        return {
            "success": True,
            "pid":     proc.pid,
            "type":    app_type,
            "command": command,
            "message": f"{app_id} lance (PID {proc.pid})",
        }

    def _start_docker(self, app_id: str, install_path: str,
                      command: list[str], port: int,
                      appdata_path: str = "") -> dict:
        """
        Lance via docker compose.
        Injecte automatiquement un volume appdata si disponible.
        """
        # Creer le dossier appdata si necessaire
        if appdata_path:
            Path(appdata_path).mkdir(parents=True, exist_ok=True)
            logger.info("AppData docker: %s -> /app/data", appdata_path)

        try:
            # Verifier que Docker tourne
            check = subprocess.run(
                ["docker", "info"],
                capture_output=True, timeout=10
            )
            if check.returncode != 0:
                return {"success": False,
                        "message": "Docker n'est pas en cours d'execution. Lance Docker Desktop."}

            result = subprocess.run(
                command, cwd=str(install_path),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=180,
            )
            output = (result.stdout + result.stderr).strip()
            if result.returncode != 0:
                return {"success": False,
                        "message": f"docker compose failed: {output[:400]}"}

            self._register_pid(app_id, -1, port, command)  # -1 = docker managed
            return {
                "success": True, "pid": -1, "type": "docker",
                "command": command,
                "message": f"{app_id} Docker lance (port {port})",
                "output":  output[:200],
            }
        except FileNotFoundError:
            return {"success": False,
                    "message": "Docker non installe. Installe Docker Desktop: https://docs.docker.com/desktop/windows/"}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Timeout docker compose (>3min)"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Stop ──────────────────────────────────────────────────────

    def stop(self, app_id: str, port: int = 0) -> dict:
        """
        Stoppe une app proprement.
        Strategie : PID sauvegarde → kill PID → si echec → kill port.

        Returns:
            {"success": bool, "message": str}
        """
        info   = self._pids.get(app_id, {})
        pid    = info.get("pid", 0)
        p_port = info.get("port", 0) or port

        killed = False
        method = ""

        # 1. Kill via PID sauvegarde
        if pid and pid > 0:
            try:
                if sys.platform == "win32":
                    result = subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F", "/T"],
                        capture_output=True, text=True, timeout=10
                    )
                    killed = result.returncode == 0
                else:
                    os.kill(pid, 15)  # SIGTERM
                    time.sleep(0.5)
                    try:
                        os.kill(pid, 9)  # SIGKILL si encore la
                    except ProcessLookupError:
                        pass
                    killed = True
                if killed:
                    method = f"PID {pid}"
            except Exception as e:
                logger.warning("Kill PID %d failed: %s", pid, e)

        # 2. Docker stop
        if not killed and pid == -1:
            install = info.get("cmd", [])
            try:
                subprocess.run(
                    ["docker", "compose", "down"],
                    capture_output=True, timeout=30
                )
                killed = True
                method = "docker compose down"
            except Exception:
                pass

        # 3. Kill via port (fallback)
        if not killed and p_port:
            killed = self._kill_port(p_port)
            if killed:
                method = f"port {p_port}"

        if killed:
            self._unregister_pid(app_id)
            logger.info("App stoppee: %s (%s)", app_id, method)
            return {"success": True, "message": f"{app_id} arrete ({method})"}

        self._unregister_pid(app_id)
        return {"success": False,
                "message": f"{app_id}: aucun processus trouve (PID={pid}, port={p_port})"}

    # ── Status ────────────────────────────────────────────────────

    def is_running(self, app_id: str, port: int = 0) -> bool:
        """Verifie si une app tourne (PID ou port)."""
        info   = self._pids.get(app_id, {})
        pid    = info.get("pid", 0)
        p_port = info.get("port", 0) or port

        # Check PID
        if pid and pid > 0:
            try:
                if sys.platform == "win32":
                    r = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}"],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace"
                    )
                    if str(pid) in (r.stdout or ""):
                        return True
                else:
                    os.kill(pid, 0)
                    return True
            except Exception:
                pass

        # Check port HTTP
        if p_port:
            try:
                import urllib.request
                urllib.request.urlopen(
                    f"http://localhost:{p_port}/health", timeout=2)
                return True
            except Exception:
                pass
            # Fallback netstat
            try:
                r = subprocess.run(
                    ["netstat", "-ano"], capture_output=True, text=True,
                    encoding="utf-8", errors="replace"
                )
                return f":{p_port} " in (r.stdout or "") and "LISTENING" in (r.stdout or "")
            except Exception:
                pass

        return False

    def status_all(self) -> dict[str, dict]:
        """Retourne le statut de toutes les apps suivies."""
        result = {}
        for app_id, info in self._pids.items():
            running = self.is_running(app_id, info.get("port", 0))
            result[app_id] = {
                "running": running,
                "pid":     info.get("pid"),
                "port":    info.get("port"),
                "started": info.get("started"),
                "command": info.get("cmd", []),
            }
            if not running:
                self._unregister_pid(app_id)
        return result

    # ── Helpers ───────────────────────────────────────────────────

    def _kill_port(self, port: int) -> bool:
        """Tue le processus qui ecoute sur un port."""
        try:
            r = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            for line in (r.stdout or "").splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    pid = line.split()[-1]
                    subprocess.run(["taskkill", "/PID", pid, "/F"],
                                   capture_output=True)
                    logger.info("Port %d libere (PID %s)", port, pid)
                    return True
        except Exception as e:
            logger.warning("_kill_port %d: %s", port, e)
        return False
