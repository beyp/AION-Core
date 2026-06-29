"""
AppStore -- Gestionnaire d'installation et de mise a jour des apps AION.

C:/AION_APPS/
  repos/<AppName>/      <- git clone
  appdata/<app_id>/     <- fichiers persistants (memory.json, *.db, *.sqlite...)
  backups/               <- zips horodates avant chaque update
  .aion/apps_store.json  <- manifest local

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


def _force_remove(path) -> tuple[bool, str]:
    """
    Supprime un dossier de maniere robuste sur Windows.
    Gere les fichiers read-only (.git/objects/...) et les processus qui tiennent des fichiers.

    Strategie :
    1. shutil.rmtree avec handler onerror (retire les attributs read-only)
    2. Si echec -> rd /s /q (commande Windows native)
    3. Verifier que le dossier n'existe plus

    Returns:
        (success: bool, error_message: str)
    """
    import shutil
    import stat
    import subprocess
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return True, ""

    def _remove_readonly(func, fpath, _):
        """Retire les attributs read-only avant suppression."""
        try:
            import os
            os.chmod(fpath, stat.S_IWRITE | stat.S_IREAD)
            func(fpath)
        except Exception:
            pass

    # Tentative 1 : shutil.rmtree avec onerror
    try:
        shutil.rmtree(str(p), onerror=_remove_readonly)
    except Exception:
        pass

    if not p.exists():
        return True, ""

    # Tentative 2 : rd /s /q (force Windows)
    try:
        result = subprocess.run(
            ["cmd", "/c", "rd", "/s", "/q", str(p)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=30
        )
        if not p.exists():
            return True, ""
        err = result.stderr.strip() or result.stdout.strip() or "rd /s /q a echoue"
        return False, err
    except Exception as e:
        return False, str(e)


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

        1. git clone dans C:/AION_APPS/repos/
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
        # Utiliser C:/code/python/[App] si le dossier existe deja (repo local)
        # Sinon git clone dans C:/code/python/[App]
        install_path = self.code_root / repo_name

        # Deja installe ?
        # On verifie le dossier ET le status dans apps.local.json
        app_status = self._registry.get("apps", {}).get(app_id, {}).get("status", "")
        if install_path.exists():
            if app_status in ("active", "installed"):
                return {
                    "success":      False,
                    "message":      f"'{app_id}' est deja installe dans {install_path}. Utilise update() pour mettre a jour.",
                    "install_path": str(install_path),
                }
            else:
                # status == "uninstalled" ou inconnu : dossier residuel -> on force la suppression
                logger.info("Nettoyage dossier residuel (status=%r): %s", app_status, install_path)
                ok, err = _force_remove(install_path)
                if not ok:
                    _err_msg = (
                        f"Impossible de supprimer {install_path}: {err}. "
                        f"Supprime manuellement: cmd /c rd /s /q {install_path}"
                    )
                    return {"success": False, "message": _err_msg}
                logger.info("Dossier residuel supprime: %s", install_path)

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

        # Configuration specifique a chaque app
        appdata_path = str(self.root / "appdata" / app_id)
        self._configure_app_env(app_id, str(install_path), appdata_path)

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
            "appdata_path":  str(self.root / "appdata" / app_id),  # AION_APPS/appdata/[app]
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

        # Injecter DATA_DIR -> C:/AION_APPS/appdata/<app_id>
        # L'app peut utiliser os.getenv("AION_DATA_DIR") pour stocker ses fichiers
        appdata_path = str(self.root / "appdata" / app_id)
        Path(appdata_path).mkdir(parents=True, exist_ok=True)
        _env = _autostart.setdefault("env", {})
        _env["AION_DATA_DIR"]  = appdata_path
        _env["AION_APP_ID"]    = app_id
        _env["AION_APPS_ROOT"] = str(self.root)

        apps[app_id]["autostart"] = _autostart
        logger.info("Autostart configure pour %s: cmd=%s  DATA_DIR=%s", app_id, _cmd, appdata_path)

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
                    import subprocess, time
                    proc = subprocess.run(["netstat", "-ano"],
                                         capture_output=True, text=True,
                                         encoding="utf-8", errors="replace")
                    for line in (proc.stdout or "").splitlines():
                        if f":{port} " in line and "LISTENING" in line:
                            parts = line.split()
                            if parts:
                                subprocess.run(["taskkill", "/PID", parts[-1], "/F"],
                                               capture_output=True)
                                logger.info("Process arrete sur port %d avant suppression", port)
                            break
                    time.sleep(1)  # laisser le temps au process de se terminer
                except Exception as e:
                    logger.warning("Stop process avant uninstall: %s", e)

            # 2. Supprimer avec _force_remove (gere read-only + rd /s /q)
            deleted, delete_error = _force_remove(install_path)
            if deleted:
                logger.info("Repo supprime: %s", install_path)
            else:
                logger.error("Echec suppression repo %s: %s", install_path, delete_error)

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

    def _configure_app_env(self, app_id: str, install_path: str,
                            appdata_path: str) -> None:
        """
        Configure les fichiers d'environnement de l'app pour pointer
        les donnees vers appdata/ au lieu du repo.

        - QuickMind   : config.example.yaml -> config.yaml (DB dans appdata/)
        - ProjectMind : .env avec DB_PATH=appdata/projectmind.db
        - Toutes apps : AION_DATA_DIR dans autostart.env
        """
        import re, shutil as _sh
        root     = Path(install_path)
        data_dir = Path(appdata_path)
        data_dir.mkdir(parents=True, exist_ok=True)

        # QuickMind : config.yaml avec chemins ABSOLUS vers appdata/
        # QuickMind lit config.yaml et utilise database.path comme chemin DB
        config_example = root / "config.example.yaml"
        config_file    = root / "config.yaml"

        # Lire config.yaml existant OU config.example.yaml comme base
        base_config    = config_file if config_file.exists() else config_example
        if base_config.exists():
            try:
                content = base_config.read_text(encoding="utf-8")

                # Chemin absolu DB → appdata/quickmind.db
                db_abs = str(data_dir / "quickmind.db").replace("\\", "/")
                # Remplacer database.path (relatif ou absolu)
                content = re.sub(
                    r'(database:\s*\n\s+path:\s*)[^\n]+',
                    f'\\g<1>"{db_abs}"',
                    content
                )
                # Si le pattern simple "path:" existe
                content = re.sub(
                    r'(^\s*path:\s*)"data/quickmind\.db"',
                    f'\\g<1>"{db_abs}"',
                    content, flags=re.MULTILINE
                )

                # Chemin absolu attachments → appdata/attachments/
                attach_abs = str(data_dir / "attachments").replace("\\", "/")
                content = re.sub(
                    r'(^\s*path:\s*)"data/attachments"',
                    f'\\g<1>"{attach_abs}"',
                    content, flags=re.MULTILINE
                )

                # Toujours écrire config.yaml dans le REPO (QuickMind le lit là)
                config_file.write_text(content, encoding="utf-8")
                # ET en copie dans appdata/ pour backup
                (data_dir / "config.yaml").write_text(content, encoding="utf-8")

                logger.info("config.yaml configure: DB=%s, attachments=%s",
                            db_abs, attach_abs)
            except Exception as e:
                logger.warning("Config QuickMind %s: %s", app_id, e)

        # .env : creer depuis .env.example + injecter DB_PATH ABSOLU vers appdata/
        env_example = root / ".env.example"
        env_file    = root / ".env"
        # DB dans appdata/ avec chemin absolu (forward slashes pour Python)
        db_env_path = str(data_dir / f"{app_id}.db").replace("\\", "/")

        if env_example.exists() and not env_file.exists():
            try:
                _sh.copy2(str(env_example), str(env_file))
                logger.info(".env cree depuis .env.example pour %s", app_id)
            except Exception as e:
                logger.warning(".env copy %s: %s", app_id, e)

        if env_file.exists():
            try:
                content_env = env_file.read_text(encoding="utf-8")
                lines_env   = content_env.splitlines()
                # Construire un dict des clés existantes
                existing    = {}
                for l in lines_env:
                    if "=" in l and not l.startswith("#"):
                        k, _, v = l.partition("=")
                        existing[k.strip()] = v.strip()

                # Mettre à jour ou ajouter DB_PATH (chemin absolu)
                new_lines_env = []
                db_path_set   = False
                aion_dir_set  = False
                for l in lines_env:
                    if l.startswith("DB_PATH=") or l.startswith("DB_PATH ="):
                        new_lines_env.append(f"DB_PATH={db_env_path}")
                        db_path_set = True
                    elif l.startswith("AION_DATA_DIR="):
                        new_lines_env.append(f"AION_DATA_DIR={str(data_dir).replace(chr(92), '/')}")
                        aion_dir_set = True
                    else:
                        new_lines_env.append(l)

                # Ajouter si absents
                extras = []
                if not db_path_set:
                    extras.append(f"DB_PATH={db_env_path}")
                if not aion_dir_set:
                    extras.append(f"AION_DATA_DIR={str(data_dir).replace(chr(92), '/')}")
                if extras:
                    new_lines_env.append("")
                    new_lines_env.append("# Added by AION-Core AppStore — DB dans appdata/")
                    new_lines_env.extend(extras)

                env_file.write_text("\n".join(new_lines_env), encoding="utf-8")
                logger.info(".env configure: DB_PATH=%s", db_env_path)
            except Exception as e:
                logger.warning(".env update %s: %s", app_id, e)

        # Injecter AION_DATA_DIR dans autostart.env du registre
        apps = self._registry.get("apps", {})
        if app_id in apps:
            env = apps[app_id].setdefault("autostart", {}).setdefault("env", {})
            env["AION_DATA_DIR"] = str(data_dir).replace("\\", "/")
            env["AION_APP_ID"]   = app_id


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