"""
docker_manager.py -- Gestion des containers Docker pour les apps AION.

Permet de lancer/stopper des apps Docker depuis AION-Core
sans avoir besoin de Docker Desktop GUI.

Prerequis : Docker Desktop installe et en cours d'execution.

Usage :
    dm = DockerManager()
    dm.start("projectmind", "C:/AION_APPS/repos/ProjectMind")
    dm.stop("projectmind")
    dm.status()
"""
import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _docker(*args, cwd=None, timeout=120) -> tuple[bool, str]:
    """Execute une commande docker et retourne (success, output)."""
    try:
        r = subprocess.run(
            ["docker"] + list(args),
            cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout
        )
        out = (r.stdout + r.stderr).strip()
        return r.returncode == 0, out
    except FileNotFoundError:
        return False, "Docker non installe ou pas dans le PATH. Lance Docker Desktop."
    except subprocess.TimeoutExpired:
        return False, f"Timeout docker (>{timeout}s)"
    except Exception as e:
        return False, str(e)


def _compose(*args, cwd=None, timeout=120) -> tuple[bool, str]:
    """Execute docker compose avec les arguments donnés."""
    return _docker("compose", *args, cwd=cwd, timeout=timeout)


class DockerManager:
    """Gere le cycle de vie des containers Docker pour les apps AION."""

    # ── Docker disponible ? ───────────────────────────────────────

    @staticmethod
    def is_docker_available() -> bool:
        """Retourne True si Docker est installe et en cours d'execution."""
        ok, _ = _docker("info", timeout=5)
        return ok

    @staticmethod
    def get_docker_status() -> dict:
        """Retourne le statut de Docker Desktop."""
        ok, out = _docker("info", "--format", "{{.ServerVersion}}", timeout=5)
        return {
            "available":       ok,
            "server_version":  out.strip() if ok else None,
            "message":         "Docker en cours" if ok else "Docker non disponible — lance Docker Desktop",
        }

    # ── Start ─────────────────────────────────────────────────────

    def start(self, app_id: str, install_path: str,
              compose_file: str = "docker-compose.yml",
              build: bool = False) -> dict:
        """
        Lance une app via docker compose.

        Args:
            app_id:       ID de l'app (ex: "projectmind")
            install_path: Repertoire du repo (ex: C:/AION_APPS/repos/ProjectMind)
            compose_file: Fichier compose (default: docker-compose.yml)
            build:        True = rebuild l'image avant de lancer

        Returns:
            {"success": bool, "message": str, "container": str}
        """
        root = Path(install_path)
        if not root.exists():
            return {"success": False, "message": f"Dossier introuvable: {install_path}"}

        compose_path = root / compose_file
        if not compose_path.exists():
            # Chercher un compose file
            for f in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]:
                if (root / f).exists():
                    compose_file = f
                    break
            else:
                return {"success": False, "message": f"Aucun docker-compose.yml dans {install_path}"}

        # Verifier Docker
        if not self.is_docker_available():
            return {"success": False,
                    "message": "Docker non disponible. Lance Docker Desktop puis reessaie."}

        # Construire la commande
        cmd = ["-f", compose_file, "up", "-d"]
        if build:
            cmd.append("--build")

        logger.info("docker compose %s dans %s", " ".join(cmd), install_path)
        ok, out = _compose(*cmd, cwd=str(root))

        if ok:
            logger.info("Docker %s lance: %s", app_id, out[:100])
            return {
                "success":   True,
                "message":   f"{app_id} lance via Docker Compose",
                "output":    out[:200],
            }
        else:
            return {
                "success": False,
                "message": f"docker compose up failed: {out[:300]}",
            }

    # ── Stop ──────────────────────────────────────────────────────

    def stop(self, app_id: str, install_path: str,
             compose_file: str = "docker-compose.yml") -> dict:
        """Stoppe les containers d'une app."""
        root = Path(install_path)

        # Essai 1 : docker compose down depuis le dossier
        if root.exists():
            for cf in [compose_file, "docker-compose.yml", "docker-compose.yaml"]:
                if (root / cf).exists():
                    ok, out = _compose("-f", cf, "down", cwd=str(root))
                    if ok:
                        return {"success": True, "message": f"{app_id} stoppe (compose down)"}
                    break

        # Essai 2 : stopper le container par nom
        ok, out = _docker("stop", app_id, timeout=30)
        if ok:
            return {"success": True, "message": f"Container {app_id} stoppe"}

        # Essai 3 : chercher par label/nom partiel
        ok, out = _docker("ps", "-q", "--filter", f"name={app_id}", timeout=10)
        if ok and out.strip():
            container_id = out.strip().split()[0]
            _docker("stop", container_id, timeout=30)
            return {"success": True, "message": f"Container {container_id} stoppe"}

        return {"success": False, "message": f"Aucun container {app_id} trouve"}

    # ── Status ────────────────────────────────────────────────────

    def is_running(self, app_id: str) -> bool:
        """Retourne True si le container app_id tourne."""
        ok, out = _docker("ps", "-q", "--filter", f"name={app_id}",
                          "--filter", "status=running", timeout=5)
        return ok and bool(out.strip())

    def container_status(self, app_id: str) -> dict:
        """Retourne le statut detaille d'un container."""
        ok, out = _docker("ps", "--filter", f"name={app_id}",
                          "--format", "{{.Status}}", timeout=5)
        if ok and out.strip():
            return {"running": True, "status": out.strip()}
        return {"running": False, "status": "stopped"}

    def list_containers(self) -> list[dict]:
        """Liste tous les containers AION (en cours ou stoppés)."""
        ok, out = _docker("ps", "-a",
                          "--format", "{{.Names}}|{{.Status}}|{{.Ports}}|{{.Image}}",
                          timeout=10)
        if not ok:
            return []
        result = []
        for line in out.splitlines():
            parts = line.split("|")
            if len(parts) >= 2:
                result.append({
                    "name":    parts[0],
                    "status":  parts[1],
                    "ports":   parts[2] if len(parts) > 2 else "",
                    "image":   parts[3] if len(parts) > 3 else "",
                    "running": "Up" in parts[1],
                })
        return result

    # ── Logs ──────────────────────────────────────────────────────

    def get_logs(self, app_id: str, lines: int = 50) -> str:
        """Retourne les derniers logs d'un container."""
        ok, out = _docker("logs", "--tail", str(lines), app_id, timeout=10)
        return out if ok else f"Impossible de lire les logs de {app_id}: {out}"

    # ── Build ─────────────────────────────────────────────────────

    def build(self, app_id: str, install_path: str,
              compose_file: str = "docker-compose.yml") -> dict:
        """Reconstruit l'image Docker d'une app."""
        root = Path(install_path)
        if not root.exists():
            return {"success": False, "message": f"Dossier introuvable: {install_path}"}
        ok, out = _compose("-f", compose_file, "build", "--no-cache",
                           cwd=str(root), timeout=300)
        return {
            "success": ok,
            "message": f"Build {'OK' if ok else 'ECHEC'}: {out[:200]}",
        }
