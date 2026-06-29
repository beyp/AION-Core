"""
backup_manager.py -- Backup quotidien des donnees d\'app AION.

Source : C:/code/python/[App]/data/
Dest   : C:/AION_APPS/backups/[app]/data_backup_YYYY-MM-DD/
"""
import json
import logging
import os
import shutil
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

AION_APPS_ROOT = Path(os.getenv("AION_APPS_ROOT", "C:/AION_APPS"))
BACKUP_ROOT    = AION_APPS_ROOT / "backups"
CODE_ROOT      = Path(os.getenv("AION_CODE_ROOT", "C:/code/python"))

DEFAULT_PATTERNS = ["data", "*.db", "*.sqlite", ".env", "config.yaml", "config.yml", "settings.json"]


class BackupManager:
    """Backups quotidiens des apps AION vers AION_APPS/backups/."""

    def __init__(self) -> None:
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        self._stop   = threading.Event()
        self._thread = None

    # ── Backup ────────────────────────────────────────────────────

    def backup_app(self, app_id: str, install_path: str,
                   extra_files: list | None = None,
                   force: bool = False) -> dict:
        """
        Sauvegarde les donnees d\'une app.

        Args:
            app_id       : ex "quickmind"
            install_path : ex "C:/code/python/QuickMind"
            extra_files  : fichiers supplementaires relatifs a install_path
            force        : True = ecraser sans confirmation

        Returns dict avec success, backup_path, files_saved, already_existed.
        """
        root  = Path(install_path)
        today = datetime.now().strftime("%Y-%m-%d")
        dest  = BACKUP_ROOT / app_id / ("data_backup_" + today)

        if dest.exists() and not force:
            return {
                "success":        False,
                "already_existed": True,
                "confirmed":      False,
                "backup_path":    str(dest),
                "message":        ("Backup du " + today + " existe deja. "
                                   "Appelle avec force=True pour ecraser."),
            }

        files = self._collect(root, extra_files)
        if not files:
            return {"success": False, "message": "Aucun fichier a sauvegarder dans " + str(install_path)}

        if dest.exists():
            shutil.rmtree(str(dest), ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)

        saved, errors = [], []
        for src in files:
            rel = src.relative_to(root)
            dst = dest / rel
            try:
                if src.is_dir():
                    shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
                    saved.append(str(rel) + "/")
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    saved.append(str(rel))
            except Exception as e:
                errors.append(str(rel) + ": " + str(e))

        meta = {"app_id": app_id, "install_path": str(install_path),
                "date": today, "timestamp": datetime.now().isoformat(),
                "files_saved": saved, "errors": errors}
        (dest / "_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        msg = ("Backup " + app_id + ": " + str(len(saved))
               + " element(s) -> " + str(dest.name))
        if errors:
            msg += " | " + str(len(errors)) + " erreur(s)"
        logger.info(msg)
        return {"success": len(saved) > 0, "backup_path": str(dest),
                "files_saved": saved, "errors": errors,
                "already_existed": False, "confirmed": True, "message": msg}

    def _collect(self, root: Path, extra: list | None) -> list:
        found = set()
        for pat in DEFAULT_PATTERNS:
            for p in root.glob(pat):
                if ".venv" not in str(p) and "__pycache__" not in str(p):
                    found.add(p)
        for f in (extra or []):
            p = root / f
            if p.exists():
                found.add(p)
        return sorted(found)

    # ── Liste / Restauration ──────────────────────────────────────

    def list_backups(self, app_id: str | None = None) -> list:
        base = BACKUP_ROOT / app_id if app_id else BACKUP_ROOT
        if not base.exists():
            return []
        results = []
        for d in sorted(base.rglob("data_backup_*"), reverse=True):
            if not d.is_dir():
                continue
            meta_f = d / "_meta.json"
            meta   = json.loads(meta_f.read_text(encoding="utf-8")) if meta_f.exists() else {}
            meta["path"] = str(d)
            results.append(meta)
        return results

    def restore_backup(self, backup_path: str, install_path: str) -> dict:
        src  = Path(backup_path)
        dest = Path(install_path)
        if not src.exists():
            return {"success": False, "message": "Backup introuvable: " + backup_path}
        restored = []
        for item in src.iterdir():
            if item.name == "_meta.json":
                continue
            dst = dest / item.name
            try:
                if item.is_dir():
                    shutil.copytree(str(item), str(dst), dirs_exist_ok=True)
                else:
                    shutil.copy2(str(item), str(dst))
                restored.append(item.name)
            except Exception as e:
                logger.warning("Restore %s: %s", item.name, e)
        return {"success": True, "restored": restored,
                "message": str(len(restored)) + " element(s) restaures depuis " + src.name}

    # ── Planification quotidienne ──────────────────────────────────

    def schedule(self, backup_hour: int = 18,
                 registry: str = "apps.local.json") -> None:
        """Lance un thread daemon qui backup toutes les apps a backup_hour."""
        if self._thread and self._thread.is_alive():
            return

        def _loop():
            import time as _t
            last = ""
            logger.info("BackupManager: planifie a %dh", backup_hour)
            while not self._stop.is_set():
                now = datetime.now()
                if now.hour >= backup_hour and now.strftime("%Y-%m-%d") != last:
                    logger.info("BackupManager: declenchement")
                    self._run_all(registry)
                    last = now.strftime("%Y-%m-%d")
                self._stop.wait(300)  # check toutes les 5 min

        self._thread = threading.Thread(target=_loop, daemon=True, name="aion-backup")
        self._thread.start()

    def _run_all(self, registry: str) -> None:
        reg = Path(registry)
        if not reg.exists():
            return
        try:
            apps = json.loads(reg.read_text(encoding="utf-8")).get("apps", {})
        except Exception:
            return
        for app_id, cfg in apps.items():
            path = cfg.get("store", {}).get("install_path", "")
            if not path or not Path(path).exists():
                continue
            extra = cfg.get("store", {}).get("appdata_files", [])
            res   = self.backup_app(app_id, path, extra_files=extra, force=False)
            if not res.get("confirmed") and res.get("already_existed"):
                self.backup_app(app_id, path, extra_files=extra, force=True)

    def stop(self) -> None:
        self._stop.set()
