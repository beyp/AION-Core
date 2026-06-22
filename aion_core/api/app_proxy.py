"""
app_proxy.py -- Route /app/{app_id} dynamique.

Comportement par type d'app :
- fastapi / api_external + url -> iframe vers l'URL de l'app
- local (system, timer...)     -> page generee par AION avec commande IA
"""
import json
import logging
from pathlib import Path
from fastapi import Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

ICON_MAP = {
    "check":"✅","circle":"🔵","clipboard":"📋",
    "monitor":"🖥️","clock":"⏰","brain":"🧠",
    "mail":"✉️","package":"📦",
}


def _load_registry() -> dict:
    """Fusionne apps.json (built-in) + apps.local.json (perso)."""
    result = {"apps": {}}
    for reg_file in [Path("apps.json"), Path("apps.local.json")]:
        if reg_file.exists():
            try:
                with open(reg_file, encoding="utf-8") as f:
                    result["apps"].update(json.load(f).get("apps", {}))
            except Exception:
                pass
    return result


def _sidebar_nav(active_id: str, version: str, ai_available: bool) -> str:
    """Genere le HTML complet de la page avec sidebar dynamique."""
    ai_badge = (
        '<span style="background:rgba(76,175,80,.2);color:#4caf50;padding:2px 8px;'
        'border-radius:10px;font-size:.75rem;font-weight:600;">● Groq</span>'
        if ai_available else
        '<span style="background:rgba(244,67,54,.2);color:#f44336;padding:2px 8px;'
        'border-radius:10px;font-size:.75rem;font-weight:600;">● Groq offline</span>'
    )
    return f"""<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
:root[data-theme="dark"]{{--bg:#0f1117;--sb:#13161f;--card:#1a1d27;--border:#2a2d3e;
  --text:#e0e0e0;--dim:#888;--accent:#1e90ff;--green:#4caf50;--red:#f44336;--hdr:#151821;}}
:root[data-theme="light"]{{--bg:#f0f2f5;--sb:#fff;--card:#fff;--border:#dde1f0;
  --text:#1a1a2e;--dim:#666;--accent:#1e90ff;--green:#2e7d32;--red:#c62828;--hdr:#fff;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:"Segoe UI",sans-serif;background:var(--bg);color:var(--text);
  display:flex;flex-direction:column;height:100vh;overflow:hidden;}}
header{{background:var(--hdr);border-bottom:2px solid var(--accent);
  padding:0 20px;height:52px;display:flex;align-items:center;gap:12px;flex-shrink:0;}}
header h1{{color:var(--accent);font-size:1.2rem;font-weight:700;}}
.spacer{{flex:1;}}
.hbtn{{background:var(--card);border:1px solid var(--border);color:var(--text);
  padding:5px 12px;border-radius:6px;cursor:pointer;font-size:.82rem;text-decoration:none;}}
.hbtn:hover{{background:var(--accent);color:#fff;}}
.layout{{display:flex;flex:1;overflow:hidden;}}
.sidebar{{width:220px;background:var(--sb);border-right:1px solid var(--border);
  display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;padding:10px 0;}}
.sb-sec{{padding:4px 12px;font-size:.68rem;text-transform:uppercase;letter-spacing:1px;
  color:var(--dim);margin-top:8px;}}
.nav-item{{display:flex;align-items:center;gap:10px;padding:9px 14px;
  border-left:3px solid transparent;font-size:.88rem;text-decoration:none;color:var(--text);}}
.nav-item:hover{{background:rgba(30,144,255,.08);}}
.nav-item.active{{background:rgba(30,144,255,.12);border-left-color:var(--accent);
  color:var(--accent);font-weight:600;}}
.nav-icon{{width:20px;text-align:center;}}
.nav-label{{flex:1;}}
.nav-dot{{width:6px;height:6px;border-radius:50%;background:var(--dim);
  margin-left:auto;flex-shrink:0;}}
.main{{flex:1;overflow:hidden;display:flex;flex-direction:column;}}
.app-bar{{background:var(--card);border-bottom:1px solid var(--border);
  padding:10px 20px;display:flex;align-items:center;gap:12px;flex-shrink:0;}}
.app-content{{flex:1;overflow:hidden;}}
.app-iframe{{width:100%;height:100%;border:none;}}
::-webkit-scrollbar{{width:5px;}}
::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px;}}
</style>
"""


