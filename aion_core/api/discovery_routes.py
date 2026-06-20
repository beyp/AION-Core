"""
App Discovery Routes — AION-Core Phase 3.
Routes FastAPI pour gérer le registre d apps.
"""
import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)


def register_discovery_routes(app, aion_app):
    """Enregistre les routes App Discovery."""

    discovery = aion_app.discovery

    # ── API REST ─────────────────────────────────────────────────────────────

    @app.get("/api/apps")
    async def list_apps():
        """Liste toutes les apps du registre."""
        return {"apps": discovery.list_apps()}

    @app.get("/api/apps/{app_id}")
    async def get_app(app_id: str):
        app_info = discovery.get_app(app_id)
        if not app_info:
            return JSONResponse({"error": f"App '{app_id}' introuvable"}, status_code=404)
        return app_info

    @app.post("/api/apps/discover")
    async def discover_app(request):
        """Découvrir et intégrer une nouvelle app."""
        body     = await request.json()
        source   = body.get("source", "")
        app_id   = body.get("app_id", None)
        app_type = body.get("type", "auto")

        if not source:
            return JSONResponse({"error": "source requis"}, status_code=400)

        result = discovery.discover(source, app_id, app_type)
        return result

    @app.delete("/api/apps/{app_id}")
    async def remove_app(app_id: str):
        return discovery.remove_app(app_id)

    @app.get("/api/apps/{app_id}/status")
    async def app_status(app_id: str):
        """Vérifie si une app est disponible."""
        app_info = discovery.get_app(app_id)
        if not app_info:
            return JSONResponse({"error": "App introuvable"}, status_code=404)

        # Tester la disponibilité
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

    # ── Page web App Registry ────────────────────────────────────────────────

    @app.get("/apps", response_class=HTMLResponse)
    async def apps_registry_page(request):
        """Page web du registre des apps."""
        apps   = discovery.list_apps()
        rows   = ""
        type_colors = {
            "api":          "#1e90ff",
            "api_external": "#9c27b0",
            "local":        "#4caf50",
            "docker":       "#ff9800",
            "github":       "#888",
        }
        status_colors = {
            "active":    "#4caf50",
            "installed": "#1e90ff",
            "pending":   "#ff9800",
            "error":     "#f44336",
        }
        for a in apps:
            tc = type_colors.get(a.get("type",""), "#888")
            sc = status_colors.get(a.get("status",""), "#888")
            web_ui = a.get("web_ui","")
            github = a.get("github","")
            rows += f"""
            <div style="background:#1a1d27;border-radius:8px;padding:14px 16px;
              margin-bottom:8px;border:1px solid #2a2d3e;display:flex;align-items:center;gap:12px;">
              <span style="font-size:1.3rem;">{a.get('icon','📦')}</span>
              <div style="flex:1;">
                <div style="font-size:0.92rem;font-weight:600;">{a.get('name',a['id'])}</div>
                <div style="font-size:0.78rem;color:#888;">{a.get('description','')[:60]}</div>
              </div>
              <span style="background:{tc}22;color:{tc};padding:2px 8px;
                border-radius:8px;font-size:0.72rem;">{a.get('type','')}</span>
              <span style="background:{sc}22;color:{sc};padding:2px 8px;
                border-radius:8px;font-size:0.72rem;">{a.get('status','')}</span>
              {'<a href="'+web_ui+'" style="color:#1e90ff;font-size:0.8rem;">Ouvrir</a>' if web_ui else ''}
              {'<a href="https://github.com/'+github+'" target="_blank" style="color:#888;font-size:0.75rem;">GitHub</a>' if github else ''}
            </div>"""

        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
        <style>
        body{{font-family:Segoe UI;background:#0f1117;color:#e0e0e0;padding:0;margin:0;}}
        .hdr{{background:#151821;border-bottom:2px solid #1e90ff;padding:14px 20px;
          display:flex;align-items:center;gap:12px;}}
        h1{{color:#1e90ff;margin:0;font-size:1.1rem;}}
        .main{{padding:20px;}}
        .discover-form{{background:#1a1d27;border-radius:8px;padding:16px;
          margin-bottom:20px;border:1px solid #2a2d3e;}}
        input{{background:#12141f;border:1px solid #2a2d3e;color:#e0e0e0;
          padding:8px 12px;border-radius:6px;font-size:0.85rem;}}
        button{{background:#1e90ff;color:white;border:none;padding:8px 16px;
          border-radius:6px;cursor:pointer;font-size:0.85rem;}}
        select{{background:#12141f;border:1px solid #2a2d3e;color:#e0e0e0;
          padding:8px;border-radius:6px;}}
        </style>
        </head><body>
        <div class="hdr">
          <span>📦</span><h1>AION-Core — App Registry</h1>
          <span style="margin-left:auto;color:#888;font-size:0.78rem;">{len(apps)} app(s)</span>
          <a href="/" style="color:#888;text-decoration:none;font-size:0.82rem;margin-left:12px;">← Dashboard</a>
        </div>
        <div class="main">
          <div class="discover-form">
            <h3 style="color:#1e90ff;margin-bottom:12px;">🔍 Découvrir une nouvelle app</h3>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <input id="src" type="text" placeholder="beyp/ProjectMind ou http://localhost:8766"
                style="flex:2;min-width:200px;">
              <input id="aid" type="text" placeholder="app_id (optionnel)" style="width:140px;">
              <select id="atype">
                <option value="auto">Auto-detect</option>
                <option value="github">GitHub</option>
                <option value="api">API REST</option>
                <option value="local">Local Python</option>
                <option value="docker">Docker</option>
              </select>
              <button onclick="discoverApp()">+ Intégrer</button>
            </div>
            <div id="discover-result" style="margin-top:10px;font-size:0.83rem;color:#888;"></div>
          </div>
          <h3 style="margin-bottom:12px;color:#888;font-size:0.82rem;
            text-transform:uppercase;letter-spacing:1px;">Apps enregistrées</h3>
          {rows}
        </div>
        <script>
        function discoverApp() {{
          var src  = document.getElementById('src').value.trim();
          var aid  = document.getElementById('aid').value.trim();
          var type = document.getElementById('atype').value;
          if (!src) {{ alert('Source requise'); return; }}
          var res = document.getElementById('discover-result');
          res.textContent = '⏳ Découverte en cours...';
          res.style.color = '#888';
          fetch('/api/apps/discover', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ source: src, app_id: aid || null, type: type }})
          }})
          .then(r => r.json())
          .then(d => {{
            res.textContent = d.message || JSON.stringify(d);
            res.style.color = d.success ? '#4caf50' : '#f44336';
            if (d.success) setTimeout(() => location.reload(), 2000);
          }})
          .catch(e => {{ res.textContent = 'Erreur: ' + e; res.style.color = '#f44336'; }});
        }}
        document.getElementById('src').addEventListener('keydown', function(e) {{
          if (e.key === 'Enter') discoverApp();
        }});
        </script>
        </body></html>""")

    # -- Autostart routes ─────────────────────────────────────────────────────

    @app.get("/api/autostart/status")
    async def autostart_status():
        """Statut de toutes les apps (running, managed, config)."""
        return {"apps": aion_app.launcher.status()}

    @app.post("/api/autostart/{app_id}/start")
    async def autostart_start(app_id: str):
        """Demarre une app manuellement."""
        return aion_app.launcher.start_app(app_id)

    @app.post("/api/autostart/{app_id}/stop")
    async def autostart_stop(app_id: str):
        """Arrete une app."""
        return aion_app.launcher.stop_app(app_id)

    @app.post("/api/autostart/configure")
    async def autostart_configure(request):
        """Configure l autostart d une app via API ou IA."""
        body    = await request.json()
        app_id  = body.get("app_id", "")
        enabled = body.get("enabled", True)
        mode    = body.get("mode", "fastapi")
        path    = body.get("path", "")
        port    = int(body.get("port", 0))
        order   = int(body.get("order", 99))

        if not app_id:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "app_id requis"}, status_code=400)

        result = aion_app.launcher.configure_autostart(
            app_id=app_id, enabled=enabled,
            mode=mode, path=path, port=port, order=order
        )

        # Si on active, demarrer immediatement
        if enabled and result.get("success"):
            start_result = aion_app.launcher.start_app(app_id)
            result["start_result"] = start_result

        return result

    logger.info("Discovery routes registered")
