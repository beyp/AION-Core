"""
updater.py -- Auto-update AION-Core.

Verifie periodiquement si une mise a jour est disponible sur GitHub,
notifie le dashboard, et peut appliquer la mise a jour + redemarrer.

Modes :
  "notify" : affiche une banniere dans le dashboard (defaut)
  "auto"   : applique automatiquement et redemarre

Usage :
    updater = AionUpdater()
    updater.start()          # lance le watcher en arriere-plan
    updater.check_now()      # verifie immediatement
    updater.apply_update()   # git pull + pip install + restart
"""
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Fichier de state persiste entre les requetes
STATE_FILE = Path("data") / "updater_state.json"


class AionUpdater:
    """
    Watcher de mise a jour pour AION-Core.
    Tourne en thread daemon, non bloquant.
    """

    DEFAULT_CHECK_INTERVAL = 3600  # 1 heure par defaut

    def __init__(self, mode: str = "notify", check_interval: int | None = None) -> None:
        self.mode           = mode   # "notify" | "auto"
        self.check_interval = check_interval or self.DEFAULT_CHECK_INTERVAL
        self.repo_path      = Path(__file__).parent.parent  # racine AION-Core
        self._thread        = None
        self._stop_event    = threading.Event()
        self._state         = self._load_state()

    # ── API publique ──────────────────────────────────────────────

    def start(self) -> None:
        """Lance le watcher en thread daemon."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="aion-updater"
        )
        self._thread.start()
        logger.info("AionUpdater demarré (mode=%s, interval=%ds)", self.mode, self.check_interval)

    def stop(self) -> None:
        """Arrete le watcher."""
        self._stop_event.set()

    def check_now(self) -> dict:
        """
        Verifie immediatement si une mise a jour est disponible.
        Utilise git fetch + comparaison des commits.

        Returns:
            {
                "update_available": bool,
                "current_commit":   str,   # SHA court local
                "remote_commit":    str,   # SHA court origin/main
                "commits_behind":   int,   # nombre de commits en retard
                "latest_message":   str,   # message du dernier commit distant
                "checked_at":       str,   # ISO datetime
            }
        """
        try:
            # 1. git fetch silencieux (ne modifie pas le working tree)
            fetch = subprocess.run(
                ["git", "fetch", "origin", "main", "--quiet"],
                cwd=str(self.repo_path),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=30
            )
            if fetch.returncode != 0:
                raise RuntimeError(f"git fetch failed: {fetch.stderr.strip()[:200]}")

            # 2. SHA local (HEAD)
            local = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.repo_path),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            current_sha = local.stdout.strip()[:12]

            # 3. SHA distant (origin/main)
            remote = subprocess.run(
                ["git", "rev-parse", "origin/main"],
                cwd=str(self.repo_path),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            remote_sha = remote.stdout.strip()[:12]

            update_available = current_sha != remote_sha

            # 4. Compter les commits en retard
            commits_behind = 0
            if update_available:
                behind = subprocess.run(
                    ["git", "rev-list", "--count", f"HEAD..origin/main"],
                    cwd=str(self.repo_path),
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace"
                )
                try:
                    commits_behind = int(behind.stdout.strip())
                except ValueError:
                    commits_behind = 1

            # 5. Message du dernier commit distant
            last_msg = subprocess.run(
                ["git", "log", "origin/main", "-1", "--pretty=%s"],
                cwd=str(self.repo_path),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            latest_message = last_msg.stdout.strip()

            # 6. Date du dernier commit distant
            last_date = subprocess.run(
                ["git", "log", "origin/main", "-1", "--pretty=%cr"],
                cwd=str(self.repo_path),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            latest_date = last_date.stdout.strip()

            checked_at = datetime.now().isoformat()

            state = {
                "update_available": update_available,
                "current_commit":   current_sha,
                "remote_commit":    remote_sha,
                "commits_behind":   commits_behind,
                "latest_message":   latest_message,
                "latest_date":      latest_date,
                "checked_at":       checked_at,
                "applied_at":       self._state.get("applied_at", ""),
                "error":            "",
            }
            self._state = state
            self._save_state()
            logger.info("Update check: %s (behind=%d) %s",
                        "UPDATE DISPO" if update_available else "A JOUR",
                        commits_behind, latest_message[:50])

            # Mode auto : appliquer directement
            if update_available and self.mode == "auto":
                logger.info("Mode auto : application de la mise a jour...")
                return self.apply_update()

            return state

        except Exception as e:
            error_state = {
                "update_available": False,
                "current_commit":   "unknown",
                "remote_commit":    "unknown",
                "commits_behind":   0,
                "latest_message":   "",
                "latest_date":      "",
                "checked_at":       datetime.now().isoformat(),
                "applied_at":       self._state.get("applied_at", ""),
                "error":            str(e),
            }
            self._state = error_state
            self._save_state()
            logger.warning("Update check error: %s", e)
            return error_state

    def apply_update(self) -> dict:
        """
        Applique la mise a jour AION-Core :
        1. git pull origin main
        2. pip install -r requirements.txt (dans le venv)
        3. Redemarrage propre via startaion.bat

        Returns:
            {"success": bool, "message": str, "steps": [...]}
        """
        steps  = []
        logger.info("=== Application mise a jour AION-Core ===")

        # Etape 1 : git pull
        try:
            pull = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=str(self.repo_path),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=120
            )
            if pull.returncode == 0:
                steps.append({"name": "git pull", "success": True,
                               "output": pull.stdout.strip()[:200]})
                logger.info("git pull OK: %s", pull.stdout.strip()[:100])
            else:
                steps.append({"name": "git pull", "success": False,
                               "output": pull.stderr.strip()[:200]})
                return {"success": False, "steps": steps,
                        "message": f"git pull echoue: {pull.stderr.strip()[:200]}"}
        except Exception as e:
            steps.append({"name": "git pull", "success": False, "output": str(e)})
            return {"success": False, "steps": steps, "message": str(e)}

        # Etape 2 : pip install (dans le venv si present)
        venv_pip = self.repo_path / ".venv" / "Scripts" / "pip.exe"
        pip_cmd  = [str(venv_pip)] if venv_pip.exists() else [sys.executable, "-m", "pip"]
        req_file = self.repo_path / "requirements.txt"

        if req_file.exists():
            try:
                pip = subprocess.run(
                    pip_cmd + ["install", "-r", "requirements.txt", "--quiet"],
                    cwd=str(self.repo_path),
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=300
                )
                steps.append({"name": "pip install", "success": pip.returncode == 0,
                               "output": (pip.stdout + pip.stderr).strip()[:200]})
                logger.info("pip install: %s", "OK" if pip.returncode == 0 else "WARN")
            except Exception as e:
                steps.append({"name": "pip install", "success": False, "output": str(e)})
                logger.warning("pip install error (non bloquant): %s", e)
        else:
            steps.append({"name": "pip install", "success": True, "output": "Pas de requirements.txt"})

        # Mettre a jour le state
        self._state["applied_at"] = datetime.now().isoformat()
        self._state["update_available"] = False
        self._save_state()

        # Etape 3 : Redemarrage
        steps.append({"name": "restart", "success": True, "output": "Redemarrage dans 3s..."})
        logger.info("Mise a jour appliquee. Redemarrage dans 3s...")

        # Lancer le redemarrage en thread separe (apres avoir repondu a la requete HTTP)
        def _do_restart():
            time.sleep(3)
            self._restart_aion()

        threading.Thread(target=_do_restart, daemon=True, name="aion-restart").start()

        return {
            "success": True,
            "steps":   steps,
            "message": "Mise a jour appliquee ! AION-Core redemarrera dans 3 secondes.",
            "restart_in": 3,
        }

    def get_state(self) -> dict:
        """Retourne l'etat actuel (depuis le fichier state)."""
        return self._state

    # ── Boucle de surveillance ────────────────────────────────────

    def _watch_loop(self) -> None:
        """Thread principal du watcher."""
        # Attendre 30s apres le demarrage avant la premiere verif
        self._stop_event.wait(30)
        while not self._stop_event.is_set():
            self.check_now()
            self._stop_event.wait(self.check_interval)

    # ── Redemarrage ───────────────────────────────────────────────

    def _restart_aion(self) -> None:
        """
        Redemarre AION-Core dans la MEME console.

        Windows : os.execv() remplace le process courant par python main.py
                  → meme fenetre, meme PID de console, clear avant affichage
        Linux   : identique avec os.execv()

        os.execv() est la cle : il remplace le process en cours sans
        ouvrir de nouvelle fenetre, la console reste la meme.
        """
        # Clear console + banniere de redemarrage
        os.system("cls" if sys.platform == "win32" else "clear")
        print("\n" + "=" * 50)
        print("  🔄 AION-Core — Redemarrage apres mise a jour")
        print("=" * 50 + "\n")

        logger.info("=== REDEMARRAGE AION-CORE (meme console) ===")

        # Trouver le bon executable Python (venv si present)
        venv_python = self.repo_path / ".venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            python_exe = str(venv_python)
        else:
            python_exe = sys.executable

        main_py = str(self.repo_path / "main.py")

        try:
            if sys.platform == "win32":
                # Windows : os.execv remplace le process courant
                # → meme console, meme fenetre, pas de nouvelle cmd
                os.execv(python_exe, [python_exe, main_py])
            else:
                # Linux / Mac : identique
                os.execv(python_exe, [python_exe, main_py])

        except Exception as e:
            logger.error("os.execv echoue (%s) — fallback subprocess", e)
            # Fallback : lancer dans la meme console via call() (bloquant)
            try:
                subprocess.call(
                    [python_exe, main_py],
                    cwd=str(self.repo_path),
                )
            except Exception as e2:
                logger.error("Fallback aussi echoue: %s", e2)
            finally:
                os._exit(0)

    # ── State persistant ──────────────────────────────────────────

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "update_available": False,
            "current_commit":   "",
            "remote_commit":    "",
            "commits_behind":   0,
            "latest_message":   "",
            "latest_date":      "",
            "checked_at":       "",
            "applied_at":       "",
            "error":            "",
        }

    def _save_state(self) -> None:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Impossible de sauvegarder l'etat updater: %s", e)
