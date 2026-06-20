"""
AppStore -- Gestionnaire d'installation et de mise a jour des apps AION.

Responsabilite :
- install(github_repo)    -> git clone dans C:\AION_APPS\repos\
- update(app_id)          -> backup appdata + git pull
- uninstall(app_id)       -> supprime le repo (garde appdata)
- restore_appdata(app_id) -> recopie les fichiers persistants apres clone
- status()                -> etat de toutes les apps installees

Chaque app dans apps.json peut avoir un champ "store" :
{
  "install_path":  "C:\\AION_APPS\\repos\\QuickMind",
  "appdata_path":  "C:\\AION_APPS\\appdata\\quickmind",
  "appdata_files": ["memory.json", "data/tasks.db"],
  "github":        "beyp/QuickMind",
  "installed_at":  "2026-06-20",
  "last_update":   "2026-06-20"
}

Usage :
    store = AppStore()
    store.install("beyp/QuickMind")
    store.update("quickmind")
    store.restore_appdata("quickmind")
"""
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from aion_core.store.appdata_manager import AppDataManager

logger = logging.getLogger(__name__)

AION_APPS_ROOT = Path(os.getenv("AION_APPS_ROOT", r"C:\AION_APPS"))
REPOS_DIR      = AION_APPS_ROOT / "repos"
STORE_MANIFEST = AION_APPS_ROOT / ".aion" / "apps_store.json"
REGISTRY_FILE  = Path("apps.json")


