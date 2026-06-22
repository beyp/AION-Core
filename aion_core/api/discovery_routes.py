"""
App Discovery Routes -- AION-Core.
Routes FastAPI pour gerer le registre d apps.
/api/apps/{app_id}        GET    - detail d'une app
/api/apps/{app_id}/status GET    - health check d'une app
/api/apps/discover        POST   - decouvrir une nouvelle app
/api/apps/{app_id}        DELETE - retirer une app du registre
Note: GET /api/apps (liste) est dans server.py pour eviter le doublon.
"""
import logging
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)


def register_discovery_routes(app, aion_app):
    """Enregistre les routes App Discovery."""

    discovery = aion_app.discovery

    @app.get("/api/apps/{app_id}/status")
    async def app_status(app_id: str):
        """Verifie si une app est disponible (health check)."""
        app_info = discovery.get_app(app_id)
        if not app_info:
            return JSONResponse({"error": "App introuvable"}, status_code=404)
        available = False
        url       = app_info.get("url", "")
        if url:
            try:
                import requests as _req
                health = app_info.get("health_endpoint", "/health")
                r      = _req.get(f"{url}{health}", timeout=3)
                available = r.status_code < 400
            except Exception:
                available = False
        return {
            "app_id":    app_id,
            "name":      app_info.get("name"),
            "available": available,
            "url":       url,
            "type":      app_info.get("type"),
        }

    @app.post("/api/apps/discover")
    async def discover_app(request):
        """Decouvre et integre une nouvelle app."""
        body     = await request.json()
        source   = body.get("source", "")
        app_id   = body.get("app_id", None)
        app_type = body.get("type", "auto")
        if not source:
            return JSONResponse({"error": "source requis"}, status_code=400)
        return discovery.discover(source, app_id, app_type)

    @app.get("/api/apps/{app_id}")
    async def get_app(app_id: str):
        """Detail d'une app du registre."""
        app_info = discovery.get_app(app_id)
        if not app_info:
            return JSONResponse({"error": f"App '{app_id}' introuvable"}, status_code=404)
        return app_info

    @app.delete("/api/apps/{app_id}")
    async def remove_app(app_id: str):
        """Retire une app du registre."""
        return discovery.remove_app(app_id)

    logger.info("Discovery routes registered")
