"""
service_runner.py — AION-Core Services Runner.

Micro-serveur FastAPI sur port 8001 (configurable AION_SERVICES_PORT).
Charge automatiquement tous les services dans :
  - aion_core/services/builtins/    (built-in, dans le repo)
  - C:/AION_APPS/services/          (custom, téléchargés depuis GitHub)

Routes :
  GET  /                              → liste des services + actions
  GET  /health                        → {"status": "ok"}
  GET  /api/services                  → liste JSON des services
  GET  /api/services/{name}           → détail d'un service
  POST /api/services/{name}/{action}  → exécuter une action
  POST /api/services/install          → installer depuis GitHub (phase 2)
"""
from __future__ import annotations
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Registre des services chargés ─────────────────────────────────────────────
_SERVICES: dict[str, Any] = {}


def _load_service_from_file(path: Path) -> tuple[str, Any] | None:
    """
    Charge un fichier service.py ou *_calc.py etc.
    Retourne (name, instance) ou None si échec.
    """
    try:
        spec   = importlib.util.spec_from_file_location(f"svc_{path.stem}", str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = getattr(module, "Service", None)
        if cls is None:
            return None
        instance = cls()
        name = getattr(instance, "name", path.stem)
        return name, instance
    except Exception as e:
        logger.warning("Impossible de charger le service %s: %s", path, e)
        return None


def load_all_services() -> dict[str, Any]:
    """Charge tous les services builtins + custom."""
    services = {}

    # 1. Builtins (dans le repo AION-Core)
    builtins_dir = Path(__file__).parent / "builtins"
    if builtins_dir.exists():
        for py_file in sorted(builtins_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            result = _load_service_from_file(py_file)
            if result:
                name, svc = result
                services[name] = svc
                logger.info("Service builtin chargé : %s", name)

    # 2. Custom (C:/AION_APPS/services/ ou AION_SERVICES_DIR)
    custom_dir = Path(os.getenv("AION_SERVICES_DIR", "C:/AION_APPS/services"))
    if custom_dir.exists():
        for svc_dir in sorted(custom_dir.iterdir()):
            if not svc_dir.is_dir():
                continue
            for fname in ["service.py", f"{svc_dir.name}.py"]:
                py_file = svc_dir / fname
                if py_file.exists():
                    result = _load_service_from_file(py_file)
                    if result:
                        name, svc = result
                        services[name] = svc
                        logger.info("Service custom chargé : %s (%s)", name, py_file)
                    break

    return services


def create_service_app() -> "FastAPI":
    """Crée et retourne l'application FastAPI des services."""
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse

    global _SERVICES
    _SERVICES = load_all_services()

    app = FastAPI(
        title       = "AION-Services",
        description = "Micro-actions Python — extensibles sans UI",
        version     = "1.0.0",
    )
    app.add_middleware(CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    # ── Health ────────────────────────────────────────────────────────────────
    @app.get("/health")
    async def health():
        return {"status": "ok", "app": "AION-Services", "services": len(_SERVICES)}

    # ── Liste des services ────────────────────────────────────────────────────
    @app.get("/api/services")
    async def list_services():
        return {
            "services": [
                {
                    "name":        name,
                    "description": getattr(svc, "description", ""),
                    "actions":     getattr(svc, "actions", []),
                }
                for name, svc in _SERVICES.items()
            ],
            "total": len(_SERVICES),
        }

    # ── Détail d'un service ───────────────────────────────────────────────────
    @app.get("/api/services/{service_name}")
    async def get_service(service_name: str):
        svc = _SERVICES.get(service_name)
        if not svc:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": f"Service '{service_name}' introuvable."},
            )
        return {
            "name":        service_name,
            "description": getattr(svc, "description", ""),
            "actions":     getattr(svc, "actions", []),
        }

    # ── Exécuter une action ───────────────────────────────────────────────────
    @app.post("/api/services/{service_name}/{action}")
    async def run_service(service_name: str, action: str, request: Request):
        svc = _SERVICES.get(service_name)
        if not svc:
            return JSONResponse(
                status_code=404,
                content={"success": False, "message": f"Service '{service_name}' introuvable."},
            )
        try:
            params = await request.json()
        except Exception:
            params = {}
        try:
            result = svc.execute(action, params)
            return result
        except Exception as e:
            logger.error("Erreur service %s/%s: %s", service_name, action, e)
            return {"success": False, "message": str(e)}

    # ── Recharger les services (hot-reload) ────────────────────────────────────
    @app.post("/api/services/reload")
    async def reload_services():
        global _SERVICES
        _SERVICES = load_all_services()
        return {"success": True, "message": f"{len(_SERVICES)} service(s) rechargé(s)",
                "services": list(_SERVICES.keys())}

    # ── Page d'accueil ────────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def index():
        rows = ""
        for name, svc in _SERVICES.items():
            desc    = getattr(svc, "description", "")
            actions = getattr(svc, "actions", [])
            acts    = " ".join(
                f"<code style='background:#1e90ff22;color:#1e90ff;padding:2px 6px;"
                f"border-radius:4px;font-size:.8rem;'>{a}</code>"
                for a in actions
            )
            rows += f"""
            <div style='background:#1a1d27;border:1px solid #2a2d3e;border-radius:8px;
                 padding:14px 16px;margin-bottom:10px;'>
              <div style='font-weight:600;color:#e0e0e0;margin-bottom:4px;'>{name}</div>
              <div style='color:#888;font-size:.85rem;margin-bottom:8px;'>{desc}</div>
              <div>{acts}</div>
            </div>"""
        return f"""<!DOCTYPE html>
<html lang='fr'><head><meta charset='UTF-8'>
<title>AION-Services</title>
<style>body{{background:#0f1117;color:#e0e0e0;font-family:'Segoe UI',sans-serif;
max-width:700px;margin:40px auto;padding:0 20px;}}</style></head>
<body>
<h1 style='color:#1e90ff;'>⚡ AION-Services</h1>
<p style='color:#888;margin-bottom:20px;'>{len(_SERVICES)} service(s) chargé(s) — port {os.getenv("AION_SERVICES_PORT","8001")}</p>
{rows}
<p style='color:#555;font-size:.8rem;margin-top:20px;'>
  API : <code>POST /api/services/{{name}}/{{action}}</code>
</p>
</body></html>"""

    return app


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("AION_SERVICES_PORT", "8001"))
    host = os.getenv("AION_SERVICES_HOST", "0.0.0.0")
    logger.info("AION-Services démarrage sur http://%s:%s", host, port)
    uvicorn.run(create_service_app(), host=host, port=port, log_level="info")
