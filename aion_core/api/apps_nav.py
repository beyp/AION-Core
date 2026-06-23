"""
apps_nav.py -- Route /api/nav/apps
Retourne la liste des apps actives pour la sidebar dynamique.
"""
import json
import logging
from pathlib import Path
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

ICON_MAP = {
    "check":     "✅",
    "circle":    "🔵",
    "clipboard": "📋",
    "monitor":   "🖥️",
    "clock":     "⏰",
    "brain":     "🧠",
    "mail":      "✉️",
    "package":   "📦",
    "gear":      "⚙️",
    "star":      "⭐",
    "bolt":      "⚡",
    "chart":     "📊",
}

SYSTEM_APPS = {"system", "timer"}


def _load_registry() -> dict:
    """
    Fusionne apps.json (built-in, git) et apps.local.json (perso, git-ignore).
    apps.local.json a priorite sur apps.json pour les cles en double.
    """
    result = {"apps": {}}

    # 1. Charger les apps built-in
    for reg_file in [Path("apps.json"), Path("apps.local.json")]:
        if reg_file.exists():
            try:
                with open(reg_file, encoding="utf-8") as f:
                    data = json.load(f)
                result["apps"].update(data.get("apps", {}))
            except Exception:
                pass

    return result


def register_nav_routes(app, aion_app):
    """Enregistre les routes de navigation dynamique."""

    @app.get("/api/nav/apps")
    async def nav_apps_json():
        """Retourne la liste JSON des apps pour la sidebar."""
        registry  = _load_registry()
        nav_items = []
        for app_id, cfg in registry.get("apps", {}).items():
            if cfg.get("status") not in ("active", "installed"):
                continue
            icon = ICON_MAP.get(cfg.get("icon", "package"), "📦")
            nav_items.append({
                "id":           app_id,
                "name":         cfg.get("name", app_id.title()),
                "icon":         icon,
                "url":          f"/app/{app_id}",
                "type":         cfg.get("type", "local"),
                "is_system":    app_id in SYSTEM_APPS,
                "external_url": cfg.get("url", ""),
            })
        return {"apps": nav_items}

    @app.get("/api/nav/apps/sidebar", response_class=HTMLResponse)
    async def nav_sidebar_fragment():
        """Fragment HTML htmx pour la sidebar — apps + services."""
        registry   = _load_registry()
        items_html = []
        for app_id, cfg in registry.get("apps", {}).items():
            if cfg.get("status") not in ("active", "installed"):
                continue
            icon = ICON_MAP.get(cfg.get("icon", "package"), "📦")
            name = cfg.get("name", app_id.title())
            url  = f"/app/{app_id}"
            items_html.append(
                f'<a href="{url}" class="nav-item" id="nav-{app_id}" '
                f'data-app-id="{app_id}">'
                f'<span class="nav-icon">{icon}</span>'
                f'<span class="nav-label">{name}</span>'
                f'<span class="nav-dot" id="dot-{app_id}"></span>'
                f'</a>'
            )

        # Section Services
        try:
            import requests as _req, os as _os
            svc_port = int(_os.getenv("AION_SERVICES_PORT", "8001"))
            r = _req.get(f"http://localhost:{svc_port}/api/services", timeout=1.0)
            services = r.json().get("services", []) if r.status_code == 200 else []
        except Exception:
            services = []

        if services:
            items_html.append(
                '<div class="sb-sec" style="margin-top:12px;">'
                '⚡ Services</div>'
            )
            for svc in services:
                svc_id = svc["name"]
                svc_name = svc.get("name", svc_id).replace("_", " ").title()
                items_html.append(
                    f'<a href="/services/{svc_id}" class="nav-item" id="nav-svc-{svc_id}">'
                    f'<span class="nav-icon">⚡</span>'
                    f'<span class="nav-label">{svc_name}</span>'
                    f'</a>'
                )

        return HTMLResponse("\n".join(items_html))

    @app.get("/api/nav/apps/status", response_class=HTMLResponse)
    async def nav_apps_status():
        """Pastilles de statut pour toutes les apps (htmx polling)."""
        registry = _load_registry()
        updates  = []
        for app_id, cfg in registry.get("apps", {}).items():
            if cfg.get("status") not in ("active", "installed"):
                continue
            url       = cfg.get("url", "")
            health_ep = cfg.get("health_endpoint", "/health")
            is_online = False
            if url:
                try:
                    import requests as _req
                    r = _req.get(url.rstrip("/") + health_ep, timeout=1.5)
                    is_online = r.status_code < 400
                except Exception:
                    pass
            else:
                is_online = True  # apps locales toujours online
            color = "#4caf50" if is_online else "#f44336"
            updates.append(
                f'<span id="dot-{app_id}" class="nav-dot" '
                f'style="width:6px;height:6px;border-radius:50%;'
                f'background:{color};margin-left:auto;display:inline-block;"></span>'
            )
        return HTMLResponse("\n".join(updates))
