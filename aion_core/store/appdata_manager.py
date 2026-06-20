"""
AppDataManager -- Gestion de la persistance des fichiers d'app.

Responsabilite :
- Copie les fichiers declares (memory.json, *.db, ...) depuis le repo vers appdata/
- Les restaure depuis appdata/ vers le repo apres un git clone / git pull
- Les sauvegarde dans backups/ sous forme de zip avant un update

Structure sur disque :
    C:\AION_APPS\
    ├── repos\<AppName>\         <- code git
    ├── appdata\<app_id>\        <- fichiers persistants
    └── backups\                  <- zips horodates

Usage :
    mgr = AppDataManager()
    mgr.save(app_id, install_path, appdata_files)    # repo -> appdata
    mgr.restore(app_id, install_path, appdata_files) # appdata -> repo
    mgr.backup(app_id)                               # appdata -> backups/zip
"""
import logging
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

AION_APPS_ROOT = Path(os.getenv("AION_APPS_ROOT", r"C:\AION_APPS"))


class AppDataManager:
    """Gere la persistance des fichiers d'app entre repo et appdata/."""

    def __init__(self, root: str | None = None) -> None:
        self.root     = Path(root) if root else AION_APPS_ROOT
        self.appdata  = self.root / "appdata"
        self.backups  = self.root / "backups"
        self.appdata.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(parents=True, exist_ok=True)

    # -- API publique ----------------------------------------------------------

    def save(self, app_id: str, install_path: str,
             appdata_files: list[str]) -> dict:
        """
        Copie les fichiers declares depuis le repo vers appdata/.
        Appele apres un git clone ou git pull pour sauvegarder l'etat.

        Args:
            app_id:        ID de l'app (ex: "quickmind")
            install_path:  Chemin du repo (ex: C:\AION_APPS\repos\QuickMind)
            appdata_files: Liste de chemins relatifs (ex: ["memory.json", "data/tasks.db"])
        """
        src_root  = Path(install_path)
        dest_root = self.appdata / app_id
        dest_root.mkdir(parents=True, exist_ok=True)

        saved, missing = [], []
        for rel in appdata_files:
            src = src_root / rel
            if src.exists():
                dest = dest_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                saved.append(rel)
                logger.info("AppData saved: %s -> %s", src, dest)
            else:
                missing.append(rel)
                logger.debug("AppData not found (skip): %s", src)

        return {
            "success": True,
            "app_id": app_id,
            "saved": saved,
            "missing": missing,
            "appdata_path": str(dest_root),
        }

    def restore(self, app_id: str, install_path: str,
                appdata_files: list[str]) -> dict:
        """
        Recopie les fichiers depuis appdata/ vers le repo.
        Appele apres un git clone pour remettre les fichiers persistants.

        Args:
            app_id:        ID de l'app
            install_path:  Chemin cible du repo
            appdata_files: Liste de chemins relatifs a restaurer
        """
        src_root  = self.appdata / app_id
        dest_root = Path(install_path)

        if not src_root.exists():
            return {
                "success": False,
                "message": f"Aucun appdata trouve pour '{app_id}' ({src_root})",
            }

        restored, missing = [], []
        for rel in appdata_files:
            src = src_root / rel
            if src.exists():
                dest = dest_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                restored.append(rel)
                logger.info("AppData restored: %s -> %s", src, dest)
            else:
                missing.append(rel)

        return {
            "success": True,
            "app_id": app_id,
            "restored": restored,
            "missing": missing,
        }

    def backup(self, app_id: str) -> dict:
        """
        Cree un zip horodate de l'appdata d'une app dans backups/.
        Appele automatiquement avant chaque git pull (update).

        Returns:
            {"success": bool, "backup_path": str}
        """
        src = self.appdata / app_id
        if not src.exists():
            return {"success": False, "message": f"Rien a sauvegarder pour '{app_id}'"}

        timestamp   = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        backup_name = f"{app_id}_{timestamp}_backup.zip"
        backup_path = self.backups / backup_name

        with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in src.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(src))

        logger.info("AppData backup created: %s", backup_path)
        return {"success": True, "app_id": app_id, "backup_path": str(backup_path)}

    def list_appdata(self, app_id: str) -> list[str]:
        """Liste les fichiers presents dans appdata/ pour une app."""
        src = self.appdata / app_id
        if not src.exists():
            return []
        return [str(f.relative_to(src)) for f in src.rglob("*") if f.is_file()]

    def list_backups(self, app_id: str | None = None) -> list[str]:
        """Liste les backups disponibles (filtre par app_id si fourni)."""
        if not self.backups.exists():
            return []
        backups = [f.name for f in self.backups.iterdir() if f.suffix == ".zip"]
        if app_id:
            backups = [b for b in backups if b.startswith(app_id + "_")]
        return sorted(backups, reverse=True)