class AppStore:
    """Gestionnaire d'installation des apps AION via GitHub."""

    def __init__(self, registry_path: str = "apps.json", root: str | None = None) -> None:
        self.root          = Path(root) if root else AION_APPS_ROOT
        self.repos_dir     = self.root / "repos"
        self.registry_path = Path(registry_path)
        self.appdata_mgr   = AppDataManager(root=str(self.root))
        self._registry     = self._load_registry()
        self._manifest     = self._load_manifest()

        # Creer les dossiers de base
        self.repos_dir.mkdir(parents=True, exist_ok=True)
        (self.root / ".aion").mkdir(parents=True, exist_ok=True)

    # -- Registry / Manifest ---------------------------------------------------

    def _load_registry(self) -> dict:
        if self.registry_path.exists():
            try:
                with open(self.registry_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"version": "1.0", "apps": {}}

    def _save_registry(self) -> None:
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=2, ensure_ascii=False)

    def _load_manifest(self) -> dict:
        manifest_path = self.root / ".aion" / "apps_store.json"
        if manifest_path.exists():
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"version": "1.0", "installed": {}}

    def _save_manifest(self) -> None:
        manifest_path = self.root / ".aion" / "apps_store.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self._manifest, f, indent=2, ensure_ascii=False)

    # -- API publique ----------------------------------------------------------

    def install(self, github_repo: str, app_id: str | None = None,
                appdata_files: list[str] | None = None) -> dict:
        """
        Installe une app depuis GitHub via git clone.

        Args:
            github_repo:   Format "owner/repo" (ex: "beyp/QuickMind")
            app_id:        ID de l'app (auto-detecte si None)
            appdata_files: Fichiers persistants a gerer (ex: ["memory.json"])

        Returns:
            {"success": bool, "message": str, "install_path": str}
        """
        if not app_id:
            app_id = github_repo.split("/")[-1].lower().replace("-", "_")

        repo_name    = github_repo.split("/")[-1]
        install_path = self.repos_dir / repo_name

        # Deja installe ?
        if install_path.exists():
            return {
                "success":      False,
                "message":      f"'{app_id}' est deja installe dans {install_path}. Utilise update() pour mettre a jour.",
                "install_path": str(install_path),
            }

        # git clone
        clone_url = f"https://github.com/{github_repo}.git"
        logger.info("git clone %s -> %s", clone_url, install_path)
        result = self._run_git(["git", "clone", clone_url, str(install_path)])
        if not result["success"]:
            return result

        today = datetime.now().strftime("%Y-%m-%d")

        # Restaurer appdata si existant (reinstallation)
        files_to_manage = appdata_files or []
        restore_result  = None
        if files_to_manage:
            restore_result = self.appdata_mgr.restore(app_id, str(install_path), files_to_manage)
            logger.info("AppData restore after clone: %s", restore_result)

        # Mettre a jour apps.json
        apps = self._registry.setdefault("apps", {})
        if app_id not in apps:
            apps[app_id] = {
                "name":      repo_name,
                "type":      "fastapi",
                "status":    "installed",
                "github":    github_repo,
                "autostart": {"enabled": False},
            }

        apps[app_id]["store"] = {
            "install_path":  str(install_path),
            "appdata_path":  str(self.root / "appdata" / app_id),
            "appdata_files": files_to_manage,
            "github":        github_repo,
            "installed_at":  today,
            "last_update":   today,
        }
        # Mettre a jour autostart.path si present
        autostart = apps[app_id].get("autostart", {})
        if autostart.get("enabled") or autostart.get("mode"):
            autostart["path"] = str(install_path)

        self._save_registry()

        # Mettre a jour le manifest local
        self._manifest["installed"][app_id] = {
            "github":       github_repo,
            "install_path": str(install_path),
            "installed_at": today,
            "last_update":  today,
        }
        self._save_manifest()

        msg = f"'{app_id}' installe depuis {github_repo} dans {install_path}"
        if restore_result and restore_result.get("restored"):
            msg += f" | AppData restaure: {restore_result['restored']}"

        logger.info(msg)
        return {
            "success":      True,
            "app_id":       app_id,
            "install_path": str(install_path),
            "message":      msg,
        }

    def update(self, app_id: str) -> dict:
        """
        Met a jour une app via git pull.
        Sauvegarde automatiquement l'appdata avant la mise a jour.

        Args:
            app_id: ID de l'app (ex: "quickmind")

        Returns:
            {"success": bool, "message": str, "backup_path": str}
        """
        store_cfg = self._get_store_cfg(app_id)
        if not store_cfg:
            return {"success": False, "message": f"App '{app_id}' non trouvee ou pas installee via AppStore"}

        install_path  = Path(store_cfg["install_path"])
        appdata_files = store_cfg.get("appdata_files", [])

        if not install_path.exists():
            return {
                "success": False,
                "message": f"Repertoire introuvable: {install_path}. Reinstalle avec install().",
            }

        # 1. Sauvegarder appdata + backup zip
        backup_result = None
        if appdata_files:
            self.appdata_mgr.save(app_id, str(install_path), appdata_files)
            backup_result = self.appdata_mgr.backup(app_id)
            logger.info("Pre-update backup: %s", backup_result)

        # 2. git pull
        logger.info("git pull %s", install_path)
        result = self._run_git(["git", "pull"], cwd=str(install_path))
        if not result["success"]:
            return result

        # 3. Restaurer appdata apres pull (au cas ou git pull aurait ecrase)
        restore_result = None
        if appdata_files:
            restore_result = self.appdata_mgr.restore(app_id, str(install_path), appdata_files)

        # 4. Mettre a jour les dates
        today = datetime.now().strftime("%Y-%m-%d")
        store_cfg["last_update"] = today
        if app_id in self._manifest.get("installed", {}):
            self._manifest["installed"][app_id]["last_update"] = today
        self._save_registry()
        self._save_manifest()

        msg = f"'{app_id}' mis a jour (git pull OK)"
        if backup_result and backup_result.get("success"):
            msg += f" | Backup: {Path(backup_result['backup_path']).name}"
        if restore_result and restore_result.get("restored"):
            msg += f" | AppData restaure: {restore_result['restored']}"

        return {
            "success":     True,
            "app_id":      app_id,
            "message":     msg,
            "backup_path": backup_result.get("backup_path", "") if backup_result else "",
            "git_output":  result.get("output", ""),
        }

    def uninstall(self, app_id: str, keep_appdata: bool = True) -> dict:
        """
        Desinstalle une app (supprime le repo, garde l'appdata par defaut).

        Args:
            app_id:       ID de l'app
            keep_appdata: Si True, conserve C:\AION_APPS\appdata\<app_id>

        Returns:
            {"success": bool, "message": str}
        """
        store_cfg = self._get_store_cfg(app_id)
        if not store_cfg:
            return {"success": False, "message": f"App '{app_id}' non trouvee"}

        install_path  = Path(store_cfg["install_path"])
        appdata_files = store_cfg.get("appdata_files", [])

        # Sauvegarder l'appdata avant de supprimer
        if keep_appdata and appdata_files and install_path.exists():
            self.appdata_mgr.save(app_id, str(install_path), appdata_files)
            self.appdata_mgr.backup(app_id)
            logger.info("AppData sauvegarde avant desinstallation de %s", app_id)

        # Supprimer le repertoire repo
        if install_path.exists():
            import shutil
            shutil.rmtree(install_path, ignore_errors=True)
            logger.info("Repo supprime: %s", install_path)

        # Mettre a jour apps.json
        apps = self._registry.get("apps", {})
        if app_id in apps:
            apps[app_id]["status"] = "uninstalled"
            apps[app_id].pop("store", None)
            self._save_registry()

        # Mettre a jour le manifest
        self._manifest.get("installed", {}).pop(app_id, None)
        self._save_manifest()

        msg = f"'{app_id}' desinstalle"
        if keep_appdata:
            msg += f" (appdata conserve dans {self.root / 'appdata' / app_id})"
        return {"success": True, "message": msg}

    def restore_appdata(self, app_id: str) -> dict:
        """
        Restaure les fichiers persistants depuis appdata/ vers le repo.
        Utile apres un git clone manuel ou une reinstallation.
        """
        store_cfg = self._get_store_cfg(app_id)
        if not store_cfg:
            return {"success": False, "message": f"App '{app_id}' non trouvee"}

        return self.appdata_mgr.restore(
            app_id,
            store_cfg["install_path"],
            store_cfg.get("appdata_files", []),
        )

    def register_appdata_file(self, app_id: str, filename: str) -> dict:
        """
        Declare un nouveau fichier a persister pour une app.
        Immediatement sauvegarde dans appdata/ si le fichier existe.

        Args:
            app_id:   ID de l'app
            filename: Chemin relatif (ex: "memory.json", "data/tasks.db")
        """
        store_cfg = self._get_store_cfg(app_id)
        if not store_cfg:
            return {"success": False, "message": f"App '{app_id}' non trouvee"}

        files = store_cfg.setdefault("appdata_files", [])
        if filename not in files:
            files.append(filename)
            self._save_registry()

        # Sauvegarder immediatement si le fichier existe
        install_path = store_cfg.get("install_path", "")
        if install_path:
            self.appdata_mgr.save(app_id, install_path, [filename])

        return {
            "success":       True,
            "message":       f"Fichier '{filename}' enregistre pour '{app_id}'",
            "appdata_files": files,
        }

    def status(self) -> list[dict]:
        """Retourne l'etat de toutes les apps gerees par l'AppStore."""
        results = []
        for app_id, cfg in self._registry.get("apps", {}).items():
            store = cfg.get("store")
            if not store:
                continue
            install_path = Path(store.get("install_path", ""))
            is_cloned    = install_path.exists()
            results.append({
                "app_id":        app_id,
                "name":          cfg.get("name", app_id),
                "github":        store.get("github", ""),
                "install_path":  str(install_path),
                "is_cloned":     is_cloned,
                "appdata_files": store.get("appdata_files", []),
                "installed_at":  store.get("installed_at", ""),
                "last_update":   store.get("last_update", ""),
                "backups":       self.appdata_mgr.list_backups(app_id),
            })
        return results

    def list_appdata(self, app_id: str) -> list[str]:
        """Liste les fichiers dans appdata/ pour une app."""
        return self.appdata_mgr.list_appdata(app_id)

    # -- Helpers ---------------------------------------------------------------

    def _get_store_cfg(self, app_id: str) -> dict | None:
        """Retourne la config store d'une app depuis apps.json."""
        app = self._registry.get("apps", {}).get(app_id)
        if not app:
            return None
        return app.get("store")

    def _run_git(self, cmd: list[str], cwd: str | None = None) -> dict:
        """Execute une commande git et retourne le resultat."""
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                return {
                    "success": False,
                    "message": f"Erreur git: {proc.stderr.strip()[:300]}",
                    "output":  proc.stdout.strip(),
                }
            return {
                "success": True,
                "output":  proc.stdout.strip() or proc.stderr.strip(),
            }
        except FileNotFoundError:
            return {"success": False, "message": "Git non trouve. Installe Git et assure-toi qu'il est dans le PATH."}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Timeout git (>120s). Verifie ta connexion reseau."}
        except Exception as e:
            return {"success": False, "message": f"Erreur: {e}"}
