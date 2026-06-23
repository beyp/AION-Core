"""
app_setup.py -- Setup complet d'une app apres git clone.

Sequence executee automatiquement par AppStore.install() :
  1. Creer le venv (.venv) si absent
  2. pip install -r requirements.txt dans le venv
  3. Copier data/ (et autres fichiers persistants) vers appdata/
  4. Generer start_<app_id>.bat dans le repo

Usage :
    setup = AppSetup(app_id, install_path, appdata_mgr)
    result = setup.run(appdata_files)
"""
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class AppSetup:
    """
    Configure un repo fraichement clone pour fonctionner avec AION-Core.
    Cree le venv, installe les dependances, genere le .bat de lancement.
    """

    def __init__(self, app_id: str, install_path: str, appdata_mgr=None) -> None:
        self.app_id       = app_id
        self.install_path = Path(install_path)
        self.appdata_mgr  = appdata_mgr
        self.venv_path    = self.install_path / ".venv"
        self.venv_python  = self.venv_path / "Scripts" / "python.exe"
        self.venv_pip     = self.venv_path / "Scripts" / "pip.exe"

    def run(self, appdata_files: list[str]) -> dict:
        """
        Sequence complete de setup. Retourne un rapport detaille.

        Returns:
            {
                "success": bool,
                "steps":   [{"name": str, "success": bool, "message": str}],
                "bat_path": str,
                "message": str
            }
        """
        steps = []

        # ── Etape 1 : Creer le venv ───────────────────────────────
        step = self._create_venv()
        steps.append(step)
        if not step["success"]:
            return {"success": False, "steps": steps,
                    "message": f"Echec creation venv: {step['message']}"}

        # ── Etape 2 : pip install ─────────────────────────────────
        step = self._pip_install()
        steps.append(step)
        # Non bloquant : on continue meme si pas de requirements.txt

        # ── Etape 3 : Copier data/ -> appdata/ (premiere fois) ───
        step = self._init_appdata(appdata_files)
        steps.append(step)

        # ── Etape 4 : Generer le .bat de lancement ────────────────
        bat_result = self._generate_bat()
        steps.append(bat_result)

        all_ok  = all(s["success"] for s in steps[:2])  # venv + pip critiques
        bat_path = bat_result.get("bat_path", "")

        return {
            "success":  all_ok,
            "steps":    steps,
            "bat_path": bat_path,
            "message":  f"Setup {self.app_id} termine ({len([s for s in steps if s['success']])} / {len(steps)} etapes OK)",
        }

    # ── Etapes ────────────────────────────────────────────────────

    def _create_venv(self) -> dict:
        """Cree le venv .venv si absent."""
        if self.venv_python.exists():
            return {"name": "venv", "success": True,
                    "message": f"Venv deja present : {self.venv_path}"}
        try:
            logger.info("Creation venv pour %s...", self.app_id)
            result = subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_path)],
                cwd=str(self.install_path),
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                return {"name": "venv", "success": False,
                        "message": f"Erreur venv: {result.stderr.strip()[:200]}"}
            logger.info("Venv cree : %s", self.venv_path)
            return {"name": "venv", "success": True,
                    "message": f"Venv cree : {self.venv_path}"}
        except Exception as e:
            return {"name": "venv", "success": False, "message": str(e)}

    def _pip_install(self) -> dict:
        """
        pip install dans le venv.

        Ordre de priorite des fichiers requirements :
          1. requirements.api.txt  (mode headless/API sans GUI — ex: QuickMind)
          2. requirements.txt      (requirements complets)

        requirements.api.txt est prefere car il inclut fastapi+uvicorn
        sans les dependances GUI (customtkinter, pywin32...) qui peuvent
        planter en mode serveur headless.
        """
        # Chercher le bon fichier requirements dans l'ordre de priorite
        candidates = [
            ("requirements.api.txt",  "mode API (sans GUI)"),
            ("requirements.txt",      "requirements complet"),
        ]

        req_file = None
        req_label = ""
        for fname, label in candidates:
            candidate = self.install_path / fname
            if candidate.exists():
                req_file  = candidate
                req_label = label
                break

        if req_file is None:
            return {"name": "pip", "success": True,
                    "message": "Aucun requirements*.txt trouve — skip pip install"}

        if not self.venv_pip.exists():
            return {"name": "pip", "success": False,
                    "message": f"pip introuvable dans le venv ({self.venv_pip})"}

        logger.info("pip install %s pour %s (%s)...",
                    req_file.name, self.app_id, req_label)
        try:
            result = subprocess.run(
                [str(self.venv_pip), "install", "-r", str(req_file), "--quiet"],
                cwd=str(self.install_path),
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=300
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip()[:400]
                return {"name": "pip", "success": False,
                        "message": f"Erreur pip ({req_file.name}): {err}",
                        "req_file": str(req_file)}
            logger.info("pip install OK pour %s via %s", self.app_id, req_file.name)
            return {"name": "pip", "success": True,
                    "message": f"Dependances installees via {req_file.name} ({req_label})",
                    "req_file": str(req_file)}
        except subprocess.TimeoutExpired:
            return {"name": "pip", "success": False,
                    "message": f"Timeout pip >5 min ({req_file.name})"}
        except Exception as e:
            return {"name": "pip", "success": False, "message": str(e)}

    def _init_appdata(self, appdata_files: list[str]) -> dict:
        """
        Copie initiale des fichiers data/ -> appdata/.
        Seulement si appdata/ est vide (premiere installation).
        Si appdata/ a des fichiers, on les restaure dans le repo.
        """
        if not self.appdata_mgr:
            return {"name": "appdata", "success": True,
                    "message": "AppDataManager non disponible - skip"}

        if not appdata_files:
            return {"name": "appdata", "success": True,
                    "message": "Aucun fichier persistant declare"}

        # Verifier si appdata existe deja (reinstallation)
        existing = self.appdata_mgr.list_appdata(self.app_id)
        if existing:
            # Reinstallation : restaurer depuis appdata/ -> repo
            result = self.appdata_mgr.restore(
                self.app_id, str(self.install_path), appdata_files)
            restored = result.get("restored", [])
            return {"name": "appdata", "success": True,
                    "message": f"AppData restaure depuis sauvegarde : {restored}"}
        else:
            # Premiere installation : copier repo -> appdata/
            result = self.appdata_mgr.save(
                self.app_id, str(self.install_path), appdata_files)
            saved = result.get("saved", [])
            missing = result.get("missing", [])
            msg = f"AppData initial copie : {saved}"
            if missing:
                msg += f" (non trouve : {missing})"
            return {"name": "appdata", "success": True, "message": msg}

    def _generate_bat(self) -> dict:
        """
        Genere start_<app_id>.bat dans le repo.
        Detecte automatiquement le script de lancement (run_api.py, main.py...).
        """
        # Detecter le script principal
        candidates = ["run_api.py", "main.py", "app.py", "server.py", "run.py"]
        launch_script = None
        for c in candidates:
            if (self.install_path / c).exists():
                launch_script = c
                break

        if not launch_script:
            return {"name": "bat", "success": False,
                    "message": "Script de lancement non detecte (run_api.py, main.py...)"}

        bat_name = f"start_{self.app_id}.bat"
        bat_path = self.install_path / bat_name

        venv_activate = str(self.venv_path / "Scripts" / "activate.bat")
        bat_content = (
            "@echo off\r\n"
            f"title {self.app_id.title()} - AION App\r\n"
            "echo.\r\n"
            f"echo  === {self.app_id.title()} - AION App ===\r\n"
            "echo.\r\n"
            f"cd /d \"{self.install_path}\"\r\n"
            "\r\n"
            ":: Activer le venv\r\n"
            f"if exist \".venv\\Scripts\\activate.bat\" (\r\n"
            f"    call .venv\\Scripts\\activate.bat\r\n"
            ") else (\r\n"
            "    echo [WARN] Venv non trouve\r\n"
            ")\r\n"
            "\r\n"
            ":: Lancer l'app\r\n"
            f"echo  Demarrage {self.app_id}...\r\n"
            f"python {launch_script}\r\n"
            "\r\n"
            "pause\r\n"
        )
        try:
            bat_path.write_text(bat_content, encoding="utf-8")
            logger.info("Bat genere : %s", bat_path)
            return {"name": "bat", "success": True,
                    "message": f"Bat genere : {bat_name} (lance: {launch_script})",
                    "bat_path": str(bat_path),
                    "launch_script": launch_script}
        except Exception as e:
            return {"name": "bat", "success": False, "message": str(e)}

    def get_launch_command(self) -> list[str]:
        """
        Retourne la commande optimale pour lancer l'app.
        Priorite : venv python > systeme python.
        """
        candidates = ["run_api.py", "main.py", "app.py", "server.py", "run.py"]
        script = None
        for c in candidates:
            if (self.install_path / c).exists():
                script = c
                break

        python_exe = str(self.venv_python) if self.venv_python.exists() else sys.executable
        return [python_exe, script or "main.py"]

    def scan_data_after_run(self) -> list[str]:
        """
        Re-scanne les fichiers persistants apres un premier lancement.
        Utile car data/ et *.db n'existent qu'apres que l'app a tourne une fois.
        Appele automatiquement par /api/store/scan/{app_id}.
        """
        from aion_core.store.app_store import _scan_appdata_files
        return _scan_appdata_files(str(self.install_path))
