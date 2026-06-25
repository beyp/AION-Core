"""
app_proxy.py -- Route /app/{app_id}

Comportement selon le type :
- fastapi / api_external + url  -> iframe plein ecran + barre retour
- local (system, timer)         -> page generee avec commande IA
- python/desktop sans url       -> page controle start/stop/status
"""
import json
import logging
from pathlib import Path
from fastapi import Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

ICON_MAP = {
    "check":"\u2705","circle":"\U0001f535","clipboard":"\U0001f4cb",
    "monitor":"\U0001f5a5\ufe0f","clock":"\u23f0","brain":"\U0001f9e0",
    "mail":"\u2709\ufe0f","package":"\U0001f4e6",
}


def _load_registry() -> dict:
    result = {"apps": {}}
    for f in [Path("apps.json"), Path("apps.local.json")]:
        if f.exists():
            try:
                with open(f, encoding="utf-8") as fp:
                    result["apps"].update(json.load(fp).get("apps", {}))
            except Exception:
                pass
    return result


def _full_page(title: str, content_html: str, app_id: str,
               app_url: str, app_type: str, icon: str,
               version: str, ai_ok: bool) -> str:
    """Genere une page complete avec sidebar htmx — identique a base.html."""
    groq_badge = (
        '<span style="background:rgba(76,175,80,.2);color:#4caf50;padding:2px 8px;'
        'border-radius:10px;font-size:.75rem;font-weight:600;">\u25cf Groq</span>'
        if ai_ok else
        '<span style="background:rgba(244,67,54,.2);color:#f44336;padding:2px 8px;'
        'border-radius:10px;font-size:.75rem;font-weight:600;">\u25cf Groq offline</span>'
    )
    type_color = {
        "fastapi":"#4caf50","api_external":"#9c27b0",
        "local":"#1e90ff","docker":"#ff9800","python":"#ff9800"
    }.get(app_type, "#888")

    return f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title} \u2014 AION-Core</title>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