def register_proxy_routes(app, aion_app):
    """Enregistre la route proxy /app/{{app_id}}."""

    @app.get("/app/{app_id}", response_class=HTMLResponse)
    async def app_proxy_view(app_id: str, request: Request):
        registry = _load_registry()
        cfg = registry.get("apps", {}).get(app_id)

        if not cfg or cfg.get("status") not in ("active", "installed"):
            return HTMLResponse(
                f"<p style='color:#f44336;padding:20px;'>App '{app_id}' introuvable.</p>",
                status_code=404
            )

        app_type    = cfg.get("type", "local")
        app_url     = cfg.get("url", "")
        icon        = ICON_MAP.get(cfg.get("icon", "package"), "📦")
        name        = cfg.get("name", app_id.title())
        version     = aion_app.VERSION
        ai_ok       = aion_app.brain.is_available()

        type_color = {"fastapi":"#4caf50","api_external":"#9c27b0",
                      "local":"#1e90ff","docker":"#ff9800"}.get(app_type,"#888")

        ai_badge = (
            '<span style="background:rgba(76,175,80,.2);color:#4caf50;padding:2px 8px;'
            'border-radius:10px;font-size:.75rem;font-weight:600;">● Groq</span>'
            if ai_ok else
            '<span style="background:rgba(244,67,54,.2);color:#f44336;padding:2px 8px;'
            'border-radius:10px;font-size:.75rem;font-weight:600;">● Groq offline</span>'
        )

        # Contenu de la zone principale
        if app_url and app_type in ("fastapi", "api_external"):
            # ── Iframe vers l'app ──────────────────────────────────────────
            content_html = f'<iframe src="{app_url}" class="app-iframe" title="{name}" loading="lazy"></iframe>'
        else:
            # ── App locale : affichage avec commande IA ────────────────────
            connector = aion_app.app_router._apps.get(app_id)
            raw = ""
            if connector:
                try:
                    raw = connector.execute("status", {})
                except Exception as e:
                    raw = f"Erreur : {e}"
            content_html = f'''
            <div style="padding:24px;overflow-y:auto;height:100%;">
              <div style="background:var(--card);border:1px solid var(--border);
                   border-radius:10px;padding:20px;max-width:700px;margin-bottom:16px;">
                <pre style="color:#4caf50;font-family:Cascadia Code,Consolas,monospace;
                     font-size:.85rem;white-space:pre-wrap;line-height:1.6;">{raw}</pre>
              </div>
              <div style="background:var(--card);border:1px solid var(--border);
                   border-radius:10px;padding:16px;max-width:700px;">
                <p style="color:var(--dim);font-size:.82rem;margin-bottom:10px;">Commande via AION IA :</p>
                <div style="display:flex;gap:8px;">
                  <input id="app-cmd" type="text"
                    placeholder="Ex: status system, timer 10 minutes..."
                    style="flex:1;background:#12141f;border:1px solid var(--border);
                      color:var(--text);padding:9px 14px;border-radius:6px;font-size:.88rem;"
                    onkeydown="if(event.key==='Enter') sendCmd()">
                  <button onclick="sendCmd()"
                    style="background:var(--accent);color:#fff;border:none;
                      padding:9px 18px;border-radius:6px;cursor:pointer;font-size:.85rem;">Envoyer</button>
                </div>
                <div id="cmd-result" style="margin-top:12px;font-size:.85rem;color:#4caf50;white-space:pre-wrap;"></div>
              </div>
            </div>
            <script>
            function sendCmd() {{
              var i=document.getElementById("app-cmd"),r=document.getElementById("cmd-result"),t=i.value.trim();
              if(!t) return; r.textContent="⏳ AION reflechit..."; i.value="";
              fetch("/api/route",{{method:"POST",headers:{{"Content-Type":"application/json"}},
                body:JSON.stringify({{text:t}})}})
              .then(x=>x.json()).then(d=>{{r.textContent=d.response||d.result||"OK";}})
              .catch(e=>{{r.textContent="Erreur: "+e;}});
            }}
            </script>
            '''

        page = f'''<!DOCTYPE html>
<html lang="fr" data-theme="dark">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{name} — AION-Core</title>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
:root[data-theme="dark"]{{--bg:#0f1117;--sb:#13161f;--card:#1a1d27;--border:#2a2d3e;
  --text:#e0e0e0;--dim:#888;--accent:#1e90ff;--green:#4caf50;--hdr:#151821;}}
:root[data-theme="light"]{{--bg:#f0f2f5;--sb:#fff;--card:#fff;--border:#dde1f0;
  --text:#1a1a2e;--dim:#666;--accent:#1e90ff;--hdr:#fff;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:"Segoe UI",sans-serif;background:var(--bg);color:var(--text);
  display:flex;flex-direction:column;height:100vh;overflow:hidden;}}
header{{background:var(--hdr);border-bottom:2px solid var(--accent);
  padding:0 20px;height:52px;display:flex;align-items:center;gap:12px;flex-shrink:0;}}
header h1{{color:var(--accent);font-size:1.2rem;font-weight:700;}}
.spacer{{flex:1;}} .ver{{color:var(--dim);font-size:.78rem;}}
.hbtn{{background:var(--card);border:1px solid var(--border);color:var(--text);
  padding:5px 12px;border-radius:6px;cursor:pointer;font-size:.82rem;text-decoration:none;}}
.hbtn:hover{{background:var(--accent);color:#fff;}}
.layout{{display:flex;flex:1;overflow:hidden;}}
.sidebar{{width:220px;background:var(--sb);border-right:1px solid var(--border);
  display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;padding:10px 0;}}
.sb-sec{{padding:4px 12px;font-size:.68rem;text-transform:uppercase;letter-spacing:1px;
  color:var(--dim);margin-top:8px;}}
.nav-item{{display:flex;align-items:center;gap:10px;padding:9px 14px;
  border-left:3px solid transparent;font-size:.88rem;text-decoration:none;color:var(--text);}}
.nav-item:hover{{background:rgba(30,144,255,.08);}}
.nav-item.active{{background:rgba(30,144,255,.12);border-left-color:var(--accent);
  color:var(--accent);font-weight:600;}}
.nav-icon{{width:20px;text-align:center;}} .nav-label{{flex:1;}}
.nav-dot{{width:6px;height:6px;border-radius:50%;background:var(--dim);
  margin-left:auto;flex-shrink:0;}}
.main{{flex:1;overflow:hidden;display:flex;flex-direction:column;}}
.app-bar{{background:var(--card);border-bottom:1px solid var(--border);
  padding:10px 20px;display:flex;align-items:center;gap:12px;flex-shrink:0;}}
.app-content{{flex:1;overflow:hidden;}}
.app-iframe{{width:100%;height:100%;border:none;}}
::-webkit-scrollbar{{width:5px;}}
::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px;}}
</style>
</head>
<body>
<header>
  <span style="font-size:1.3rem;">🤖</span>
  <h1>AION-Core</h1><span class="ver">v{version}</span>
  <div class="spacer"></div>
  {ai_badge}
  <button class="hbtn" onclick="toggleTheme()">🌓</button>
  <a href="/docs" target="_blank" class="hbtn">📖 API</a>
</header>
<div class="layout">
  <nav class="sidebar">
    <div class="sb-sec">Navigation</div>
    <a href="/" class="nav-item"><span class="nav-icon">📊</span><span class="nav-label">Dashboard</span></a>
    <a href="/chat" class="nav-item"><span class="nav-icon">🤖</span><span class="nav-label">IA Chat</span></a>
    <div class="sb-sec">Apps</div>
    <div id="sidebar-apps" hx-get="/api/nav/apps/sidebar" hx-trigger="load" hx-swap="innerHTML">
      <div style="padding:8px 14px;color:var(--dim);font-size:.8rem;">…</div>
    </div>
    <div class="sb-sec">AION</div>
    <a href="/store" class="nav-item"><span class="nav-icon">🏪</span><span class="nav-label">App Store</span></a>
    <a href="/memory" class="nav-item"><span class="nav-icon">🧠</span><span class="nav-label">Memory</span></a>
    <a href="/settings" class="nav-item"><span class="nav-icon">⚙️</span><span class="nav-label">Settings</span></a>
  </nav>
  <main class="main">
    <div class="app-bar">
      <span style="font-size:1.2rem;">{icon}</span>
      <span style="font-weight:600;">{name}</span>
      <span style="font-size:.7rem;padding:2px 8px;border-radius:10px;font-weight:600;
        background:color-mix(in srgb,{type_color} 20%,transparent);
        color:{type_color};">{app_type}</span>
      {f'<a href="{app_url}" target="_blank" style="color:var(--dim);font-size:.78rem;margin-left:auto;">↗️ {app_url}</a>' if app_url else ""}
    </div>
    <div class="app-content">{content_html}</div>
  </main>
</div>
<script>
document.addEventListener("htmx:afterSwap", function(e) {{
  if (e.target.id === "sidebar-apps") {{
    document.querySelectorAll("#sidebar-apps .nav-item").forEach(function(i) {{
      if (i.getAttribute("href") === window.location.pathname) i.classList.add("active");
    }});
  }}
}});
function toggleTheme() {{
  var h=document.documentElement;
  h.setAttribute("data-theme",h.getAttribute("data-theme")==="dark"?"light":"dark");
  localStorage.setItem("theme",h.getAttribute("data-theme"));
}}
var t=localStorage.getItem("theme"); if(t) document.documentElement.setAttribute("data-theme",t);
</script>
</body></html>'''
        return HTMLResponse(page)