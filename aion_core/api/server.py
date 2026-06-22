"""
AION-Core API Server -- FastAPI.
Point d entree web : Dashboard, Voice API, REST.
"""
import html
import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent.parent / "web" / "templates"

_VOICE_RESULTS: dict[str, dict] = {}
_VOICE_TTL = 300


def create_app(aion_app) -> FastAPI:
    """Cree et configure l application FastAPI."""

    app = FastAPI(
        title       = "AION-Core",
        description = "AI-First Personal Orchestrator",
        version     = aion_app.VERSION,
    )
    app.add_middleware(CORSMiddleware,
        allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None

    # ── Status ────────────────────────────────────────────────────

    @app.get("/api/status")
    async def api_status():
        return {"name": "AION-Core", "version": aion_app.VERSION,
                "status": "online", "apps": aion_app.app_router.available_apps}

    @app.get("/api/ping")
    async def api_ping():
        import socket
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            local_ip = "unknown"
        return {"status": "ok", "message": "AION-Core is running !",
                "local_ip": local_ip,
                "saved_url": aion_app.memory.recall("aion_public_url") or ""}

    # ── Voice API ─────────────────────────────────────────────────

    @app.post("/api/voice")
    async def voice_endpoint(request: Request):
        """Point d entree vocal -- iPhone Raccourcis / Siri."""
        body     = await request.json()
        text     = body.get("text", "").strip()
        img_b64  = body.get("image_data", "")
        img_mime = body.get("image_mime", "image/jpeg")

        if not text and not img_b64:
            return {"response": "Rien compris. Repetez.", "ok": False}
        if not aion_app.brain.is_available():
            return {"response": "GROQ_API_KEY non configuree.", "ok": False}

        result = aion_app.app_router.route(
            text=text or "Analyse cette image.",
            image_b64=img_b64 or None,
            image_mime=img_mime,
        )
        uid = str(uuid.uuid4())[:8]
        _VOICE_RESULTS[uid] = {**result, "query": text,
                                "created_at": time.time(),
                                "expires_at": time.time() + _VOICE_TTL}
        now = time.time()
        for k in [k for k, v in list(_VOICE_RESULTS.items()) if v.get("expires_at", 0) < now]:
            del _VOICE_RESULTS[k]

        saved_url = aion_app.memory.recall("aion_public_url") or ""
        req_host  = request.headers.get("host", "")
        if saved_url:
            base_url = saved_url.rstrip("/")
        elif req_host and not req_host.startswith("127") and not req_host.startswith("localhost"):
            base_url = f"http://{req_host}"
        else:
            base_url = str(request.base_url).rstrip("/")

        return {
            "response": result["response"], "app": result["app"],
            "result": result["result"],
            "url": f"{base_url}/voice/result/{uid}",
            "result_uid": uid, "ok": True,
        }

    @app.get("/voice/result/{uid}", response_class=HTMLResponse)
    async def voice_result(uid: str):
        data = _VOICE_RESULTS.get(uid)
        if not data:
            return HTMLResponse(
                "<html><body style='background:#0f1117;color:#e0e0e0;font-family:sans-serif;"
                "display:flex;align-items:center;justify-content:center;height:100vh;'>"
                "<div style='text-align:center;'><h2 style='color:#f44336;'>Page expiree</h2>"
                "<p style='color:#888;'>Ce resultat a expire.</p></div></body></html>",
                status_code=410)
        return HTMLResponse(_build_voice_page(uid, data))

    # ── Memory API ────────────────────────────────────────────────

    @app.get("/api/memory")
    async def get_memory():
        return aion_app.memory.list_memory()

    @app.post("/api/memory/{key}")
    async def set_memory(key: str, request: Request):
        body = await request.json()
        aion_app.memory.remember(key, body.get("value", ""), body.get("type", "info"))
        return {"ok": True, "key": key}

    @app.delete("/api/memory/{key}")
    async def del_memory(key: str):
        return {"ok": aion_app.memory.forget(key)}

    @app.post("/api/memory/import")
    async def import_memory(request: Request):
        """
        Importe un fichier memory.json complet dans la memoire AION.
        Supporte 2 formats :
          - Format AION natif : {"key": {"value": "...", "type": "..."}}
          - Format simple     : {"key": "valeur"}
        Body: {"data": {...}, "overwrite": true}
        """
        body      = await request.json()
        raw       = body.get("data", {})
        overwrite = body.get("overwrite", True)
        imported  = []
        skipped   = []

        for key, val in raw.items():
            # Ignorer les cles systeme
            if key.startswith("_"):
                skipped.append(key)
                continue
            # Ne pas ecraser si overwrite=False et cle existante
            if not overwrite and aion_app.memory.recall(key):
                skipped.append(key)
                continue
            # Format natif AION
            if isinstance(val, dict) and "value" in val:
                aion_app.memory.remember(key, str(val["value"]), val.get("type", "imported"))
            # Format simple
            elif isinstance(val, (str, int, float, bool)):
                aion_app.memory.remember(key, str(val), "imported")
            else:
                skipped.append(key)
                continue
            imported.append(key)

        return {
            "ok":       True,
            "imported": len(imported),
            "skipped":  len(skipped),
            "keys":     imported,
            "message":  f"{len(imported)} cle(s) importee(s) dans la memoire AION",
        }

    # ── Updater AION-Core ─────────────────────────────────────────

    @app.get("/api/update/status")
    async def update_status():
        """Etat de la mise a jour AION-Core."""
        if not hasattr(aion_app, "updater") or not aion_app.updater:
            return {"update_available": False, "error": "Updater non initialise"}
        return aion_app.updater.get_state()

    @app.post("/api/update/check")
    async def update_check():
        """Force une verification de mise a jour immediate."""
        if not hasattr(aion_app, "updater") or not aion_app.updater:
            return {"error": "Updater non initialise"}
        import asyncio
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, aion_app.updater.check_now)
        return result

    @app.post("/api/update/apply")
    async def update_apply():
        """Applique la mise a jour et redemarre AION-Core."""
        if not hasattr(aion_app, "updater") or not aion_app.updater:
            return {"success": False, "error": "Updater non initialise"}
        import asyncio
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, aion_app.updater.apply_update)
        return result

    @app.get("/api/update/banner", response_class=__import__("fastapi.responses",
             fromlist=["HTMLResponse"]).HTMLResponse)
    async def update_banner():
        """
        Fragment HTML htmx — banniere de mise a jour.
        Affichee dans le dashboard si update_available=True.
        """
        from fastapi.responses import HTMLResponse as _HR
        if not hasattr(aion_app, "updater") or not aion_app.updater:
            return _HR("")
        state = aion_app.updater.get_state()
        if not state.get("update_available"):
            return _HR("")  # Rien a afficher

        commits = state.get("commits_behind", 1)
        msg     = state.get("latest_message", "")[:60]
        date    = state.get("latest_date", "")
        sha     = state.get("remote_commit", "")[:8]

        banner = f'''
        <div id="update-banner" style="
          background:linear-gradient(135deg,rgba(30,144,255,.15),rgba(123,47,190,.15));
          border:1px solid rgba(30,144,255,.4);border-radius:10px;
          padding:14px 18px;margin-bottom:16px;
          display:flex;align-items:center;gap:14px;">
          <span style="font-size:1.5rem;">\U0001f504</span>
          <div style="flex:1;">
            <div style="font-weight:600;color:#1e90ff;margin-bottom:2px;">
              Mise a jour AION-Core disponible
              <span style="font-size:.75rem;color:#888;margin-left:8px;">{commits} commit(s)</span>
            </div>
            <div style="font-size:.82rem;color:#ccc;">{msg}</div>
            <div style="font-size:.75rem;color:#888;margin-top:2px;">
              SHA: {sha} &bull; {date}
            </div>
          </div>
          <div style="display:flex;gap:8px;flex-shrink:0;">
            <button onclick="applyAionUpdate()"
              style="background:#1e90ff;color:#fff;border:none;
              padding:8px 16px;border-radius:6px;cursor:pointer;
              font-size:.85rem;font-weight:600;">
              \u2B07\uFE0F Mettre a jour
            </button>
            <button onclick="document.getElementById('update-banner').remove()"
              style="background:transparent;border:1px solid #444;color:#888;
              padding:8px 12px;border-radius:6px;cursor:pointer;font-size:.82rem;">
              Plus tard
            </button>
          </div>
        </div>
        <script>
        function applyAionUpdate() {{
          if(!confirm("Mettre a jour AION-Core et redemarrer ?")) return;
          var btn = event.target;
          btn.textContent = "\u23f3 En cours...";
          btn.disabled = true;
          fetch("/api/update/apply", {{method:"POST"}})
            .then(r=>r.json())
            .then(d=>{{
              if(d.success) {{
                btn.textContent = "\u2705 Redemarrage...";
                document.getElementById("update-banner").style.background =
                  "rgba(76,175,80,.15)";
                setTimeout(()=>location.reload(), 5000);
              }} else {{
                btn.textContent = "\u274c Erreur";
                btn.disabled = false;
                alert(d.message || "Erreur lors de la mise a jour");
              }}
            }})
            .catch(e=>{{ btn.textContent="Erreur"; btn.disabled=false; }});
        }}
        </script>
        '''
        return _HR(banner)

    # ── Route IA ──────────────────────────────────────────────────

    @app.post("/api/route")
    async def route_request(request: Request):
        """
        Route une requete texte vers la bonne app.
        Detecte automatiquement les JSON colles dans le texte
        pour faciliter l'import memoire via le chat.
        """
        import re as _re, json as _json
        body     = await request.json()
        text     = body.get("text", "")
        img_b64  = body.get("image_data")
        img_mime = body.get("image_mime", "image/jpeg")

        # Detection JSON dans le texte -> import memoire direct
        import_keywords = ["import", "importe", "memoire", "memory",
                           "charger", "ajouter ces", "mets dans", "enregistre", "cles"]
        json_in_text = None
        if text and "{" in text:
            m = _re.search(r'\{.+\}', text, _re.DOTALL)
            if m:
                try:
                    json_in_text = _json.loads(m.group(0))
                except Exception:
                    pass

        if json_in_text and any(kw in text.lower() for kw in import_keywords):
            import_result = aion_app.app_router._handle_memory(
                "import_json", {"data": json_in_text}
            )
            return {
                "app":      "memory",
                "action":   "import_json",
                "params":   {},
                "result":   import_result,
                "response": import_result,
            }

        return aion_app.app_router.route(
            text       = text,
            image_b64  = img_b64,
            image_mime = img_mime,
        )

    @app.get("/api/apps")
    async def api_list_apps():
        """Liste les apps disponibles dans le router."""
        return {"apps": aion_app.app_router.available_apps}

    @app.get("/api/apps/status", response_class=__import__("fastapi.responses", fromlist=["HTMLResponse"]).HTMLResponse)
    async def api_apps_status():
        """
        Statut live de toutes les apps — appele par le dashboard htmx.
        Retourne un fragment HTML avec pastilles online/offline.
        """
        import json as _json
        from pathlib import Path as _Path
        from fastapi.responses import HTMLResponse as _HTMLResponse

        reg_file = _Path("apps.json")
        registry = _json.loads(reg_file.read_text(encoding="utf-8")) if reg_file.exists() else {}

        icons = {
            "check":     "\u2705",
            "circle":    "\U0001f535",
            "clipboard": "\U0001f4cb",
            "monitor":   "\U0001f5a5\ufe0f",
            "clock":     "\u23f0",
            "package":   "\U0001f4e6",
        }
        rows = []
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
                is_online = True  # apps locales (system, timer)

            color    = "var(--green)" if is_online else "var(--red)"
            status   = "online" if is_online else "offline"
            icon_key = cfg.get("icon", "package")
            icon     = icons.get(icon_key, "\U0001f4e6")
            name     = cfg.get("name", app_id)
            rows.append(
                f'<div style="display:flex;align-items:center;gap:10px;padding:7px 0;'
                f'border-bottom:1px solid var(--border);font-size:.85rem;">'
                f'<span>{icon}</span>'
                f'<span style="flex:1;"><a href="/app/{app_id}" style="color:var(--text);text-decoration:none;">{name}</a></span>'
                f'<span style="color:{color};font-size:.78rem;font-weight:600;">{status}</span>'
                f'</div>'
            )

        html = "\n".join(rows) if rows else '<p style="color:var(--dim);font-size:.83rem;">Aucune app active.</p>'
        return _HTMLResponse(html)

    # ── Pages Web statiques ───────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def web_dashboard(request: Request):
        if templates is None:
            return HTMLResponse("<h1>AION-Core</h1><a href='/docs'>API Docs</a>")
        mem    = aion_app.memory.list_memory()
        recent = dict(list(mem.items())[-5:]) if mem else {}
        return templates.TemplateResponse(request=request, name="dashboard.html", context={
            "version": aion_app.VERSION, "active": "dashboard",
            "ai_available": aion_app.brain.is_available(),
            "apps_count": len(aion_app.app_router.available_apps),
            "memory_count": len(mem), "recent_memory": recent,
        })

    @app.get("/chat", response_class=HTMLResponse)
    async def web_chat(request: Request):
        if templates is None:
            return HTMLResponse("<p>Templates not found</p>")
        return templates.TemplateResponse(request=request, name="chat.html", context={
            "version": aion_app.VERSION, "active": "chat",
            "ai_available": aion_app.brain.is_available(),
            "groq_model": aion_app.brain.model,
        })

    @app.get("/memory", response_class=HTMLResponse)
    async def web_memory():
        mem  = aion_app.memory.list_memory()
        rows = "".join(
            f"<tr><td style='color:#1e90ff;padding:8px 12px;'>{k}</td>"
            f"<td style='padding:8px 12px;color:#888;'>{v.get('type','')}</td>"
            f"<td style='padding:8px 12px;'>{v.get('value','')[:60]}</td></tr>"
            for k, v in mem.items()
        )
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
        <style>body{{font-family:Segoe UI;background:#0f1117;color:#e0e0e0;padding:20px;}}
        table{{width:100%;border-collapse:collapse;background:#1a1d27;border-radius:8px;overflow:hidden;}}
        th{{background:#041E42;color:#fff;padding:10px 12px;text-align:left;}}
        tr:hover{{background:#2a2d3e;}}</style></head>
        <body><h2 style="color:#1e90ff;margin-bottom:16px;">&#x1F9E0; AION Memory ({len(mem)} items)</h2>
        <table><thead><tr><th>Cle</th><th>Type</th><th>Valeur</th></tr></thead>
        <tbody>{rows}</tbody></table>
        <p style="color:#888;margin-top:12px;font-size:.8rem;">
        <a href="/" style="color:#1e90ff;">&#x2190; Dashboard</a></p></body></html>""")

    @app.get("/settings", response_class=HTMLResponse)
    async def web_settings():
        model  = aion_app.brain.model
        models = aion_app.brain.list_models() if aion_app.brain.is_available() else []
        ok     = aion_app.brain.is_available()
        apps_rows = "".join(
            f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
            f'border-bottom:1px solid #2a2d3e;font-size:.85rem;">'
            f'<span>{a}</span><span style="color:#888;">&#x2705; connecte</span></div>'
            for a in aion_app.app_router.available_apps
        )
        return HTMLResponse(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
        <style>body{{font-family:Segoe UI;background:#0f1117;color:#e0e0e0;padding:20px;}}
        .card{{background:#1a1d27;border-radius:8px;padding:16px;margin-bottom:14px;border:1px solid #2a2d3e;}}
        h3{{color:#1e90ff;margin-bottom:10px;}}
        .row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2d3e;font-size:.85rem;}}
        </style></head><body>
        <h2 style="color:#1e90ff;margin-bottom:16px;">&#x2699;&#xFE0F; Settings</h2>
        <div class="card"><h3>&#x1F916; IA</h3>
        <div class="row"><span>Modele</span><span style="color:#4caf50;">{model}</span></div>
        <div class="row"><span>Groq</span>
        <span style="color:{'#4caf50' if ok else '#f44336'};">{'&#x2705;' if ok else '&#x274C;'}</span></div>
        <div class="row"><span>Modeles dispo</span>
        <span style="color:#888;">{", ".join(models[:3]) if models else "N/A"}</span></div></div>
        <div class="card"><h3>&#x1F4CA; Apps</h3>{apps_rows}</div>
        <p style="color:#888;margin-top:12px;font-size:.8rem;">
        <a href="/" style="color:#1e90ff;">&#x2190; Dashboard</a></p></body></html>""")

    # ── Modules de routes externes ────────────────────────────────

    # 1. Navigation dynamique sidebar
    try:
        from aion_core.api.apps_nav import register_nav_routes
        register_nav_routes(app, aion_app)
        logger.info("Nav routes OK")
    except Exception as _e:
        logger.warning("Nav routes: %s", _e)

    # 2. Proxy apps dynamique /app/{app_id}
    try:
        from aion_core.api.app_proxy import register_proxy_routes
        register_proxy_routes(app, aion_app)
        logger.info("App proxy routes OK")
    except Exception as _e:
        logger.warning("App proxy routes: %s", _e)

    # 3. App Store routes
    try:
        from aion_core.api.store_routes import register_store_routes
        register_store_routes(app, aion_app)
        logger.info("Store routes OK")
    except Exception as _e:
        logger.warning("Store routes: %s", _e)

    # 4. QuickMind routes legacy
    try:
        from aion_core.api.quickmind_routes import register_routes as _reg_qm
        _reg_qm(app, aion_app)
    except Exception as _e:
        logger.warning("QuickMind routes: %s", _e)

    # 5. Discovery routes
    try:
        from aion_core.api.discovery_routes import register_discovery_routes
        register_discovery_routes(app, aion_app)
    except Exception as _e:
        logger.warning("Discovery routes: %s", _e)

    return app


def _build_voice_page(uid: str, data: dict) -> str:
    """Genere la page HTML de resultat vocal (mobile-first)."""
    import re
    query    = html.escape(data.get("query", ""))
    app_name = html.escape(data.get("app", ""))
    response = html.escape(data.get("response", ""))
    result   = data.get("result", "")
    created  = time.strftime("%H:%M:%S", time.localtime(data.get("created_at", 0)))
    expires  = max(0, int(data.get("expires_at", 0) - time.time()))

    color = {"quickmind":"#4caf50","ado":"#0078d4","system":"#9c27b0",
             "timer":"#ff9800","search":"#1e90ff"}.get(app_name, "#888")

    result_html = ""
    if result:
        items = []
        for line in result.splitlines():
            line = line.strip()
            if not line:
                continue
            if "#" in line and app_name == "ado":
                m = re.search(r"#(\d+)", line)
                if m:
                    aid = m.group(1)
                    url = f"https://dev.azure.com/Premiertech/PTG%20-%20TMM%20D2/_workitems/edit/{aid}"
                    items.append(
                        f'<a href="{url}" style="display:flex;align-items:center;gap:10px;'
                        f'background:#1a1d27;border-radius:8px;padding:12px;margin-bottom:6px;'
                        f'text-decoration:none;color:#e0e0e0;border:1px solid #2a2d3e;">'
                        f'<span style="color:#0078d4;font-weight:700;">#{aid}</span>'
                        f'<span style="flex:1;font-size:.85rem;">{html.escape(line)}</span>'
                        f'<span style="color:#888;">&#x279C;</span></a>'
                    )
                    continue
            items.append(
                f'<div style="background:#1a1d27;border-radius:6px;padding:10px 12px;'
                f'margin-bottom:5px;font-size:.85rem;color:#ccc;">{html.escape(line)}</div>'
            )
        result_html = "\n".join(items)

    return f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0">
<title>AION &#x2014; {query[:30]}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,sans-serif;background:#0f1117;color:#e0e0e0;}}
.hdr{{background:#151821;border-bottom:2px solid {color};padding:14px 16px;
  display:flex;align-items:center;gap:10px;}}
.hdr h1{{color:{color};font-size:1.1rem;}}
.badge{{background:{color}22;color:{color};border:1px solid {color}44;
  padding:3px 10px;border-radius:12px;font-size:.72rem;font-weight:600;}}
.query{{background:#1a1d27;border-left:3px solid {color};padding:12px 16px;
  margin:12px;border-radius:0 8px 8px 0;font-size:.9rem;color:#ccc;font-style:italic;}}
.vresp{{background:#1a1d27;border-radius:10px;padding:14px 16px;margin:0 12px 12px;font-size:1rem;line-height:1.5;}}
.results{{padding:0 12px 20px;}}
.results h2{{font-size:.78rem;text-transform:uppercase;letter-spacing:1px;color:#888;margin-bottom:10px;}}
.refresh{{display:block;text-align:center;background:#1a1d27;border:1px solid #2a2d3e;
  color:#888;padding:10px;margin:0 12px 12px;border-radius:8px;text-decoration:none;font-size:.85rem;}}
.exp{{color:#444;font-size:.7rem;text-align:center;padding:4px 0 20px;}}
</style></head><body>
<div class="hdr">
  <span style="font-size:1.4rem;">&#x1F916;</span><h1>AION-Core</h1>
  <span class="badge">{app_name}</span>
  <span style="margin-left:auto;color:#555;font-size:.72rem;">{created}</span>
</div>
<div class="query">&#x201C;{query}&#x201D;</div>
<div class="vresp"><span style="font-size:1.2rem;margin-right:8px;">&#x1F50A;</span>{response}</div>
{"<div class='results'><h2>Resultats</h2>" + result_html + "</div>" if result_html else ""}
<a href="/voice/result/{uid}" class="refresh">&#x21BA; Rafraichir</a>
<div class="exp">Expire dans {expires}s</div>
</body></html>"""