:root[data-theme="dark"]{{--bg:#0f1117;--sb:#13161f;--card:#1a1d27;--border:#2a2d3e;
  --text:#e0e0e0;--dim:#888;--accent:#1e90ff;--green:#4caf50;--red:#f44336;--orange:#ff9800;--hdr:#151821;}}
:root[data-theme="light"]{{--bg:#f0f2f5;--sb:#fff;--card:#fff;--border:#dde1f0;
  --text:#1a1a2e;--dim:#666;--accent:#1e90ff;--hdr:#fff;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:"Segoe UI",sans-serif;background:var(--bg);color:var(--text);
  display:flex;flex-direction:column;height:100vh;overflow:hidden;}}
header{{background:var(--hdr);border-bottom:2px solid var(--accent);
  padding:0 16px;height:52px;display:flex;align-items:center;gap:10px;flex-shrink:0;}}
header h1{{color:var(--accent);font-size:1.2rem;font-weight:700;}}
.spacer{{flex:1;}}
.hbtn{{background:var(--card);border:1px solid var(--border);color:var(--text);
  padding:5px 12px;border-radius:6px;cursor:pointer;font-size:.82rem;text-decoration:none;}}
.hbtn:hover{{background:var(--accent);color:#fff;}}
.layout{{display:flex;flex:1;overflow:hidden;}}
.sidebar{{width:220px;background:var(--sb);border-right:1px solid var(--border);
  display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;padding:10px 0;
  transition:width .2s ease;}}
.sidebar.collapsed{{width:52px;overflow:hidden;}}
.sidebar.collapsed .nav-label,.sidebar.collapsed .sb-sec{{display:none;}}
.sidebar.collapsed .nav-item{{justify-content:center;padding:10px 0;}}
.sidebar.collapsed .nav-icon{{width:auto;}}
.collapse-btn{{background:transparent;border:none;color:var(--dim);cursor:pointer;
  padding:8px 14px;font-size:.9rem;text-align:left;width:100%;display:flex;align-items:center;gap:8px;}}
.collapse-btn:hover{{color:var(--accent);}}
.sb-sec{{padding:4px 12px;font-size:.68rem;text-transform:uppercase;letter-spacing:1px;
  color:var(--dim);margin-top:8px;}}
.nav-item{{display:flex;align-items:center;gap:10px;padding:9px 14px;
  border-left:3px solid transparent;font-size:.88rem;text-decoration:none;color:var(--text);}}
.nav-item:hover{{background:rgba(30,144,255,.08);}}
.nav-item.active{{background:rgba(30,144,255,.12);border-left-color:var(--accent);
  color:var(--accent);font-weight:600;}}
.nav-icon{{width:20px;text-align:center;}} .nav-label{{flex:1;}}
.main{{flex:1;overflow:hidden;display:flex;flex-direction:column;}}
.app-bar{{background:var(--card);border-bottom:1px solid var(--border);
  padding:8px 16px;display:flex;align-items:center;gap:10px;flex-shrink:0;font-size:.88rem;}}
.app-content{{flex:1;overflow:hidden;}}
.app-iframe{{width:100%;height:100%;border:none;background:var(--bg);}}
::-webkit-scrollbar{{width:5px;}} ::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px;}}
</style>
</head>
<body>
<header>
  <span style="font-size:1.2rem;">\U0001f916</span>
  <h1>AION-Core</h1><span style="color:var(--dim);font-size:.75rem;">v{version}</span>
  <div class="spacer"></div>
  {groq_badge}
  <button class="hbtn" onclick="toggleTheme()">\U0001f313</button>
</header>
<div class="layout">
  <nav class="sidebar" id="sb">
    <button class="collapse-btn" onclick="toggleSidebar()" title="Réduire/Agrandir">
      <span id="sb-icon">\u276E</span>
      <span class="nav-label" id="sb-lbl" style="font-size:.78rem;">Réduire</span>
    </button>
    <div class="sb-sec">Navigation</div>
    <a href="/" class="nav-item"><span class="nav-icon">\U0001f4ca</span><span class="nav-label">Dashboard</span></a>
    <a href="/chat" class="nav-item"><span class="nav-icon">\U0001f916</span><span class="nav-label">IA Chat</span></a>
    <div class="sb-sec">Apps</div>
    <div id="sidebar-apps" hx-get="/api/nav/apps/sidebar" hx-trigger="load" hx-swap="innerHTML">
      <div style="padding:8px 14px;color:var(--dim);font-size:.8rem;">\u2026</div>
    </div>
    <div class="sb-sec">AION</div>
    <a href="/store" class="nav-item"><span class="nav-icon">\U0001f3ea</span><span class="nav-label">App Store</span></a>
    <a href="/docker" class="nav-item"><span class="nav-icon">\U0001f433</span><span class="nav-label">Docker</span></a>
    <a href="/memory" class="nav-item"><span class="nav-icon">\U0001f9e0</span><span class="nav-label">Memory</span></a>
    <a href="/settings" class="nav-item"><span class="nav-icon">\u2699\ufe0f</span><span class="nav-label">Settings</span></a>
  </nav>
  <main class="main">
    <!-- Barre de l'app -->
    <div class="app-bar">
      <a href="/" class="hbtn" style="padding:4px 10px;font-size:.78rem;">\u2190</a>
      <span style="font-size:1rem;">{icon}</span>
      <span style="font-weight:600;">{title}</span>
      <span style="font-size:.7rem;padding:2px 7px;border-radius:10px;font-weight:600;
        background:color-mix(in srgb,{type_color} 20%,transparent);color:{type_color};">{app_type}</span>
      <div class="spacer"></div>
      {f'<a href="{app_url}" target="_blank" class="hbtn" style="font-size:.75rem;">\u2197 {app_url}</a>' if app_url else ""}
    </div>
    <div class="app-content">{content_html}</div>
  </main>
</div>
<script>
document.addEventListener("htmx:afterSwap", function(e) {{
  if (e.target.id === "sidebar-apps") {{
    e.target.querySelectorAll(".nav-item").forEach(function(a) {{
      if (a.getAttribute("href") === window.location.pathname) a.classList.add("active");
    }});
  }}
}});
function toggleTheme() {{
  var h = document.documentElement;
  h.setAttribute("data-theme", h.getAttribute("data-theme") === "dark" ? "light" : "dark");
  localStorage.setItem("theme", h.getAttribute("data-theme"));
}}
function toggleSidebar() {{
  var sb = document.getElementById("sb");
  var collapsed = sb.classList.toggle("collapsed");
  localStorage.setItem("sidebarCollapsed", collapsed ? "1" : "0");
  var icon = document.getElementById("sb-icon");
  var lbl  = document.getElementById("sb-lbl");
  if (icon) icon.textContent = collapsed ? "\u276F" : "\u276E";
  if (lbl)  lbl.textContent  = collapsed ? "" : "R\u00e9duire";
}}
(function() {{
  var t = localStorage.getItem("theme");
  if (t) document.documentElement.setAttribute("data-theme", t);
  if (localStorage.getItem("sidebarCollapsed") === "1") {{
    var sb = document.getElementById("sb");
    if (sb) {{
      sb.classList.add("collapsed");
      var icon = document.getElementById("sb-icon");
      if (icon) icon.textContent = "\u276F";
    }}
  }}
}})();
</script>
</body></html>"""


def register_proxy_routes(app, aion_app):
    """Enregistre la route proxy /app/{{app_id}}."""

    @app.get("/app/{app_id}", response_class=HTMLResponse)
    async def app_proxy_view(app_id: str, request: Request):
        registry = _load_registry()
        cfg = registry.get("apps", {}).get(app_id)

        if not cfg or cfg.get("status") not in ("active", "installed"):
            return HTMLResponse(
                f"<p style='color:#f44336;padding:20px;'>App '{app_id}' introuvable.</p>",
                status_code=404)

        app_type = cfg.get("type", "local")
        app_url  = cfg.get("url", "")
        icon     = ICON_MAP.get(cfg.get("icon", "package"), "\U0001f4e6")
        name     = cfg.get("name", app_id.title())
        version  = aion_app.VERSION
        ai_ok    = aion_app.brain.is_available()

        # ── FastAPI / API externe avec URL → iframe plein écran ──────────
        if app_url and app_type in ("fastapi", "api_external"):
            # Health check rapide
            health_info = ""
            try:
                import requests as _rq
                hr = _rq.get(app_url.rstrip("/") + cfg.get("health_endpoint", "/health"), timeout=1.5)
                if hr.status_code < 400:
                    hdata = hr.json()
                    stats = " &bull; ".join(
                        f"<strong>{v}</strong> {k}"
                        for k, v in hdata.items()
                        if k not in ("status","app","time") and v is not None
                    )[:80]
                    health_info = f'<span style="color:#4caf50;font-size:.75rem;">\u25cf En ligne{" | "+stats if stats else ""}</span>'
                else:
                    health_info = '<span style="color:#f44336;font-size:.75rem;">\u25cf Hors ligne</span>'
            except Exception:
                health_info = '<span style="color:#888;font-size:.75rem;">\u25cf ...</span>'

            # Iframe plein écran — QuickMind/ProjectMind s'affichent directement
            # NOTE : window.location.origin dans l'app retournera :8000 (AION)
            # → les fetch() de l'app iront sur AION au lieu de :8765
            # → "Chargement..." permanent
            # SOLUTION PROPRE : afficher l'app dans son propre onglet ET un iframe
            # avec src pointant vers le bon port — le navigateur le bloque en cross-origin
            # mais uniquement si l'app fait des fetch() relatifs.
            # → Pour QuickMind : modifier run_api.py pour utiliser l'URL absolue
            # → En attendant : on affiche l'iframe et on laisse l'utilisateur voir
            #   si ça marche (les apps qui utilisent des URLs absolues fonctionneront)

            iframe_html = f"""
            <iframe
              src="{app_url}"
              class="app-iframe"
              title="{name}"
              allow="fullscreen"
              loading="lazy"
              id="app-frame-{app_id}"
            ></iframe>
            <div id="iframe-fallback-{app_id}" style="display:none;padding:20px;text-align:center;">
              <p style="color:var(--dim);margin-bottom:12px;">
                L'app ne s'affiche pas correctement dans l'iframe.
              </p>
              <a href="{app_url}" target="_blank"
                 style="background:var(--accent);color:#fff;text-decoration:none;
                 padding:10px 24px;border-radius:8px;font-weight:600;">
                \U0001f680 Ouvrir {name} dans un nouvel onglet
              </a>
            </div>
            <script>
            // Détecter si l'iframe charge correctement
            var frame = document.getElementById("app-frame-{app_id}");
            var fallback = document.getElementById("iframe-fallback-{app_id}");
            if (frame) {{
              setTimeout(function() {{
                try {{
                  // Si l'iframe est vide ou en erreur, afficher le fallback
                  var doc = frame.contentDocument || frame.contentWindow.document;
                  if (!doc || doc.body.innerHTML.trim() === "") {{
                    frame.style.display = "none";
                    fallback.style.display = "block";
                  }}
                }} catch(e) {{
                  // Cross-origin: l'iframe a chargé quelque chose (bon signe)
                }}
              }}, 3000);
            }}
            </script>
            """

            # Ajouter health_info dans la barre de l'app via JS injection
            content_html = iframe_html
            # Patcher la barre avec health_info
            return HTMLResponse(_full_page(
                name, content_html, app_id, app_url, app_type, icon,
                version, ai_ok
            ).replace(
                f'<span style="font-weight:600;">{name}</span>',
                f'<span style="font-weight:600;">{name}</span> {health_info}'
            ))

        # ── App Python/desktop sans URL → page de contrôle ───────────────
        elif app_type in ("python", "desktop") and not app_url:
            from aion_core.store.process_manager import ProcessManager
            pm = ProcessManager()
            store_cfg    = cfg.get("store", {})
            autostart    = cfg.get("autostart", {})
            install_path = store_cfg.get("install_path", "") or autostart.get("path", "")
            port         = int(autostart.get("port", 0))
            is_running   = pm.is_running(app_id, port)

            run_color  = "#4caf50" if is_running else "#f44336"
            run_status = "\u25cf En cours" if is_running else "\u25cf Arrete"

            content_html = f"""
            <div style="padding:20px;overflow-y:auto;height:100%;">
              <div style="background:var(--card);border:1px solid var(--border);
                   border-radius:10px;padding:16px;margin-bottom:12px;">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">
                  <span style="font-size:2rem;">{icon}</span>
                  <div>
                    <div style="font-weight:600;font-size:1rem;">{name}</div>
                    <div style="font-size:.82rem;color:{run_color};">{run_status}</div>
                    <div style="font-size:.75rem;color:var(--dim);">{install_path}</div>
                  </div>
                </div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                  <button onclick="ctrlAction('start')"
                    style="background:rgba(76,175,80,.15);border:1px solid rgba(76,175,80,.4);
                    color:#4caf50;border-radius:6px;padding:8px 16px;cursor:pointer;font-weight:600;">
                    \u25b6 Start</button>
                  <button onclick="ctrlAction('stop')"
                    style="background:rgba(244,67,54,.15);border:1px solid rgba(244,67,54,.4);
                    color:#f44336;border-radius:6px;padding:8px 16px;cursor:pointer;font-weight:600;">
                    \u25a0 Stop</button>
                  <button onclick="ctrlAction('update')"
                    style="background:rgba(30,144,255,.15);border:1px solid rgba(30,144,255,.4);
                    color:#1e90ff;border-radius:6px;padding:8px 16px;cursor:pointer;">
                    \U0001f504 Update</button>
                  <a href="/store" style="background:transparent;border:1px solid var(--border);
                    color:var(--dim);border-radius:6px;padding:8px 16px;text-decoration:none;font-size:.85rem;">
                    \U0001f3ea App Store</a>
                </div>
                <div id="ctrl-result" style="margin-top:10px;font-size:.82rem;display:none;
                     padding:6px 10px;border-radius:5px;"></div>
              </div>
              <div style="background:var(--card);border:1px solid var(--border);
                   border-radius:10px;padding:14px;">
                <div style="font-size:.78rem;color:var(--dim);margin-bottom:8px;">\U0001f916 Commande IA</div>
                <div style="display:flex;gap:8px;">
                  <input id="app-cmd" type="text"
                    placeholder="Ex: lance {app_id}, arrete {app_id}..."
                    style="flex:1;background:#12141f;border:1px solid var(--border);
                      color:var(--text);padding:9px 12px;border-radius:6px;font-size:.85rem;"
                    onkeydown="if(event.key==='Enter') sendCmd()">
                  <button onclick="sendCmd()"
                    style="background:var(--accent);color:#fff;border:none;
                      padding:9px 16px;border-radius:6px;cursor:pointer;">Envoyer</button>
                </div>
                <div id="cmd-result" style="margin-top:8px;font-size:.82rem;color:#4caf50;min-height:20px;"></div>
              </div>
            </div>
            <script>
            function ctrlAction(action) {{
              var res = document.getElementById("ctrl-result");
              res.style.display="block"; res.style.color="var(--orange)"; res.textContent="\u23f3 En cours...";
              var urls = {{start:"/api/store/start/{app_id}",stop:"/api/store/stop/{app_id}",
                           update:"/api/store/update/{app_id}"}};
              fetch(urls[action], {{method:"POST"}})
                .then(function(r){{return r.json();}})
                .then(function(d){{
                  res.style.color=d.success?"var(--green)":"var(--red)";
                  res.textContent=d.message;
                  if(d.success) setTimeout(function(){{location.reload();}}, 1500);
                }})
                .catch(function(e){{res.style.color="var(--red)";res.textContent="Erreur: "+e;}});
            }}
            function sendCmd() {{
              var i=document.getElementById("app-cmd"),r=document.getElementById("cmd-result"),t=i.value.trim();
              if(!t) return; r.style.color="var(--orange)"; r.textContent="\u23f3 AION..."; i.value="";
              fetch("/api/route",{{method:"POST",headers:{{"Content-Type":"application/json"}},
                body:JSON.stringify({{text:t}})}})
              .then(function(x){{return x.json();}})
              .then(function(d){{r.style.color="var(--green)";r.textContent=d.response||d.result||"OK";}})
              .catch(function(e){{r.style.color="var(--red)";r.textContent="Erreur: "+e;}});
            }}
            </script>
            """
            return HTMLResponse(_full_page(name, content_html, app_id, app_url, app_type, icon, version, ai_ok))

        # ── App locale (system, timer) → page commande IA ────────────────
        else:
            connector = aion_app.app_router._apps.get(app_id)
            raw = ""
            if connector:
                try:
                    raw = connector.execute("status", {})
                except Exception as e:
                    raw = f"Erreur : {e}"
            content_html = f"""
            <div style="padding:20px;overflow-y:auto;height:100%;">
              <div style="background:var(--card);border:1px solid var(--border);
                   border-radius:10px;padding:16px;margin-bottom:12px;max-width:700px;">
                <pre style="color:#4caf50;font-family:Cascadia Code,Consolas,monospace;
                     font-size:.85rem;white-space:pre-wrap;line-height:1.6;">{raw}</pre>
              </div>
              <div style="background:var(--card);border:1px solid var(--border);
                   border-radius:10px;padding:14px;max-width:700px;">
                <div style="font-size:.78rem;color:var(--dim);margin-bottom:8px;">\U0001f916 Commande AION IA</div>
                <div style="display:flex;gap:8px;">
                  <input id="app-cmd" type="text"
                    placeholder="Ex: status system, timer 25 minutes..."
                    style="flex:1;background:#12141f;border:1px solid var(--border);
                      color:var(--text);padding:9px 12px;border-radius:6px;font-size:.85rem;"
                    onkeydown="if(event.key==='Enter') sendCmd()">
                  <button onclick="sendCmd()"
                    style="background:var(--accent);color:#fff;border:none;
                      padding:9px 16px;border-radius:6px;cursor:pointer;">Envoyer</button>
                </div>
                <div id="cmd-result" style="margin-top:8px;font-size:.85rem;color:#4caf50;min-height:20px;"></div>
              </div>
            </div>
            <script>
            function sendCmd() {{
              var i=document.getElementById("app-cmd"),r=document.getElementById("cmd-result"),t=i.value.trim();
              if(!t) return; r.style.color="var(--orange)"; r.textContent="\u23f3 AION..."; i.value="";
              fetch("/api/route",{{method:"POST",headers:{{"Content-Type":"application/json"}},
                body:JSON.stringify({{text:t}})}})
              .then(function(x){{return x.json();}})
              .then(function(d){{r.style.color="var(--green)";r.textContent=d.response||d.result||"OK";}})
              .catch(function(e){{r.style.color="var(--red)";r.textContent="Erreur: "+e;}});
            }}
            </script>
            """
            return HTMLResponse(_full_page(name, content_html, app_id, app_url, app_type, icon, version, ai_ok))
