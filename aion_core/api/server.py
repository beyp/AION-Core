"""
AION-Core API Server — FastAPI.
Point d entrée web : Dashboard, Voice API, REST.
"""
import html
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "web" / "templates"

# Stockage temporaire des pages de résultat vocal
_VOICE_RESULTS: dict[str, dict] = {}
_VOICE_TTL = 300  # 5 minutes


def create_app(aion_app) -> FastAPI:
    """Crée et configure l application FastAPI."""

    app = FastAPI(
        title       = "AION-Core",
        description = "AI-First Personal Orchestrator",
        version     = aion_app.VERSION,
    )

    app.add_middleware(CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    # Templates Jinja2
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None

    # ── Status ──────────────────────────────────────────────────────────────

    @app.get("/")
    async def root():
        return {
            "name":    "AION-Core",
            "version": aion_app.VERSION,
            "status":  "online",
            "apps":    aion_app.app_router.available_apps,
        }

    @app.get("/api/ping")
    async def ping():
        import socket
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = "unknown"
        saved_url = aion_app.memory.recall("aion_public_url") or ""
        return {
            "status":    "ok",
            "message":   "AION-Core is running !",
            "local_ip":  local_ip,
            "saved_url": saved_url,
        }

    # ── Voice API ────────────────────────────────────────────────────────────

    @app.post("/api/voice")
    async def voice_endpoint(request: Request):
        """Point d entrée vocal — iPhone Raccourcis / Siri."""
        body   = await request.json()
        text   = body.get("text", "").strip()
        img_b64 = body.get("image_data", "")
        img_mime = body.get("image_mime", "image/jpeg")

        if not text and not img_b64:
            return {"response": "Rien compris. Répétez.", "ok": False}

        if not aion_app.brain.is_available():
            return {"response": "GROQ_API_KEY non configurée.", "ok": False}

        # Router la requête
        result = aion_app.app_router.route(
            text       = text or "Analyse cette image.",
            image_b64  = img_b64 or None,
            image_mime = img_mime,
        )

        # Stocker le résultat pour la page web
        uid = str(uuid.uuid4())[:8]
        _VOICE_RESULTS[uid] = {
            **result,
            "query":      text,
            "created_at": time.time(),
            "expires_at": time.time() + _VOICE_TTL,
        }
        # Nettoyer les anciens
        now = time.time()
        for k in [k for k, v in _VOICE_RESULTS.items() if v.get("expires_at", 0) < now]:
            del _VOICE_RESULTS[k]

        # URL de résultat (utilise l IP mémorisée si dispo)
        saved_url  = aion_app.memory.recall("aion_public_url") or ""
        req_host   = request.headers.get("host", "")
        if saved_url:
            base_url = saved_url.rstrip("/")
        elif req_host and not req_host.startswith("127") and not req_host.startswith("localhost"):
            base_url = f"http://{req_host}"
        else:
            base_url = str(request.base_url).rstrip("/")

        result_url = f"{base_url}/voice/result/{uid}"

        return {
            "response":   result["response"],
            "action":     result["app"],
            "app":        result["app"],
            "result":     result["result"],
            "url":        result_url,
            "result_uid": uid,
            "ok":         True,
        }

    @app.get("/voice/result/{uid}", response_class=HTMLResponse)
    async def voice_result(uid: str, request: Request):
        """Page de résultat vocal — optimisée mobile."""
        data = _VOICE_RESULTS.get(uid)
        if not data:
            return HTMLResponse(
                "<html><body style='background:#0f1117;color:#e0e0e0;font-family:sans-serif;"
                "display:flex;align-items:center;justify-content:center;height:100vh;'>"
                "<div style='text-align:center;'><h2 style='color:#f44336;'>Page expirée</h2>"
                "<p style='color:#888;'>Ce résultat a expiré (5 min max).</p></div></body></html>",
                status_code=410
            )
        return HTMLResponse(_build_voice_page(uid, data))

    # ── Memory API ───────────────────────────────────────────────────────────

    @app.get("/api/memory")
    async def get_memory():
        return aion_app.memory.list_memory()

    @app.post("/api/memory/{key}")
    async def set_memory(key: str, request: Request):
        body  = await request.json()
        value = body.get("value", "")
        mtype = body.get("type", "info")
        aion_app.memory.remember(key, value, mtype)
        return {"ok": True, "key": key, "value": value}

    @app.delete("/api/memory/{key}")
    async def del_memory(key: str):
        ok = aion_app.memory.forget(key)
        return {"ok": ok}

    # ── Apps API ─────────────────────────────────────────────────────────────

    @app.post("/api/route")
    async def route_request(request: Request):
        """Route une requête texte vers la bonne app."""
        body  = await request.json()
        text  = body.get("text", "")
        result = aion_app.app_router.route(text)
        return result

    @app.get("/api/apps")
    async def list_apps():
        return {"apps": aion_app.app_router.available_apps}

    # ── Web Routes ─────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def web_dashboard(request: Request):
        if templates is None:
            return HTMLResponse("<h1>AION-Core API</h1><p><a href='/docs'>API Docs</a></p>")
        mem   = aion_app.memory.list_memory()
        recent = dict(list(mem.items())[-5:]) if mem else {}
        return templates.TemplateResponse(request=request, name="dashboard.html", context={
            "version":      aion_app.VERSION,
            "active":       "dashboard",
            "ai_available": aion_app.brain.is_available(),
            "apps_count":   len(aion_app.app_router.available_apps),
            "memory_count": len(mem),
            "recent_memory": recent,
        })

    @app.get("/chat", response_class=HTMLResponse)
    async def web_chat(request: Request):
        if templates is None:
            return HTMLResponse("<p>Templates not found</p>")
        return templates.TemplateResponse(request=request, name="chat.html", context={
            "version":      aion_app.VERSION,
            "active":       "chat",
            "ai_available": aion_app.brain.is_available(),
            "groq_model":   aion_app.brain.model,
        })

    @app.get("/memory", response_class=HTMLResponse)
    async def web_memory(request: Request):
        mem = aion_app.memory.list_memory()
        rows = "".join(
            f"<tr><td style='color:var(--accent);padding:8px 12px;'>{k}</td>"
            f"<td style='padding:8px 12px;color:var(--dim);'>{v.get('type','')}</td>"
            f"<td style='padding:8px 12px;'>{v.get('value','')[:60]}</td></tr>"
            for k, v in mem.items()
        )
        html_content = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
        <style>body{{font-family:Segoe UI;background:#0f1117;color:#e0e0e0;padding:20px;}}
        table{{width:100%;border-collapse:collapse;background:#1a1d27;border-radius:8px;overflow:hidden;}}
        th{{background:#041E42;color:#fff;padding:10px 12px;text-align:left;}}
        tr:hover{{background:#2a2d3e;}}</style></head>
        <body><h2 style="color:#1e90ff;margin-bottom:16px;">🧠 AION Memory ({len(mem)} items)</h2>
        <table><thead><tr><th>Clé</th><th>Type</th><th>Valeur</th></tr></thead>
        <tbody>{rows}</tbody></table>
        <p style="color:#888;margin-top:12px;font-size:0.8rem;">
        <a href="/" style="color:#1e90ff;">← Dashboard</a></p></body></html>"""
        return HTMLResponse(html_content)

    @app.get("/app/{app_name}", response_class=HTMLResponse)
    async def web_app(app_name: str, request: Request):
        """Vue dédiée par app — à enrichir dans les phases suivantes."""
        connector = aion_app.app_router._apps.get(app_name)
        if not connector:
            return HTMLResponse(f"<p>App '{app_name}' non trouvée.</p>", status_code=404)
        result = connector.execute("list_tasks" if app_name=="quickmind" else
                                   "search" if app_name=="ado" else
                                   "cpu_ram" if app_name=="system" else
                                   "status", {})
        html_content = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
        <style>body{{font-family:Segoe UI;background:#0f1117;color:#e0e0e0;padding:20px;}}
        pre{{background:#1a1d27;padding:16px;border-radius:8px;white-space:pre-wrap;
        color:#4caf50;font-size:0.85rem;}}</style></head>
        <body><h2 style="color:#1e90ff;margin-bottom:16px;">
        {app_name.upper()}</h2>
        <pre>{result}</pre>
        <p style="color:#888;margin-top:12px;font-size:0.8rem;">
        <a href="/" style="color:#1e90ff;">← Dashboard</a></p></body></html>"""
        return HTMLResponse(html_content)

    @app.get("/api/apps/status")
    async def apps_status():
        """Statut de toutes les apps — appelé par htmx."""
        status = {}
        for app_name, connector in aion_app.app_router._apps.items():
            try:
                if hasattr(connector, "health"):
                    r = connector.health()
                    status[app_name] = "online" if "actif" in r.lower() or "active" in r.lower() else "offline"
                else:
                    status[app_name] = "unknown"
            except Exception:
                status[app_name] = "offline"
        html_parts = []
        icons = {"quickmind":"✅","ado":"🔵","system":"🖥️","timer":"⏰"}
        colors = {"online":"var(--green)","offline":"var(--red)","unknown":"var(--dim)"}
        for app_name, state in status.items():
            color = colors.get(state, "var(--dim)")
            icon  = icons.get(app_name, "📦")
            html_parts.append(
                f'<div style="display:flex;align-items:center;gap:10px;padding:7px 0;'
                f'border-bottom:1px solid var(--border);font-size:0.85rem;">'
                f'<span>{icon}</span>'
                f'<span style="flex:1;">{app_name}</span>'
                f'<span style="color:{color};font-size:0.78rem;font-weight:600;">{state}</span>'
                f'</div>'
            )
        return HTMLResponse("\n".join(html_parts))

    @app.get("/settings", response_class=HTMLResponse)
    async def web_settings(request: Request):
        model = aion_app.brain.model
        models = aion_app.brain.list_models() if aion_app.brain.is_available() else []
        html_content = f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
        <style>body{{font-family:Segoe UI;background:#0f1117;color:#e0e0e0;padding:20px;}}
        .card{{background:#1a1d27;border-radius:8px;padding:16px;margin-bottom:14px;border:1px solid #2a2d3e;}}
        h3{{color:#1e90ff;margin-bottom:10px;}}
        .row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2d3e;font-size:0.85rem;}}
        .dim{{color:#888;}}</style></head>
        <body>
        <h2 style="color:#1e90ff;margin-bottom:16px;">⚙️ AION-Core Settings</h2>
        <div class="card"><h3>🤖 IA</h3>
        <div class="row"><span>Modèle actif</span><span style="color:#4caf50;">{model}</span></div>
        <div class="row"><span>Groq disponible</span>
        <span style="color:{'#4caf50' if aion_app.brain.is_available() else '#f44336'};">
        {'✅ Oui' if aion_app.brain.is_available() else '❌ Non'}</span></div>
        <div class="row"><span>Modèles disponibles</span>
        <span class="dim">{', '.join(models[:3]) if models else 'N/A'}</span></div>
        </div>
        <div class="card"><h3>📊 Apps</h3>
        {''.join(f'<div class="row"><span>{a}</span><span class="dim">✅ connecté</span></div>' for a in aion_app.app_router.available_apps)}
        </div>
        <p style="color:#888;margin-top:12px;font-size:0.8rem;">
        <a href="/" style="color:#1e90ff;">← Dashboard</a></p></body></html>"""
        return HTMLResponse(html_content)

    return app


def _build_voice_page(uid: str, data: dict) -> str:
    """Génère la page HTML de résultat vocal."""
    query    = html.escape(data.get("query", ""))
    app_name = html.escape(data.get("app", ""))
    response = html.escape(data.get("response", ""))
    result   = data.get("result", "")
    created  = time.strftime("%H:%M:%S", time.localtime(data.get("created_at", 0)))
    expires  = max(0, int(data.get("expires_at", 0) - time.time()))

    app_colors = {
        "quickmind": "#4caf50", "ado": "#0078d4",
        "system": "#9c27b0", "timer": "#ff9800",
        "search": "#1e90ff",
    }
    color = app_colors.get(app_name, "#888")

    # Formater le résultat
    result_html = ""
    if result:
        lines = result.splitlines()
        items = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if "#" in line and app_name == "ado":
                import re
                m = re.search(r"#(\d+)", line)
                if m:
                    aid = m.group(1)
                    url = f"https://dev.azure.com/Premiertech/PTG%20-%20TMM%20D2/_workitems/edit/{aid}"
                    items.append(
                        f'<a href="{url}" style="display:flex;align-items:center;gap:10px;'
                        f'background:#1a1d27;border-radius:8px;padding:12px;margin-bottom:6px;'
                        f'text-decoration:none;color:#e0e0e0;border:1px solid #2a2d3e;">'
                        f'<span style="color:#0078d4;font-weight:700;min-width:50px;">#{aid}</span>'
                        f'<span style="flex:1;font-size:0.85rem;">{html.escape(line)}</span>'
                        f'<span style="color:#888;">&#x279C;</span></a>'
                    )
                    continue
            items.append(
                f'<div style="background:#1a1d27;border-radius:6px;padding:10px 12px;'
                f'margin-bottom:5px;font-size:0.85rem;color:#ccc;">{html.escape(line)}</div>'
            )
        result_html = "\n".join(items)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>AION — {query[:30]}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f1117;color:#e0e0e0;}}
.hdr{{background:#151821;border-bottom:2px solid {color};padding:14px 16px;
  display:flex;align-items:center;gap:10px;}}
.hdr h1{{color:{color};font-size:1.1rem;}}
.badge{{background:{color}22;color:{color};border:1px solid {color}44;
  padding:3px 10px;border-radius:12px;font-size:0.72rem;font-weight:600;}}
.query{{background:#1a1d27;border-left:3px solid {color};padding:12px 16px;
  margin:12px;border-radius:0 8px 8px 0;font-size:0.9rem;color:#ccc;font-style:italic;}}
.vresp{{background:#1a1d27;border-radius:10px;padding:14px 16px;margin:0 12px 12px;
  font-size:1rem;line-height:1.5;}}
.results{{padding:0 12px 20px;}}
.results h2{{font-size:0.78rem;text-transform:uppercase;letter-spacing:1px;color:#888;margin-bottom:10px;}}
.refresh{{display:block;text-align:center;background:#1a1d27;border:1px solid #2a2d3e;
  color:#888;padding:10px;margin:0 12px 12px;border-radius:8px;text-decoration:none;font-size:0.85rem;}}
.expires{{color:#444;font-size:0.7rem;text-align:center;padding:4px 0 20px;}}
</style>
</head>
<body>
<div class="hdr">
  <span style="font-size:1.4rem;">&#x1F916;</span>
  <h1>AION-Core</h1>
  <span class="badge">{app_name}</span>
  <span style="margin-left:auto;color:#555;font-size:0.72rem;">{created}</span>
</div>
<div class="query">&#x201C;{query}&#x201D;</div>
<div class="vresp"><span style="font-size:1.2rem;margin-right:8px;">&#x1F50A;</span>{response}</div>
{"<div class='results'><h2>Resultats</h2>" + result_html + "</div>" if result_html else ""}
<a href="/voice/result/{uid}" class="refresh">&#x21BA; Rafraichir</a>
<div class="expires">Expire dans {expires}s</div>
</body>
</html>"""
