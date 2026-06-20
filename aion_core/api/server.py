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
