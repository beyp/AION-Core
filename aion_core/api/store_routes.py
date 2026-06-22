"""
store_routes.py -- Routes FastAPI pour l'AppStore AION.

GET  /store                      -> page web App Store
GET  /api/store/status           -> statut de toutes les apps gerees
POST /api/store/install          -> git clone une app depuis GitHub
POST /api/store/update/{app_id}  -> git pull + backup appdata auto
POST /api/store/restore/{app_id} -> restaure appdata -> repo
POST /api/store/register-file    -> declare un fichier persistant
DELETE /api/store/{app_id}       -> desinstalle une app (garde appdata)
"""
import logging
from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

ICON_MAP = {
    "check":"✅","circle":"🔵","clipboard":"📋",
    "monitor":"🖥️","clock":"⏰","brain":"🧠",
    "mail":"✉️","package":"📦",
}


def register_store_routes(app, aion_app):
    """Enregistre les routes App Store dans FastAPI."""

    from aion_core.store.app_store import AppStore
    store = AppStore()

    # ── API REST ──────────────────────────────────────────────────

    @app.get("/api/store/status")
    async def store_status():
        return {"apps": store.status()}

    @app.post("/api/store/install")
    async def store_install(request: Request):
        """Installe une app depuis GitHub (git clone).
        Body: {"github":"owner/repo","app_id":"...","appdata_files":[...]}
        """
        body          = await request.json()
        github_repo   = body.get("github", "")
        app_id        = body.get("app_id", None)
        appdata_files = body.get("appdata_files", [])
        if not github_repo:
            return JSONResponse({"success": False,
                "message": "github requis (ex: beyp/QuickMind)"}, status_code=400)
        result = store.install(github_repo, app_id=app_id, appdata_files=appdata_files)
        if result.get("success"):
            try:
                aion_app.app_router.reload_apps()
            except Exception as e:
                logger.warning("Reload apps post-install: %s", e)
        return result

    @app.post("/api/store/update/{app_id}")
    async def store_update(app_id: str):
        """Met a jour via git pull (backup appdata automatique)."""
        return store.update(app_id)

    @app.post("/api/store/restore/{app_id}")
    async def store_restore(app_id: str):
        """Restaure les fichiers persistants depuis appdata/ vers le repo."""
        return store.restore_appdata(app_id)

    @app.post("/api/store/register-file")
    async def store_register_file(request: Request):
        """Declare un fichier persistant. Body: {"app_id":"...","filename":"..."}"""
        body     = await request.json()
        app_id   = body.get("app_id", "")
        filename = body.get("filename", "")
        if not app_id or not filename:
            return JSONResponse({"success": False,
                "message": "app_id et filename requis"}, status_code=400)
        return store.register_appdata_file(app_id, filename)

    @app.delete("/api/store/{app_id}")
    async def store_uninstall(app_id: str, keep_appdata: bool = True):
        """Desinstalle (supprime repo, garde appdata par defaut)."""
        result = store.uninstall(app_id, keep_appdata=keep_appdata)
        if result.get("success"):
            try:
                aion_app.app_router.reload_apps()
            except Exception:
                pass
        return result

    @app.get("/api/store/{app_id}/appdata")
    async def store_list_appdata(app_id: str):
        return {"app_id": app_id, "files": store.list_appdata(app_id)}

    # ── Page Web App Store ────────────────────────────────────────

    @app.get("/store", response_class=HTMLResponse)
    async def store_page(request: Request):
        apps_status = store.status()
        rows_html   = ""

        for info in apps_status:
            app_id    = info["app_id"]
            name      = info["name"]
            github    = info.get("github", "")
            is_cloned = info["is_cloned"]
            last_upd  = info.get("last_update", "—")
            nb_back   = len(info.get("backups", []))
            appfiles  = info.get("appdata_files", [])

            status_html = (
                '<span style="color:#4caf50;font-weight:600;">✅ Installe</span>'
                if is_cloned else
                '<span style="color:#f44336;font-weight:600;">❌ Non clone</span>'
            )
            gh_link = (
                f'<a href="https://github.com/{github}" target="_blank" '
                f'style="color:#1e90ff;font-size:.8rem;">{github}</a>'
                if github else "—"
            )
            files_str = (", ".join(appfiles)
                         if appfiles else '<span style="color:#888;">(aucun)</span>')

            rows_html += f'''
            <div style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:10px;
                 padding:16px;margin-bottom:12px;">
              <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
                <div style="flex:1;">
                  <div style="font-weight:600;font-size:.95rem;">{name}</div>
                  <div style="margin-top:2px;">{gh_link}</div>
                </div>
                {status_html}
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;
                   font-size:.8rem;color:#888;margin-bottom:12px;">
                <div>Mis a jour : <span style="color:#e0e0e0;">{last_upd}</span></div>
                <div>Backups : <span style="color:#e0e0e0;">{nb_back}</span></div>
                <div style="grid-column:1/-1;">
                  Appdata : <span style="color:#4caf50;">{files_str}</span></div>
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <button onclick="storeAction('update','{app_id}')"
                  style="background:#1e90ff22;border:1px solid #1e90ff55;color:#1e90ff;
                  padding:6px 14px;border-radius:6px;cursor:pointer;font-size:.8rem;">
                  🔄 Mettre a jour</button>
                <button onclick="storeAction('restore','{app_id}')"
                  style="background:#4caf5022;border:1px solid #4caf5055;color:#4caf50;
                  padding:6px 14px;border-radius:6px;cursor:pointer;font-size:.8rem;">
                  💾 Restaurer AppData</button>
                <button onclick="storeUninstall('{app_id}')"
                  style="background:#f4433622;border:1px solid #f4433655;color:#f44336;
                  padding:6px 14px;border-radius:6px;cursor:pointer;font-size:.8rem;">
                  🗑️ Desinstaller</button>
              </div>
              <div id="sr-{app_id}" style="margin-top:8px;font-size:.82rem;color:#4caf50;display:none;"></div>
            </div>'''

        page = f'''<!DOCTYPE html>
<html lang="fr" data-theme="dark"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>App Store — AION-Core</title>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<style>
:root[data-theme="dark"]{{--bg:#0f1117;--sb:#13161f;--card:#1a1d27;--border:#2a2d3e;
  --text:#e0e0e0;--dim:#888;--accent:#1e90ff;--hdr:#151821;}}
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:"Segoe UI",sans-serif;background:var(--bg);color:var(--text);
  display:flex;flex-direction:column;height:100vh;overflow:hidden;}}
header{{background:var(--hdr);border-bottom:2px solid var(--accent);padding:0 20px;
  height:52px;display:flex;align-items:center;gap:12px;flex-shrink:0;}}
header h1{{color:var(--accent);font-size:1.2rem;font-weight:700;}}
.spacer{{flex:1;}}
.hbtn{{background:var(--card);border:1px solid var(--border);color:var(--text);
  padding:5px 12px;border-radius:6px;cursor:pointer;font-size:.82rem;text-decoration:none;}}
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
.main{{flex:1;overflow-y:auto;padding:20px;}}
input{{background:#12141f;border:1px solid #2a2d3e;color:#e0e0e0;
  padding:9px 14px;border-radius:6px;font-size:.88rem;}}
::-webkit-scrollbar{{width:5px;}} ::-webkit-scrollbar-thumb{{background:#2a2d3e;border-radius:3px;}}
</style></head>
<body>
<header>
  <span style="font-size:1.3rem;">🤖</span>
  <h1>AION-Core</h1><div class="spacer"></div>
  <a href="/" class="hbtn">← Dashboard</a>
</header>
<div class="layout">
  <nav class="sidebar">
    <div class="sb-sec">Navigation</div>
    <a href="/" class="nav-item"><span class="nav-icon">📊</span><span class="nav-label">Dashboard</span></a>
    <a href="/chat" class="nav-item"><span class="nav-icon">🤖</span><span class="nav-label">IA Chat</span></a>
    <div class="sb-sec">Apps</div>
    <div id="sidebar-apps" hx-get="/api/nav/apps/sidebar" hx-trigger="load" hx-swap="innerHTML">
      <div style="padding:8px 14px;color:#888;font-size:.8rem;">…</div>
    </div>
    <div class="sb-sec">AION</div>
    <a href="/store" class="nav-item active"><span class="nav-icon">🏪</span><span class="nav-label">App Store</span></a>
    <a href="/memory" class="nav-item"><span class="nav-icon">🧠</span><span class="nav-label">Memory</span></a>
    <a href="/apps" class="nav-item"><span class="nav-icon">📦</span><span class="nav-label">Registry</span></a>
    <a href="/settings" class="nav-item"><span class="nav-icon">⚙️</span><span class="nav-label">Settings</span></a>
  </nav>
  <main class="main">
    <h2 style="color:#1e90ff;margin-bottom:6px;">🏪 App Store</h2>
    <p style="color:#888;font-size:.85rem;margin-bottom:20px;">
      Installe et gere tes apps AION depuis GitHub. AppData sauvegarde automatiquement avant chaque update.</p>
    <div style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:10px;padding:16px;margin-bottom:20px;">
      <div style="font-weight:600;margin-bottom:12px;color:#1e90ff;">➕ Installer une nouvelle app</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        <input id="inst-repo" type="text" placeholder="owner/repo (ex: beyp/QuickMind)"
          style="flex:1;min-width:200px;">
        <input id="inst-files" type="text" placeholder="Fichiers persistants (ex: memory.json,app.db)"
          style="flex:1;min-width:200px;">
        <button onclick="doInstall()"
          style="background:#1e90ff;color:#fff;border:none;padding:9px 20px;
          border-radius:6px;cursor:pointer;font-size:.88rem;font-weight:600;">
          📥 Installer</button>
      </div>
      <div id="inst-result" style="margin-top:10px;font-size:.82rem;display:none;"></div>
    </div>
    <div style="font-weight:600;margin-bottom:12px;color:#888;font-size:.85rem;
         text-transform:uppercase;letter-spacing:1px;">Apps gerees ({len(apps_status)})</div>
    {rows_html if rows_html else '<p style="color:#888;font-size:.85rem;">Aucune app installee via AppStore.</p>'}
  </main>
</div>
<script>
document.addEventListener("htmx:afterSwap",function(e){{
  if(e.target.id==="sidebar-apps"){{
    document.querySelectorAll("#sidebar-apps .nav-item").forEach(function(i){{
      if(i.getAttribute("href")===window.location.pathname) i.classList.add("active");
    }});
  }}
}});
function doInstall(){{
  var repo=document.getElementById("inst-repo").value.trim();
  var files=document.getElementById("inst-files").value.trim();
  var res=document.getElementById("inst-result");
  if(!repo) return;
  var af=files?files.split(",").map(f=>f.trim()).filter(f=>f):[];
  res.style.display="block"; res.style.color="#ff9800";
  res.textContent="⏳ Installation en cours (git clone)...";
  fetch("/api/store/install",{{method:"POST",headers:{{"Content-Type":"application/json"}},
    body:JSON.stringify({{github:repo,appdata_files:af}})}})
  .then(r=>r.json()).then(d=>{{
    res.style.color=d.success?"#4caf50":"#f44336";
    res.textContent=d.message;
    if(d.success) setTimeout(()=>location.reload(),1500);
  }}).catch(e=>{{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
}}
function storeAction(action,id){{
  var res=document.getElementById("sr-"+id);
  res.style.display="block"; res.style.color="#ff9800"; res.textContent="⏳ En cours...";
  var url=action==="update"?"/api/store/update/"+id:"/api/store/restore/"+id;
  fetch(url,{{method:"POST"}}).then(r=>r.json()).then(d=>{{
    res.style.color=d.success?"#4caf50":"#f44336"; res.textContent=d.message;
  }}).catch(e=>{{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
}}
function storeUninstall(id){{
  if(!confirm("Desinstaller "+id+" ? (appdata conserve)")) return;
  var res=document.getElementById("sr-"+id);
  res.style.display="block"; res.style.color="#ff9800"; res.textContent="Desinstallation...";
  fetch("/api/store/"+id,{{method:"DELETE"}}).then(r=>r.json()).then(d=>{{
    res.style.color=d.success?"#4caf50":"#f44336"; res.textContent=d.message;
    if(d.success) setTimeout(()=>location.reload(),1500);
  }}).catch(e=>{{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
}}
</script>
</body></html>'''
        return HTMLResponse(page)
