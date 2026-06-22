"""
store_routes.py -- Routes FastAPI pour l'AppStore AION.

GET  /store                        -> page web App Store
GET  /api/store/status             -> statut de toutes les apps gerees
GET  /api/store/scan/{app_id}      -> scan auto des fichiers persistants
POST /api/store/install            -> git clone + scan auto appdata
POST /api/store/update/{app_id}    -> git pull + backup appdata auto
POST /api/store/restore/{app_id}   -> restaure appdata -> repo
POST /api/store/register-file      -> ajoute manuellement un fichier persistant
DELETE /api/store/{app_id}         -> desinstalle (garde appdata)
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

    @app.get("/api/store/scan/{app_id}")
    async def store_scan(app_id: str):
        """
        Scanne les fichiers persistants d'un repo installe et les sauvegarde.
        Utile apres un premier lancement (data/ cree par l'app au runtime).
        """
        result = store.scan_appdata(app_id)
        # Si de nouveaux fichiers sont detectes, les sauvegarder immediatement
        if result.get("success") and result.get("appdata_files"):
            store_cfg = store._get_store_cfg(app_id)
            if store_cfg and store_cfg.get("install_path"):
                save_result = store.appdata_mgr.save(
                    app_id,
                    store_cfg["install_path"],
                    result["appdata_files"]
                )
                result["saved"] = save_result.get("saved", [])
                result["missing"] = save_result.get("missing", [])
        return result

    @app.post("/api/store/scan-and-save/{app_id}")
    async def store_scan_and_save(app_id: str):
        """
        Re-scanne ET sauvegarde immediatement dans appdata/.
        A appeler apres le premier lancement d'une app nouvellement installee.
        """
        result = store.scan_appdata(app_id)
        if result.get("success") and result.get("appdata_files"):
            store_cfg = store._get_store_cfg(app_id)
            if store_cfg and store_cfg.get("install_path"):
                save_result = store.appdata_mgr.save(
                    app_id,
                    store_cfg["install_path"],
                    result["appdata_files"]
                )
                result["saved"]   = save_result.get("saved", [])
                result["missing"] = save_result.get("missing", [])
                result["message"] += f" | Sauvegarde: {save_result.get('saved', [])}"
        return result

    @app.post("/api/store/install")
    async def store_install(request: Request):
        """
        Installe une app depuis GitHub.
        Body: {"github":"owner/repo", "app_id":"...", "appdata_files":[...]}
        Si appdata_files est absent ou vide -> scan automatique apres clone.
        """
        body          = await request.json()
        github_repo   = body.get("github", "")
        app_id        = body.get("app_id") or None
        appdata_files = body.get("appdata_files") or None  # None = scan auto

        if not github_repo:
            return JSONResponse({"success": False,
                "message": "github requis (ex: beyp/QuickMind)"}, status_code=400)

        result = store.install(github_repo, app_id=app_id, appdata_files=appdata_files)

        if result.get("success"):
            installed_id = result.get("app_id", (app_id or github_repo.split("/")[-1].lower()))

            # 1. Recharger les apps dans le router
            try:
                aion_app.app_router.reload_apps()
                logger.info("Apps rechargees apres installation de %s", github_repo)
            except Exception as e:
                logger.warning("Reload apps post-install: %s", e)

            # 2. Lancer l'app si autostart est configure (enabled=True)
            try:
                from aion_core.discovery.launcher import AppLauncher
                launcher = AppLauncher()
                launch_result = launcher.start_app(installed_id)
                result["launch"] = launch_result
                logger.info("Lancement post-install %s: %s", installed_id, launch_result)
            except Exception as e:
                logger.warning("Lancement post-install %s: %s", installed_id, e)
                result["launch"] = {"success": False, "message": str(e)}

        return result

    @app.post("/api/store/update/{app_id}")
    async def store_update(app_id: str):
        """Git pull + backup appdata automatique."""
        return store.update(app_id)

    @app.post("/api/store/restore/{app_id}")
    async def store_restore(app_id: str):
        """Restaure les fichiers depuis appdata/ vers le repo."""
        return store.restore_appdata(app_id)

    @app.post("/api/store/register-file")
    async def store_register_file(request: Request):
        """Ajoute manuellement un fichier persistant.
        Body: {"app_id":"quickmind","filename":"data/myfile.db"}
        """
        body     = await request.json()
        app_id   = body.get("app_id", "")
        filename = body.get("filename", "")
        if not app_id or not filename:
            return JSONResponse({"success": False,
                "message": "app_id et filename requis"}, status_code=400)
        return store.register_appdata_file(app_id, filename)

    @app.delete("/api/store/{app_id}")
    async def store_uninstall(app_id: str, keep_appdata: bool = True):
        """Desinstalle une app (garde appdata par defaut)."""
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

    @app.post("/api/store/start/{app_id}")
    async def store_start(app_id: str):
        """Lance une app installee."""
        try:
            import json
            from pathlib import Path
            from aion_core.discovery.launcher import AppLauncher
            from aion_core.store.app_setup import AppSetup

            reg_file = Path("apps.json")
            registry = json.loads(reg_file.read_text(encoding="utf-8")) if reg_file.exists() else {}
            app_cfg  = registry.get("apps", {}).get(app_id, {})
            if not app_cfg:
                return {"success": False, "message": f"App '{app_id}' introuvable"}

            autostart = app_cfg.get("autostart", {})
            store_cfg = app_cfg.get("store", {})
            install_path = store_cfg.get("install_path", autostart.get("path", ""))

            # Garantir le path
            if install_path and not autostart.get("path"):
                autostart["path"] = install_path

            # Detecter la commande via AppSetup si manquante
            if install_path and not autostart.get("command"):
                setup = AppSetup(app_id, install_path)
                cmd   = setup.get_launch_command()
                autostart["command"] = [str(c) for c in cmd]
                autostart["mode"]    = autostart.get("mode", "fastapi")
                autostart["enabled"] = True
                app_cfg["autostart"] = autostart

            launcher = AppLauncher()
            launcher._registry = registry
            result = launcher.start_app(app_id)
            return result
        except Exception as e:
            logger.error("Store start %s: %s", app_id, e)
            return {"success": False, "message": str(e)}

    @app.post("/api/store/stop/{app_id}")
    async def store_stop(app_id: str):
        """Arrete une app via son port."""
        try:
            import json, subprocess
            from pathlib import Path
            reg_file = Path("apps.json")
            registry = json.loads(reg_file.read_text(encoding="utf-8")) if reg_file.exists() else {}
            app_cfg  = registry.get("apps", {}).get(app_id, {})
            port     = app_cfg.get("autostart", {}).get("port", 0)
            if not port:
                return {"success": False, "message": "Port non configure"}
            proc = subprocess.run(["netstat", "-ano"], capture_output=True, text=True,
                                     encoding="utf-8", errors="replace")
            pid = None
            stdout = proc.stdout or ""
            for line in stdout.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.split()
                    if parts: pid = parts[-1]
                    break
            if pid:
                subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
                return {"success": True, "message": f"'{app_id}' arrete (PID {pid})"}
            return {"success": False, "message": f"Aucun process sur port {port}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @app.get("/api/store/running/{app_id}")
    async def store_is_running(app_id: str):
        """Verifie si une app repond sur son URL."""
        try:
            import json, requests as _req
            from pathlib import Path
            reg_file = Path("apps.json")
            registry = json.loads(reg_file.read_text(encoding="utf-8")) if reg_file.exists() else {}
            app_cfg  = registry.get("apps", {}).get(app_id, {})
            url      = app_cfg.get("url", "")
            health   = app_cfg.get("health_endpoint", "/health")
            running  = False
            if url:
                try:
                    r = _req.get(url.rstrip("/") + health, timeout=2)
                    running = r.status_code < 400
                except Exception:
                    pass
            return {"app_id": app_id, "running": running, "url": url}
        except Exception as e:
            return {"app_id": app_id, "running": False, "error": str(e)}

    # ── Page Web App Store ────────────────────────────────────────

    @app.get("/store", response_class=HTMLResponse)
    async def store_page(request: Request):
        apps_status = store.status()
        rows_html   = ""

        for info in apps_status:
            app_id      = info["app_id"]
            name        = info["name"]
            github      = info.get("github", "")
            is_cloned   = info["is_cloned"]
            last_upd    = info.get("last_update", "—")
            nb_back     = len(info.get("backups", []))
            appfiles    = info.get("appdata_files", [])
            auto_det    = info.get("auto_detected", False)

            status_html = (
                '<span style="color:#4caf50;font-weight:600;">✅ Installe</span>'
                if is_cloned else
                '<span style="color:#f44336;font-weight:600;">❌ Non clone</span>'
            )
            gh_link = (
                f'<a href="https://github.com/{github}" target="_blank" '
                f'style="color:#1e90ff;font-size:.8rem;">{github} ↗️</a>'
                if github else "—"
            )

            # Fichiers appdata avec badge auto/manuel
            if appfiles:
                mode_badge = (
                    '<span style="font-size:.68rem;background:rgba(30,144,255,.2);'
                    'color:#1e90ff;padding:1px 6px;border-radius:8px;margin-left:4px;">auto</span>'
                    if auto_det else
                    '<span style="font-size:.68rem;background:rgba(255,152,0,.2);'
                    'color:#ff9800;padding:1px 6px;border-radius:8px;margin-left:4px;">manuel</span>'
                )
                files_items = "".join(
                    f'<div style="display:flex;align-items:center;gap:6px;padding:3px 0;">'
                    f'<span style="color:#4caf50;font-size:.85rem;">📄</span>'
                    f'<code style="font-size:.8rem;color:#e0e0e0;">{f}</code>'
                    f'</div>' for f in appfiles
                )
                appdata_html = f'''
                <div style="margin-top:8px;">
                  <div style="font-size:.78rem;color:#888;margin-bottom:4px;">
                    Fichiers persistants{mode_badge}
                    <button onclick="scanAppdata('{app_id}')"
                      style="margin-left:8px;background:transparent;border:1px solid #2a2d3e;
                      color:#888;padding:1px 8px;border-radius:4px;cursor:pointer;font-size:.72rem;">
                      🔍 Re-scanner</button>
                    <button onclick="showAddFile('{app_id}')"
                      style="margin-left:4px;background:transparent;border:1px solid #2a2d3e;
                      color:#888;padding:1px 8px;border-radius:4px;cursor:pointer;font-size:.72rem;">
                      ➕ Ajouter</button>
                  </div>
                  <div style="background:#0f1117;border-radius:6px;padding:8px 10px;">{files_items}</div>
                  <div id="add-file-{app_id}" style="display:none;margin-top:8px;display:none;">
                    <div style="display:flex;gap:6px;">
                      <input id="af-input-{app_id}" type="text"
                        placeholder="Chemin relatif (ex: data/myfile.db)"
                        style="flex:1;background:#12141f;border:1px solid #2a2d3e;color:#e0e0e0;
                        padding:6px 10px;border-radius:5px;font-size:.82rem;">
                      <button onclick="addAppFile('{app_id}')"
                        style="background:#ff9800;color:#fff;border:none;padding:6px 12px;
                        border-radius:5px;cursor:pointer;font-size:.8rem;">➕</button>
                    </div>
                  </div>
                </div>
                '''
            else:
                appdata_html = '''
                <div style="margin-top:8px;font-size:.8rem;color:#888;">
                  <span style="color:#f44336;">⚠️</span>
                  Aucun fichier persistant detecte.
                  <button onclick="scanAppdata(\'{app_id}\')"
                    style="margin-left:6px;background:transparent;border:1px solid #2a2d3e;
                    color:#1e90ff;padding:1px 8px;border-radius:4px;cursor:pointer;font-size:.78rem;">
                    🔍 Scanner maintenant</button>
                </div>
                '''
                appdata_html = appdata_html.replace("{app_id}", app_id)

            rows_html += f'''
            <div style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:10px;
                 padding:16px;margin-bottom:12px;">
              <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px;">
                <div style="flex:1;">
                  <div style="font-weight:600;font-size:.95rem;">{name}</div>
                  <div style="margin-top:2px;">{gh_link}</div>
                </div>
                {status_html}
              </div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;
                   font-size:.8rem;color:#888;margin-bottom:4px;">
                <div>Mis a jour : <span style="color:#ccc;">{last_upd}</span></div>
                <div>Backups disponibles : <span style="color:#ccc;">{nb_back}</span></div>
              </div>
              {appdata_html}
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;align-items:center;">
                <button id="btn-start-{app_id}" onclick="appStart('{app_id}')"
                  style="background:#4caf5022;border:1px solid #4caf5055;color:#4caf50;
                  padding:6px 16px;border-radius:6px;cursor:pointer;font-size:.82rem;font-weight:600;">
                  &#x25B6; Start</button>
                <button id="btn-stop-{app_id}" onclick="appStop('{app_id}')"
                  style="background:#f4433622;border:1px solid #f4433655;color:#f44336;
                  padding:6px 16px;border-radius:6px;cursor:pointer;font-size:.82rem;font-weight:600;">
                  &#x25A0; Stop</button>
                <button onclick="scanAfterStart('{app_id}')"
                  title="Scanner et sauvegarder les fichiers appdata apres un premier lancement"
                  style="background:#9c27b022;border:1px solid #9c27b055;color:#9c27b0;
                  padding:6px 12px;border-radius:6px;cursor:pointer;font-size:.78rem;">
                  &#x1F50D; Scan AppData</button>
                <div style="width:1px;height:20px;background:#2a2d3e;margin:0 4px;"></div>
                <button onclick="storeAction('update','{app_id}')"
                  style="background:#1e90ff22;border:1px solid #1e90ff55;color:#1e90ff;
                  padding:6px 12px;border-radius:6px;cursor:pointer;font-size:.78rem;">
                  &#x1F504; Update</button>
                <button onclick="storeAction('restore','{app_id}')"
                  style="background:#ff980022;border:1px solid #ff980055;color:#ff9800;
                  padding:6px 12px;border-radius:6px;cursor:pointer;font-size:.78rem;">
                  &#x1F4BE; Restaurer</button>
                <button onclick="storeUninstall('{app_id}')"
                  style="background:#f4433611;border:1px solid #f4433633;color:#f44336;
                  padding:6px 12px;border-radius:6px;cursor:pointer;font-size:.78rem;">
                  &#x1F5D1;&#xFE0F; Supprimer</button>
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
.sidebar{{width:220px;background:var(--sb,#13161f);border-right:1px solid var(--border);
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
input,code{{font-family:"Cascadia Code",Consolas,monospace;}}
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
    <h2 style="color:#1e90ff;margin-bottom:4px;">🏪 App Store</h2>
    <p style="color:#888;font-size:.82rem;margin-bottom:20px;">
      Les fichiers persistants (DB, JSON...) sont <strong style="color:#e0e0e0;">detectes automatiquement</strong>
      apres le git clone et sauvegardes dans
      <code style="color:#4caf50;font-size:.8rem;">C:/AION_APPS/appdata/</code>
      avant chaque mise a jour.</p>

    <!-- Installer -->
    <div style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:10px;padding:16px;margin-bottom:20px;">
      <div style="font-weight:600;margin-bottom:12px;color:#1e90ff;">➕ Installer une nouvelle app</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;">
        <div style="flex:1;min-width:200px;">
          <label style="font-size:.75rem;color:#888;display:block;margin-bottom:4px;">Repo GitHub</label>
          <input id="inst-repo" type="text" placeholder="owner/repo  (ex: beyp/QuickMind)"
            style="width:100%;background:#12141f;border:1px solid #2a2d3e;color:#e0e0e0;
            padding:9px 14px;border-radius:6px;font-size:.88rem;">
        </div>
        <div style="flex-shrink:0;">
          <label style="font-size:.75rem;color:#888;display:block;margin-bottom:4px;">&nbsp;</label>
          <button onclick="doInstall()"
            style="background:#1e90ff;color:#fff;border:none;padding:9px 20px;
            border-radius:6px;cursor:pointer;font-size:.88rem;font-weight:600;white-space:nowrap;">
            📥 Installer (scan auto)
          </button>
        </div>
      </div>
      <p style="font-size:.75rem;color:#555;margin-top:8px;">
        💡 Les fichiers <code style="color:#888;">.db .sqlite .env memory.json config.json</code>
        et les dossiers <code style="color:#888;">data/ db/ storage/</code>
        seront detectes automatiquement.</p>
      <div id="inst-result" style="margin-top:10px;font-size:.82rem;display:none;padding:8px 12px;border-radius:6px;"></div>
    </div>

    <!-- Apps gerees -->
    <div style="font-weight:600;margin-bottom:12px;color:#888;font-size:.8rem;
         text-transform:uppercase;letter-spacing:1px;">Apps gerees via AppStore ({len(apps_status)})</div>
    {rows_html if rows_html else '<div style="color:#888;font-size:.85rem;padding:16px;background:#1a1d27;border-radius:8px;">Aucune app installee via AppStore pour l\'instant.</div>'}
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
  var res=document.getElementById("inst-result");
  if(!repo) return;
  res.style.display="block"; res.style.background="rgba(255,152,0,.1)";
  res.style.color="#ff9800"; res.innerHTML="⏳ git clone en cours... (peut prendre 10-30 sec)";
  fetch("/api/store/install",{{method:"POST",headers:{{"Content-Type":"application/json"}},
    body:JSON.stringify({{github:repo}})}})
  .then(r=>r.json()).then(d=>{{
    res.style.background=d.success?"rgba(76,175,80,.1)":"rgba(244,67,54,.1)";
    res.style.color=d.success?"#4caf50":"#f44336";
    var files = d.appdata_files && d.appdata_files.length
      ? "<br>📄 Fichiers detectes : <code style='color:#ccc;'>" + d.appdata_files.join(", ") + "</code>"
      : "<br><span style='color:#888;'>Aucun fichier persistant detecte</span>";
    var launch = d.launch ? (d.launch.success
      ? "<br>\u25cf App lanc\u00e9e : " + (d.launch.message || "OK")
      : "<br>\u26a0\ufe0f Lancement auto : " + (d.launch.message || "non configure")) : "";
    res.innerHTML = d.message + files + launch;
    if(d.success) setTimeout(()=>location.reload(),2500);
  }}).catch(e=>{{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
}}
function storeAction(action,id){{
  var res=document.getElementById("sr-"+id);
  res.style.display="block"; res.style.color="#ff9800"; res.textContent="⏳ En cours...";
  var url=action==="update"?"/api/store/update/"+id:"/api/store/restore/"+id;
  fetch(url,{{method:"POST"}}).then(r=>r.json()).then(d=>{{
    res.style.color=d.success?"#4caf50":"#f44336"; res.textContent=d.message;
    if(d.success && action==="update") setTimeout(()=>location.reload(),1500);
  }}).catch(e=>{{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
}}
function scanAppdata(id){{
  var res=document.getElementById("sr-"+id);
  res.style.display="block"; res.style.color="#1e90ff"; res.textContent="🔍 Scan en cours...";
  fetch("/api/store/scan/"+id).then(r=>r.json()).then(d=>{{
    res.style.color=d.success?"#4caf50":"#f44336";
    res.textContent=d.message;
    if(d.success) setTimeout(()=>location.reload(),1200);
  }}).catch(e=>{{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
}}
function showAddFile(id){{
  var el=document.getElementById("add-file-"+id);
  el.style.display=el.style.display==="none"||el.style.display===""?"flex":"none";
}}
function addAppFile(id){{
  var val=document.getElementById("af-input-"+id).value.trim();
  if(!val) return;
  var res=document.getElementById("sr-"+id);
  res.style.display="block"; res.style.color="#ff9800"; res.textContent="⏳ Enregistrement...";
  fetch("/api/store/register-file",{{method:"POST",headers:{{"Content-Type":"application/json"}},
    body:JSON.stringify({{app_id:id,filename:val}})}})
  .then(r=>r.json()).then(d=>{{
    res.style.color=d.success?"#4caf50":"#f44336"; res.textContent=d.message;
    if(d.success) setTimeout(()=>location.reload(),1200);
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
function appStart(id){{
  var res=document.getElementById("sr-"+id);
  res.style.display="block"; res.style.color="#ff9800";
  res.textContent="⏳ Demarrage en cours...";
  fetch("/api/store/start/"+id,{{method:"POST"}}).then(r=>r.json()).then(d=>{{
    res.style.color=d.success?"#4caf50":"#f44336";
    res.textContent=d.message;
    if(d.success){{
      checkRunning(id);
      // Auto-scan appdata 5s apres le demarrage (l'app a eu le temps de creer data/)
      setTimeout(()=>scanAfterStart(id), 5000);
    }}
  }}).catch(e=>{{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
}}
function appStop(id){{
  var res=document.getElementById("sr-"+id);
  res.style.display="block"; res.style.color="#ff9800"; res.textContent="⏳ Arret...";
  fetch("/api/store/stop/"+id,{{method:"POST"}}).then(r=>r.json()).then(d=>{{
    res.style.color=d.success?"#4caf50":"#f44336"; res.textContent=d.message;
    if(d.success) setTimeout(()=>checkRunning(id),1500);
  }}).catch(e=>{{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
}}
function checkRunning(id){{
  fetch("/api/store/running/"+id).then(r=>r.json()).then(d=>{{
    var btnStart=document.getElementById("btn-start-"+id);
    var btnStop =document.getElementById("btn-stop-"+id);
    var res     =document.getElementById("sr-"+id);
    if(d.running){{
      if(btnStart) btnStart.style.opacity="0.4";
      if(btnStop)  btnStop.style.opacity="1";
    }} else {{
      if(btnStart) btnStart.style.opacity="1";
      if(btnStop)  btnStop.style.opacity="0.4";
    }}
  }}).catch(()=>{{}});
}}
function scanAfterStart(id){{
  var res=document.getElementById("sr-"+id);
  res.style.display="block"; res.style.color="#1e90ff";
  res.textContent="🔍 Scan appdata apres lancement...";
  fetch("/api/store/scan-and-save/"+id,{{method:"POST"}})
    .then(r=>r.json()).then(d=>{{
      res.style.color=d.success?"#4caf50":"#888";
      var saved=d.saved&&d.saved.length?"📄 "+d.saved.join(", "):"(aucun fichier detecte)";
      res.textContent=d.message+" | "+saved;
      if(d.success&&d.appdata_files&&d.appdata_files.length)
        setTimeout(()=>location.reload(),1500);
    }}).catch(e=>{{res.style.color="#888";res.textContent="Erreur: "+e;}});
}}
// Verifier le statut de toutes les apps au chargement
document.addEventListener("DOMContentLoaded", function(){{
  document.querySelectorAll("[id^='btn-start-']").forEach(function(btn){{
    var id = btn.id.replace("btn-start-","");
    checkRunning(id);
  }});
}});
</script>
</body></html>'''
        return HTMLResponse(page)
