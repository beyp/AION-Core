"""
AppStore -- Gestionnaire d'installation et de mise a jour des apps AION.

C:\AION_APPS\
  repos\<AppName>\      <- git clone
  appdata\<app_id>\     <- fichiers persistants (memory.json, *.db, *.sqlite...)
  backups\               <- zips horodates avant chaque update
  .aion\apps_store.json  <- manifest local

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
REGISTRY_FILE      = Path("apps.json")        # built-in apps (git-tracked)
LOCAL_REGISTRY_FILE = Path("apps.local.json")  # personal apps (git-ignored)

# Extensions et noms de fichiers qui doivent etre persistes automatiquement
PERSISTENT_EXTENSIONS = {".db", ".sqlite", ".sqlite3", ".json", ".env", ".key", ".csv"}
PERSISTENT_NAMES      = {"memory.json", ".env", "config.json", "settings.json",
                          "secrets.json", "tokens.json", "data.json"}
PERSISTENT_DIRS       = {"data", "db", "storage", "appdata", "userdata"}
EXCLUDED_NAMES        = {"requirements.txt", "package.json", "package-lock.json",
                          "apps.json", "README.json"}


def _scan_appdata_files(install_path: str) -> list[str]:
    """
    Scanne un repo installe et detecte automatiquement les fichiers
    qui doivent etre persistes dans appdata/.

    Logique :
    - Fichiers .db / .sqlite* a la racine ou dans data/, db/, storage/
    - Fichiers .json avec noms connus (memory.json, config.json, ...)
    - Fichiers .env a la racine
    - Tout fichier dans les dossiers data/, db/, storage/

    Returns:
        Liste de chemins relatifs (ex: ["memory.json", "data/quickmind.db"])
    """
    root    = Path(install_path)
    found   = set()

    if not root.exists():
        return []

    # Parcourir le repo (profondeur max 3)
    for item in root.rglob("*"):
        if not item.is_file():
            continue

        rel = item.relative_to(root)
        parts = rel.parts

        # Exclure .git, __pycache__, node_modules, .venv
        if any(p.startswith(".git") or p in ("__pycache__", "node_modules",
               ".venv", "venv", "dist", "build") for p in parts):
            continue

        # Exclure les fichiers exclus
        if item.name in EXCLUDED_NAMES:
            continue

        rel_str = str(rel).replace("\\", "/")

        # Regle 1 : extensions persistantes
        if item.suffix.lower() in PERSISTENT_EXTENSIONS:
            # .json seulement si nom connu ou dans dossier data
            if item.suffix.lower() == ".json":
                if item.name in PERSISTENT_NAMES or (len(parts) > 1 and parts[0] in PERSISTENT_DIRS):
                    found.add(rel_str)
            else:
                found.add(rel_str)

        # Regle 2 : noms connus directement
        if item.name in PERSISTENT_NAMES:
            found.add(rel_str)

        # Regle 3 : tout fichier dans un dossier persistant
        if len(parts) > 1 and parts[0] in PERSISTENT_DIRS:
            found.add(rel_str)

    return sorted(found)


class AppStore:
    """Gestionnaire d'installation des apps AION via GitHub."""

    def __init__(self, registry_path: str = "apps.local.json", root: str | None = None) -> None:
        self.root          = Path(root) if root else AION_APPS_ROOT
        self.repos_dir     = self.root / "repos"
        # AppStore ecrit toujours dans apps.local.json (git-ignored)
        self.registry_path = Path(registry_path)
        self.appdata_mgr   = AppDataManager(root=str(self.root))
        self._registry     = self._load_registry()
        self._manifest     = self._load_manifest()

        self.repos_dir.mkdir(parents=True, exist_ok=True)
        (self.root / ".aion").mkdir(parents=True, exist_ok=True)

    # ── Registry / Manifest ───────────────────────────────────────

    def _load_registry(self) -> dict:
        """
        Charge apps.local.json.
        Si inexistant, le cree comme copie de apps.local.json.example
        ou comme registre vide.
        """
        if self.registry_path.exists():
            try:
                with open(self.registry_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # Creer apps.local.json vide si absent
        empty = {"version": "1.0", "apps": {}}
        try:
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump(empty, f, indent=2, ensure_ascii=False)
            logger.info("apps.local.json cree (premier demarrage AppStore)")
        except Exception as e:
            logger.warning("Impossible de creer apps.local.json: %s", e)
        return empty

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

    # ── API publique ──────────────────────────────────────────────

    def install(self, github_repo: str, app_id: str | None = None,
                appdata_files: list[str] | None = None) -> dict:
        """
        Installe une app depuis GitHub via git clone.

        1. git clone dans C:\AION_APPS\repos\
        2. Scan auto des fichiers persistants (si appdata_files non fourni)
        3. Restaure appdata/ si une installation precedente existait
        4. Met a jour apps.json (status, install_path, url, appdata_files)

        Args:
            github_repo:   "owner/repo" (ex: "beyp/QuickMind")
            app_id:        ID de l'app (auto-detecte si None)
            appdata_files: Fichiers a persister -- si None, scan automatique
        """
        if not app_id:
            app_id = github_repo.split("/")[-1].lower().replace("-", "_")

        repo_name    = github_repo.split("/")[-1]
        install_path = self.repos_dir / repo_name

        # Deja installe ?
        # On verifie le dossier ET le status dans apps.json
        app_status = self._registry.get("apps", {}).get(app_id, {}).get("status", "")
        if install_path.exists():
            if app_status == "uninstalled":
                # Reinstallation apres uninstall : dossier pas bien supprime -> on nettoie
                import shutil
                shutil.rmtree(install_path, ignore_errors=True)
                logger.info("Nettoyage dossier residuel apres uninstall: %s", install_path)
            elif app_status in ("active", "installed"):
                return {
                    "success":      False,
                    "message":      f"'{app_id}' est deja installe dans {install_path}. Utilise update() pour mettre a jour.",
                    "install_path": str(install_path),
                }
            else:
                # Dossier existe mais status inconnu -> on nettoie et on reinstalle
                import shutil
                shutil.rmtree(install_path, ignore_errors=True)
                logger.info("Nettoyage dossier orphelin (status=%s): %s", app_status, install_path)

        # git clone
        clone_url = f"https://github.com/{github_repo}.git"
        logger.info("git clone %s -> %s", clone_url, install_path)
        git_result = self._run_git(["git", "clone", clone_url, str(install_path)])
        if not git_result["success"]:
            return git_result

        today = datetime.now().strftime("%Y-%m-%d")

        # Scan automatique des fichiers persistants si non fournis
        if appdata_files is None:
            files_to_manage = _scan_appdata_files(str(install_path))
            logger.info("AppData scan auto pour %s: %s", app_id, files_to_manage)
        else:
            files_to_manage = appdata_files

        # Setup complet : venv + pip + appdata init + bat
        from aion_core.store.app_setup import AppSetup
        setup = AppSetup(app_id, str(install_path), self.appdata_mgr)
        setup_result = setup.run(files_to_manage)
        logger.info("Setup %s: %s", app_id, setup_result.get("message"))

        restore_result = None  # gere par AppSetup._init_appdata

        # Mettre a jour apps.json
        # IMPORTANT : on met a jour meme si l'app existait deja dans apps.json
        apps = self._registry.setdefault("apps", {})
        if app_id not in apps:
            # Nouvelle app inconnue
            apps[app_id] = {
                "name":      repo_name,
                "type":      "fastapi",
                "status":    "installed",
                "github":    github_repo,
                "url":       "",
                "icon":      "package",
                "autostart": {"enabled": False},
            }
        else:
            # App existante : on met a jour les champs store sans ecraser les autres
            pass

        # Toujours mettre a jour le champ store et le status
        apps[app_id]["status"] = "installed"
        apps[app_id]["store"]  = {
            "install_path":  str(install_path),
            "appdata_path":  str(self.root / "appdata" / app_id),
            "appdata_files": files_to_manage,
            "github":        github_repo,
            "installed_at":  today,
            "last_update":   today,
            "auto_detected": appdata_files is None,
        }

        # Configurer autostart avec la commande auto-detectee
        from aion_core.store.app_setup import AppSetup
        _setup    = AppSetup(app_id, str(install_path))
        _cmd      = _setup.get_launch_command()
        _autostart = apps[app_id].setdefault("autostart", {})
        _autostart["enabled"]      = True
        _autostart["mode"]         = _autostart.get("mode", "fastapi")
        _autostart["path"]         = str(install_path)
        _autostart["command"]      = [str(c) for c in _cmd]
        _autostart["health_check"] = False   # non bloquant
        if not _autostart.get("port"):
            _autostart["port"]     = 8765    # port par defaut
        apps[app_id]["autostart"] = _autostart
        logger.info("Autostart configure pour %s: %s", app_id, _cmd)

        self._save_registry()

        # Manifest local
        self._manifest.setdefault("installed", {})[app_id] = {
            "github":       github_repo,
            "install_path": str(install_path),
            "installed_at": today,
            "last_update":  today,
        }
        self._save_manifest()

        msg = f"'{app_id}' installe depuis {github_repo}"
        if files_to_manage:
            msg += f" | Appdata: {files_to_manage}"

        logger.info(msg)
        return {
            "success":        True,
            "app_id":         app_id,
            "install_path":   str(install_path),
            "appdata_files":  files_to_manage,
            "auto_detected":  appdata_files is None,
            "setup":          setup_result,
            "bat_path":       setup_result.get("bat_path", ""),
            "message":        msg,
        }

    def update(self, app_id: str) -> dict:
        """
        Met a jour une app via git pull.
        1. Sauvegarde appdata/ (copy + zip backup)
        2. git pull
        3. Restaure appdata/ dans le repo
        4. Re-scanne les nouveaux fichiers persistants si auto_detected=True
        """
        store_cfg = self._get_store_cfg(app_id)
        if not store_cfg:
            return {"success": False, "message": f"App '{app_id}' non trouvee ou pas installee via AppStore"}

        install_path  = Path(store_cfg["install_path"])
        appdata_files = store_cfg.get("appdata_files", [])
        auto_detected = store_cfg.get("auto_detected", False)

        if not install_path.exists():
            return {"success": False,
                    "message": f"Repertoire introuvable: {install_path}. Reinstalle avec install()."}

        # 1. Sauvegarder appdata avant pull
        backup_result = None
        if appdata_files:
            self.appdata_mgr.save(app_id, str(install_path), appdata_files)
            backup_result = self.appdata_mgr.backup(app_id)
            logger.info("Pre-update backup: %s", backup_result)

        # 2. git pull
        logger.info("git pull %s", install_path)
        git_result = self._run_git(["git", "pull"], cwd=str(install_path))
        if not git_result["success"]:
            return git_result

        # 3. Re-scanner si auto_detected (le repo a peut-etre de nouveaux fichiers)
        if auto_detected:
            new_files = _scan_appdata_files(str(install_path))
            if set(new_files) != set(appdata_files):
                logger.info("Nouveaux fichiers detectes apres pull: %s", new_files)
                appdata_files = new_files
                store_cfg["appdata_files"] = new_files

        # 4. Restaurer appdata
        restore_result = None
        if appdata_files:
            restore_result = self.appdata_mgr.restore(app_id, str(install_path), appdata_files)

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
            "git_output":  git_result.get("output", ""),
            "appdata_files": appdata_files,
        }

    def uninstall(self, app_id: str, keep_appdata: bool = True) -> dict:
        """Desinstalle (supprime repo, garde appdata par defaut)."""
        store_cfg = self._get_store_cfg(app_id)
        if not store_cfg:
            return {"success": False, "message": f"App '{app_id}' non trouvee"}

        install_path  = Path(store_cfg["install_path"])
        appdata_files = store_cfg.get("appdata_files", [])

        if keep_appdata and appdata_files and install_path.exists():
            self.appdata_mgr.save(app_id, str(install_path), appdata_files)
            self.appdata_mgr.backup(app_id)

        deleted = False
        delete_error = ""
        if install_path.exists():
            # 1. Stopper l'app si elle tourne (liberer les fichiers verrouilles)
            port = self._registry.get("apps", {}).get(app_id, {}) \
                       .get("autostart", {}).get("port", 0)
            if port:
                try:
                    import subprocess
                    proc = subprocess.run(["netstat", "-ano"],
                                         capture_output=True, text=True,
                                         encoding="utf-8", errors="replace")
                    stdout = proc.stdout or ""
                    for line in stdout.splitlines():
                        if f":{port} " in line and "LISTENING" in line:
                            parts = line.split()
                            if parts:
                                subprocess.run(["taskkill", "/PID", parts[-1], "/F"],
                                               capture_output=True)
                                logger.info("Process arrete sur port %d avant suppression", port)
                            break
                    import time
                    time.sleep(0.5)  # laisser le temps au process de se terminer
                except Exception as e:
                    logger.warning("Stop process avant uninstall: %s", e)

            # 2. Supprimer avec gestion des fichiers read-only Windows (.git)
            import shutil, stat

            def _remove_readonly(func, path, _):
                """Handler pour retirer les attributs read-only avant suppression."""
                try:
                    import os
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass

            try:
                shutil.rmtree(str(install_path), onerror=_remove_readonly)
                if not install_path.exists():
                    deleted = True
                    logger.info("Repo supprime: %s", install_path)
                else:
                    # Dernier recours : rd /s /q via cmd Windows
                    import subprocess
                    result = subprocess.run(
                        ["cmd", "/c", "rd", "/s", "/q", str(install_path)],
                        capture_output=True, text=True, timeout=30
                    )
                    deleted = not install_path.exists()
                    if not deleted:
                        delete_error = result.stderr.strip() or "rd /s /q a echoue"
            except Exception as e:
                delete_error = str(e)
                logger.error("Erreur suppression repo %s: %s", install_path, e)

        apps = self._registry.get("apps", {})
        if app_id in apps:
            apps[app_id]["status"] = "uninstalled"
            apps[app_id].pop("store", None)
            self._save_registry()

        self._manifest.get("installed", {}).pop(app_id, None)
        self._save_manifest()

        if deleted:
            msg = f"'{app_id}' desinstalle et repertoire supprime"
        elif delete_error:
            msg = f"'{app_id}' retire du registre MAIS repertoire non supprime: {delete_error[:100]}"
        else:
            msg = f"'{app_id}' desinstalle (repertoire n'existait pas)"

        if keep_appdata:
            msg += f" | appdata conserve dans C:\\AION_APPS\\appdata\\{app_id}"
        return {
            "success":  True,   # succes registre meme si dossier non supprime
            "deleted":  deleted,
            "message":  msg,
            "warning":  delete_error if delete_error and not deleted else "",
        }

    def restore_appdata(self, app_id: str) -> dict:
        """Restaure les fichiers persistants depuis appdata/ vers le repo."""
        store_cfg = self._get_store_cfg(app_id)
        if not store_cfg:
            return {"success": False, "message": f"App '{app_id}' non trouvee"}
        return self.appdata_mgr.restore(
            app_id, store_cfg["install_path"], store_cfg.get("appdata_files", []))

    def register_appdata_file(self, app_id: str, filename: str) -> dict:
        """Declare manuellement un fichier persistant pour une app."""
        store_cfg = self._get_store_cfg(app_id)
        if not store_cfg:
            return {"success": False, "message": f"App '{app_id}' non trouvee"}
        files = store_cfg.setdefault("appdata_files", [])
        if filename not in files:
            files.append(filename)
            store_cfg["auto_detected"] = False  # passage en mode manuel
            self._save_registry()
        install_path = store_cfg.get("install_path", "")
        if install_path:
            self.appdata_mgr.save(app_id, install_path, [filename])
        return {"success": True, "message": f"Fichier '{filename}' enregistre pour '{app_id}'",
                "appdata_files": files}

    def scan_appdata(self, app_id: str) -> dict:
        """
        Re-scanne les fichiers persistants d'une app installee.
        Utile si l'app a evolue et a de nouveaux fichiers de donnees.
        """
        store_cfg = self._get_store_cfg(app_id)
        if not store_cfg:
            return {"success": False, "message": f"App '{app_id}' non trouvee"}
        install_path = store_cfg.get("install_path", "")
        if not Path(install_path).exists():
            return {"success": False, "message": f"Repo non clone: {install_path}"}
        new_files = _scan_appdata_files(install_path)
        store_cfg["appdata_files"] = new_files
        store_cfg["auto_detected"] = True
        self._save_registry()
        return {"success": True, "app_id": app_id,
                "appdata_files": new_files,
                "message": f"{len(new_files)} fichier(s) detecte(s): {new_files}"}

    def status(self) -> list[dict]:
        """Retourne l'etat de toutes les apps gerees par l'AppStore."""
        results = []
        for app_id, cfg in self._registry.get("apps", {}).items():
            store = cfg.get("store")
            if not store:
                continue
            install_path = Path(store.get("install_path", ""))
            results.append({
                "app_id":        app_id,
                "name":          cfg.get("name", app_id),
                "github":        store.get("github", ""),
                "install_path":  str(install_path),
                "is_cloned":     install_path.exists(),
                "appdata_files": store.get("appdata_files", []),
                "auto_detected": store.get("auto_detected", False),
                "installed_at":  store.get("installed_at", ""),
                "last_update":   store.get("last_update", ""),
                "backups":       self.appdata_mgr.list_backups(app_id),
            })
        return results

    def list_appdata(self, app_id: str) -> list[str]:
        return self.appdata_mgr.list_appdata(app_id)

    # ── Helpers ───────────────────────────────────────────────────

    def _get_store_cfg(self, app_id: str) -> dict | None:
        app = self._registry.get("apps", {}).get(app_id)
        return app.get("store") if app else None

    def _run_git(self, cmd: list[str], cwd: str | None = None) -> dict:
        try:
            proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                return {"success": False,
                        "message": f"Erreur git: {proc.stderr.strip()[:300]}",
                        "output":  proc.stdout.strip()}
            return {"success": True, "output": proc.stdout.strip() or proc.stderr.strip()}
        except FileNotFoundError:
            return {"success": False, "message": "Git non trouve. Installe Git et assure-toi qu'il est dans le PATH."}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Timeout git (>120s). Verifie ta connexion reseau."}
        except Exception as e:
            return {"success": False, "message": f"Erreur: {e}"}
