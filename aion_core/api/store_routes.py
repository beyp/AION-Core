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

    # Lazy init : AppStore cree a la premiere requete, pas a l'import
    # Evite les crashes si C:\AION_APPS n'existe pas encore au demarrage
    _store_instance = [None]

    def _get_store():
        if _store_instance[0] is None:
            from aion_core.store.app_store import AppStore
            try:
                _store_instance[0] = AppStore()
            except Exception as e:
                logger.error("AppStore init failed: %s", e)
                raise
        return _store_instance[0]

    # ── API REST ──────────────────────────────────────────────────

    @app.get("/api/store/status")
    async def store_status():
        return {"apps": _get_store().status()}

    @app.get("/api/store/scan/{app_id}")
    async def store_scan(app_id: str):
        """
        Scanne les fichiers persistants d'un repo installe et les sauvegarde.
        Utile apres un premier lancement (data/ cree par l'app au runtime).
        Liste TOUS les fichiers du repo pour debug si scan vide.
        """
        result = _get_store().scan_appdata(app_id)
        store_cfg = _get_store()._get_store_cfg(app_id)

        if result.get("success"):
            if result.get("appdata_files"):
                # Fichiers detectes → sauvegarder immediatement
                if store_cfg and store_cfg.get("install_path"):
                    save_result = _get_store().appdata_mgr.save(
                        app_id,
                        store_cfg["install_path"],
                        result["appdata_files"]
                    )
                    result["saved"]   = save_result.get("saved", [])
                    result["missing"] = save_result.get("missing", [])
            else:
                # Scan vide → lister ce qui existe dans le dossier pour debug
                if store_cfg and store_cfg.get("install_path"):
                    from pathlib import Path as _P
                    install = _P(store_cfg["install_path"])
                    all_files = []
                    if install.exists():
                        for f in install.rglob("*"):
                            if f.is_file():
                                rel = str(f.relative_to(install)).replace("\\", "/")
                                skip = any(p in rel for p in [".git/",".venv/","__pycache__",
                                                               "node_modules/",".pyc"])
                                if not skip:
                                    all_files.append(rel)
                    result["all_files_in_repo"] = sorted(all_files)[:50]
                    result["message"] = (
                        f"Aucun fichier persistant detecte automatiquement. "
                        f"{len(all_files)} fichiers trouves dans le repo. "
                        f"Lance l'app d'abord, puis re-scanne. "
                        f"Ou declare manuellement avec le bouton Ajouter."
                    )
        return result

    @app.post("/api/store/scan-and-save/{app_id}")
    async def store_scan_and_save(app_id: str):
        """
        Re-scanne ET sauvegarde immediatement dans appdata/.
        A appeler apres le premier lancement d'une app nouvellement installee.
        """
        result = _get_store().scan_appdata(app_id)
        if result.get("success") and result.get("appdata_files"):
            store_cfg = _get_store()._get_store_cfg(app_id)
            if store_cfg and store_cfg.get("install_path"):
                save_result = _get_store().appdata_mgr.save(
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
        Installe une app depuis GitHub puis la lance automatiquement.
        Body: {
            "github":       "owner/repo",
            "app_id":       "...",           (optionnel)
            "appdata_files": [...],          (optionnel - scan auto si absent)
            "port":         8765,            (optionnel)
            "app_type":     "auto",          (auto|fastapi|docker|python)
        }
        """
        from aion_core.store.process_manager import ProcessManager
        from pathlib import Path as _P
        import json as _json
        body          = await request.json()
        github_repo   = body.get("github", "")
        app_id        = body.get("app_id") or None
        appdata_files = body.get("appdata_files") or None
        port          = int(body.get("port", 0))
        app_type      = body.get("app_type", "auto")

        if not github_repo:
            return JSONResponse({"success": False,
                "message": "github requis (ex: beyp/QuickMind)"}, status_code=400)

        # 1. Clone + setup (venv, pip, bat)
        result = _get_store().install(github_repo, app_id=app_id,
                                      appdata_files=appdata_files)
        if not result.get("success"):
            return result

        installed_id = result.get("app_id", app_id or
                                  github_repo.split("/")[-1].lower())
        install_path = result.get("install_path", "")

        # 2. Recharger le router
        try:
            aion_app.app_router.reload_apps()
        except Exception as e:
            logger.warning("Reload apps: %s", e)

        # 3. Auto-detect type + lancement via ProcessManager
        pm = ProcessManager()
        detected = pm.detect_launch_type(install_path)
        result["detected_type"] = detected["type"]
        result["detected_cmd"]  = detected["command"]
        result["detected_info"] = detected["info"]

        # Determiner le port depuis apps.local.json si non fourni
        if not port:
            for rf in [_P("apps.local.json"), _P("apps.json")]:
                if rf.exists():
                    try:
                        reg = _json.loads(rf.read_text(encoding="utf-8"))
                        port = (reg.get("apps", {}).get(installed_id, {})
                                   .get("autostart", {}).get("port", 0))
                        if port: break
                    except Exception:
                        pass

        # Preparer env avec AION_DATA_DIR
        env = {
            "AION_DATA_DIR":  str(_P("C:/AION_APPS/appdata") / installed_id),
            "AION_APP_ID":    installed_id,
        }

        launch_result = pm.start(
            app_id       = installed_id,
            install_path = install_path,
            app_type     = app_type if app_type != "auto" else detected["type"],
            command      = detected["command"] if detected["type"] != "unknown" else None,
            port         = port,
            env          = env,
        )
        result["launch"] = launch_result
        logger.info("Post-install launch %s: %s", installed_id, launch_result)

        return result

    @app.post("/api/store/update/{app_id}")
    async def store_update(app_id: str):
        """Git pull + backup appdata automatique."""
        return _get_store().update(app_id)

    @app.post("/api/store/restore/{app_id}")
    async def store_restore(app_id: str):
        """Restaure les fichiers depuis appdata/ vers le repo."""
        return _get_store().restore_appdata(app_id)

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
        return _get_store().register_appdata_file(app_id, filename)

    @app.delete("/api/store/{app_id}")
    async def store_uninstall(app_id: str, keep_appdata: bool = True):
        """Desinstalle une app (garde appdata par defaut)."""
        result = _get_store().uninstall(app_id, keep_appdata=keep_appdata)
        if result.get("success"):
            try:
                aion_app.app_router.reload_apps()
            except Exception:
                pass
        return result

    @app.get("/api/store/{app_id}/appdata")
    async def store_list_appdata(app_id: str):
        return {"app_id": app_id, "files": _get_store().list_appdata(app_id)}

    @app.get("/api/store/{app_id}/config")
    async def store_get_config(app_id: str):
        """Lit config app + infos shared (GROQ_API_KEY, ADO_PAT, etc.)."""
        from pathlib import Path as _P
        from aion_core.store.config_editor import ConfigEditor
        from aion_core.store.shared_config  import SharedConfig
        import json as _j

        install_path = appdata_path = ""
        app_shared_keys = []
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    d = _j.loads(rf.read_text(encoding="utf-8"))
                    app_cfg = d.get("apps", {}).get(app_id, {})
                    s = app_cfg.get("store", {})
                    install_path    = s.get("install_path", "")
                    appdata_path    = s.get("appdata_path", "")
                    app_shared_keys = app_cfg.get("shared_keys", [])
                    if install_path: break
                except Exception: pass

        if not install_path:
            return {"success": False, "message": f"App '{app_id}' non trouvee"}

        editor     = ConfigEditor(app_id, install_path, appdata_path)
        app_config = editor.read_all()

        shared = SharedConfig()
        for fname, fdata in app_config.get("files", {}).items():
            fdata["fields"] = shared.enrich_fields(fdata.get("fields", []), app_shared_keys)

        shared_data = shared.read_all()
        app_config["shared_available"] = list(shared_data.keys())
        app_config["shared_count"]     = len(shared_data)
        return app_config

    @app.post("/api/store/{app_id}/config")
    async def store_save_config(app_id: str, request: Request):
        """
        Sauvegarde des champs de config dans appdata/.
        Body: {"filename": "config.yaml", "key": "updater.github_token", "value": "..."}
        ou   {"updates": {"config.yaml": {"key": "val"}, ".env": {"KEY": "val"}}}
        """
        from pathlib import Path as _P
        from aion_core.store.config_editor import ConfigEditor
        import json as _j

        body         = await request.json()
        install_path = appdata_path = ""
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    d = _j.loads(rf.read_text(encoding="utf-8"))
                    s = d.get("apps", {}).get(app_id, {}).get("store", {})
                    install_path = s.get("install_path", "")
                    appdata_path = s.get("appdata_path", "")
                    if install_path: break
                except Exception: pass

        if not install_path:
            return {"success": False, "message": f"App '{app_id}' non trouvee"}

        editor = ConfigEditor(app_id, install_path, appdata_path)

        # Mode bulk
        if "updates" in body:
            return editor.save_all_fields(body["updates"])

        # Mode single field
        filename = body.get("filename", "")
        key      = body.get("key", "")
        value    = body.get("value", "")
        if not all([filename, key]):
            return {"success": False, "message": "filename et key requis"}
        return editor.save_field(filename, key, value)
    @app.post("/api/store/{app_id}/config/inherit")
    async def store_inherit_shared(app_id: str, request: Request):
        """Propage les valeurs partagées (shared.env) vers le .env de l'app."""
        from pathlib import Path as _P2
        from aion_core.store.shared_config import SharedConfig
        import json as _j2
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        appdata_path = ""
        app_shared_keys = []
        for rf in [_P2("apps.local.json"), _P2("apps.json")]:
            if rf.exists():
                try:
                    d = _j2.loads(rf.read_text(encoding="utf-8"))
                    app_cfg = d.get("apps", {}).get(app_id, {})
                    appdata_path    = app_cfg.get("store", {}).get("appdata_path", "")
                    app_shared_keys = app_cfg.get("shared_keys", [])
                    if appdata_path: break
                except Exception: pass
        if not appdata_path:
            return {"success": False, "message": f"App '{app_id}' introuvable"}
        keys   = body.get("keys", app_shared_keys or None)
        shared = SharedConfig()
        return shared.propagate_to_app(app_id, appdata_path, keys)

    @app.get("/api/shared")
    async def get_shared_config():
        """Retourne toutes les valeurs partagées AION."""
        from aion_core.store.shared_config import SharedConfig, KNOWN_SHARED_KEYS
        shared = SharedConfig()
        data   = shared.read_all()
        SENSITIVE = {"api_key","token","secret","password","pat","groq"}
        def _sens(k): return any(s in k.lower() for s in SENSITIVE)
        def _empty(v): return not v or v.strip() in {"","your_key_here","gsk_your_key_here","your_pat_here"}
        fields = [{"key":k,"value":v,"sensitive":_sens(k),"empty":_empty(v)} for k,v in data.items()]
        for k in sorted(KNOWN_SHARED_KEYS):
            if k not in data:
                fields.append({"key":k,"value":"","sensitive":_sens(k),"empty":True})
        return {"fields": fields, "total": len(fields), "defined": len(data)}

    @app.post("/api/shared")
    async def save_shared_config(request: Request):
        """Sauvegarde des valeurs partagées + propagation optionnelle."""
        from aion_core.store.shared_config import SharedConfig
        body    = await request.json()
        updates = body.get("updates", {})
        if not updates:
            return {"success": False, "message": "Aucune mise à jour fournie"}
        shared  = SharedConfig()
        results = shared.set_many(updates)
        saved   = [k for k, ok in results.items() if ok]
        prop    = None
        if body.get("propagate", False):
            prop = shared.propagate_to_all_apps()
        return {"success": True, "message": f"{len(saved)} valeur(s) sauvegardée(s)",
                "saved": saved, "propagation": prop}

    @app.post("/api/shared/propagate")
    async def propagate_shared():
        """Propage toutes les valeurs partagées à toutes les apps."""
        from aion_core.store.shared_config import SharedConfig
        return SharedConfig().propagate_to_all_apps()



    @app.post("/api/store/start/{app_id}")
    async def store_start(app_id: str):
        """
        Lance une app via ProcessManager (bouton Start dans /store ou commande IA).
        Detecte automatiquement le type (fastapi/docker/python) et la commande.
        """
        from pathlib import Path as _P
        from aion_core.store.process_manager import ProcessManager
        import json as _json

        # Lire la config de l'app
        registry = {}
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    data = _json.loads(rf.read_text(encoding="utf-8"))
                    for k, v in data.get("apps", {}).items():
                        registry.setdefault(k, v)
                except Exception:
                    pass

        app_cfg = registry.get(app_id)
        if not app_cfg:
            return {"success": False,
                    "message": f"App '{app_id}' introuvable. Installe-la via /store."}

        store_cfg    = app_cfg.get("store", {})
        autostart    = app_cfg.get("autostart", {})
        install_path = (store_cfg.get("install_path") or
                        autostart.get("path") or "")

        if not install_path or not _P(install_path).exists():
            return {"success": False,
                    "message": f"Dossier non trouve: {install_path!r}. "
                               f"Reinstalle l'app via /store."}

        port = int(autostart.get("port", 0) or
                   app_cfg.get("port", 0) or 0)

        env = {
            "AION_DATA_DIR": str(_P("C:/AION_APPS/appdata") / app_id),
            "AION_APP_ID":   app_id,
        }
        env.update(autostart.get("env", {}))

        pm = ProcessManager()
        # Commande explicite si configuree et valide
        cmd = autostart.get("command", [])
        explicit_cmd = cmd if (cmd and _P(cmd[0]).exists()) else None

        result = pm.start(
            app_id       = app_id,
            install_path = install_path,
            app_type     = autostart.get("mode", "auto"),
            command      = explicit_cmd,
            port         = port,
            env          = env,
        )
        logger.info("Start %s: %s", app_id, result.get("message"))
        return result

    @app.post("/api/store/stop/{app_id}")
    async def store_stop(app_id: str):
        """Stoppe une app via ProcessManager (PID + port)."""
        from pathlib import Path as _P
        from aion_core.store.process_manager import ProcessManager
        import json as _j
        port = 0
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    d = _j.loads(rf.read_text(encoding="utf-8"))
                    port = d.get("apps",{}).get(app_id,{}).get("autostart",{}).get("port",0)
                    if port: break
                except Exception: pass
        pm = ProcessManager()
        result = pm.stop(app_id, port=int(port))
        logger.info("Stop %s: %s", app_id, result.get("message"))
        return result

    @app.get("/api/store/running/{app_id}")
    async def store_is_running(app_id: str):
        """Verifie si une app tourne (PID sauvegarde + port)."""
        from pathlib import Path as _P
        from aion_core.store.process_manager import ProcessManager
        import json as _j
        port = 0; url = ""
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    d    = _j.loads(rf.read_text(encoding="utf-8"))
                    cfg  = d.get("apps",{}).get(app_id,{})
                    port = cfg.get("autostart",{}).get("port",0)
                    url  = cfg.get("url","")
                    if port or url: break
                except Exception: pass
        pm = ProcessManager()
        running = pm.is_running(app_id, int(port))
        return {"app_id": app_id, "running": running, "url": url, "port": port}


    # ── Page Web App Store ────────────────────────────────────────

    @app.get("/store", response_class=HTMLResponse)
    async def store_page(request: Request):
        apps_status = _get_store().status()
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
                        padding:6px 10px;border-radius:5px;font-size:.82rem;"
                        onkeydown="if(event.key==='Enter') addAppFile('{app_id}')"
                        title="Entree pour ajouter">
                      <button onclick="addAppFile('{app_id}')"
                        style="background:#ff9800;color:#fff;border:none;padding:6px 12px;
                        border-radius:5px;cursor:pointer;font-size:.8rem;">➕</button>
                    </div>
                  </div>
                </div>
                '''
            else:
                # Suggestions basees sur le nom de l'app
                _suggestions = [
                    f"data/{app_id}.db",
                    f"{app_id}.db",
                    "memory.json",
                    "data/database.db",
                ]
                _sugg_btns = " ".join(
                    f'<button onclick="quickAddFile(\'{app_id}\',\'{s}\')" ' +
                    'style="background:#1e90ff11;border:1px solid #1e90ff33;color:#1e90ff;' +
                    'padding:2px 8px;border-radius:4px;cursor:pointer;font-size:.72rem;margin:2px;">' +
                    s + '</button>'
                    for s in _suggestions
                )
                appdata_html = f'''
                <div style="margin-top:8px;font-size:.8rem;color:#888;">
                  <div style="margin-bottom:6px;">
                    <span style="color:#ff9800;">⚠️</span>
                    Aucun fichier persistant detecte.
                    <button onclick="scanAppdata(\'{app_id}\')"
                      style="margin-left:6px;background:transparent;border:1px solid #2a2d3e;
                      color:#1e90ff;padding:1px 8px;border-radius:4px;cursor:pointer;font-size:.72rem;">
                      🔍 Scanner apres lancement</button>
                  </div>
                  <div style="margin-bottom:6px;color:#666;font-size:.75rem;">
                    Suggestions (clic pour ajouter) :
                    {_sugg_btns}
                  </div>
                  <div style="display:flex;gap:6px;">
                    <input id="af-input-{app_id}" type="text"
                      placeholder="Chemin relatif (ex: data/{app_id}.db)"
                      style="flex:1;background:#12141f;border:1px solid #2a2d3e;color:#e0e0e0;
                      padding:5px 10px;border-radius:5px;font-size:.8rem;"
                      onkeydown="if(event.key==='Enter') addAppFile(\'{app_id}\')"
                      title="Entree pour ajouter">
                    <button onclick="addAppFile(\'{app_id}\')"
                      style="background:#ff9800;color:#fff;border:none;padding:5px 12px;
                      border-radius:5px;cursor:pointer;font-size:.8rem;">➕ Ajouter</button>
                  </div>
                  <div id="sr-add-{app_id}" style="font-size:.75rem;margin-top:4px;display:none;"></div>
                </div>
                '''  

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
                <button onclick="openConfig('{app_id}')"
                  title="Configurer les cles API et parametres de l'app"
                  style="background:#ff980022;border:1px solid #ff980055;color:#ff9800;
                  padding:6px 14px;border-radius:6px;cursor:pointer;font-size:.82rem;font-weight:600;">
                  &#x2699;&#xFE0F; Config</button>
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
      <div style="font-weight:600;margin-bottom:12px;color:#1e90ff;">&#x2795; Installer une nouvelle app</div>
      <div style="display:grid;grid-template-columns:1fr 110px 155px auto;gap:8px;align-items:end;">
        <div>
          <label style="font-size:.75rem;color:#888;display:block;margin-bottom:4px;">Repo GitHub</label>
          <input id="inst-repo" type="text" placeholder="owner/repo  (ex: beyp/QuickMind)"
            style="width:100%;background:#12141f;border:1px solid #2a2d3e;color:#e0e0e0;
            padding:9px 14px;border-radius:6px;font-size:.88rem;"
            onkeydown="if(event.key==='Enter') doInstall()"
            title="Entree pour installer">
        </div>
        <div>
          <label style="font-size:.75rem;color:#888;display:block;margin-bottom:4px;">Port</label>
          <input id="inst-port" type="number" placeholder="ex: 8765"
            style="width:100%;background:#12141f;border:1px solid #2a2d3e;color:#e0e0e0;
            padding:9px 10px;border-radius:6px;font-size:.85rem;">
        </div>
        <div>
          <label style="font-size:.75rem;color:#888;display:block;margin-bottom:4px;">Type</label>
          <select id="inst-type"
            style="width:100%;background:#12141f;border:1px solid #2a2d3e;color:#e0e0e0;
            padding:9px 8px;border-radius:6px;font-size:.82rem;">
            <option value="auto">&#x1F50D; Auto-detect</option>
            <option value="docker">&#x1F433; Docker Compose</option>
            <option value="uvicorn">&#x26A1; Uvicorn/FastAPI</option>
            <option value="python">&#x1F40D; Python script</option>
          </select>
        </div>
        <div>
          <label style="font-size:.75rem;color:#888;display:block;margin-bottom:4px;">&nbsp;</label>
          <button onclick="doInstall()"
            style="background:#1e90ff;color:#fff;border:none;padding:9px 16px;
            border-radius:6px;cursor:pointer;font-size:.88rem;font-weight:600;white-space:nowrap;">
            &#x1F4E5; Installer
          </button>
        </div>
      </div>
      <p style="font-size:.73rem;color:#555;margin-top:6px;">
        &#x1F4A1; <strong>Auto-detect</strong> : priorite docker-compose.yml, puis run_api.py, main.py.
        DB detectee apres 1er lancement via <strong>Scan AppData</strong>.</p>
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
  var repo  = document.getElementById("inst-repo").value.trim();
  var port  = parseInt(document.getElementById("inst-port").value) || 0;
  var atype = document.getElementById("inst-type").value;
  var res   = document.getElementById("inst-result");
  if(!repo){{ alert("Saisis un repo GitHub (ex: beyp/QuickMind)"); return; }}
  res.style.display="block"; res.style.background="rgba(255,152,0,.1)";
  res.style.color="#ff9800";
  res.innerHTML="&#x23F3; Installation... git clone + setup (venv ou docker build) peut prendre 1-5 min";
  fetch("/api/store/install",{{method:"POST",headers:{{"Content-Type":"application/json"}},
    body:JSON.stringify({{github:repo,port:port,app_type:atype}})}})
  .then(function(r){{return r.json();}})
  .then(function(d){{
    res.style.background=d.success?"rgba(76,175,80,.1)":"rgba(244,67,54,.1)";
    res.style.color=d.success?"#4caf50":"#f44336";
    var typeInfo = d.detected_type
      ? "<br>&#x1F50D; Type : <strong>"+d.detected_type+"</strong>"
        +(d.detected_info?" &mdash; "+d.detected_info:"")
      : "";
    var files = d.appdata_files&&d.appdata_files.length
      ? "<br>&#x1F4C4; Appdata : <code style='color:#ccc;'>"+d.appdata_files.join(", ")+"</code>"
      : "";
    var launch = d.launch
      ? (d.launch.success
          ? "<br>&#x25B6; Lance : "+(d.launch.message||"OK")
          : "<br>&#x26A0; Lancement : "+(d.launch.message||"non configure"))
      : "";
    res.innerHTML = d.message + typeInfo + files + launch;
    if(d.success) setTimeout(function(){{location.reload();}},2500);
  }}).catch(function(e){{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
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
    res.style.color=d.success?"#4caf50":"#888";
    var msg=d.message;
    if(d.all_files_in_repo&&d.all_files_in_repo.length){{
      msg+=" | Fichiers dans repo: "+d.all_files_in_repo.slice(0,6).join(", ");
      if(d.all_files_in_repo.length>6) msg+=" +"+(d.all_files_in_repo.length-6)+" autres";
    }}
    res.innerHTML=msg;
    if(d.success&&d.appdata_files&&d.appdata_files.length) setTimeout(()=>location.reload(),1500);
  }}).catch(e=>{{res.style.color="#f44336";res.textContent="Erreur: "+e;}});
}}
function showAddFile(id){{
  var el=document.getElementById("add-file-"+id);
  el.style.display=el.style.display==="none"||el.style.display===""?"flex":"none";
}}
function quickAddFile(id,filename){{
  // Remplir le champ et soumettre directement
  var input=document.getElementById("af-input-"+id);
  if(input){{ input.value=filename; addAppFile(id); return; }}
  // Si input pas visible (appdata non vide), appel direct API
  var res=document.getElementById("sr-"+id)||document.getElementById("sr-add-"+id);
  if(res){{res.style.display="block";res.style.color="#ff9800";res.textContent="⏳ Ajout...";}}
  fetch("/api/store/register-file",{{method:"POST",headers:{{"Content-Type":"application/json"}},
    body:JSON.stringify({{app_id:id,filename:filename}})}}).then(r=>r.json()).then(d=>{{
    if(res){{res.style.color=d.success?"#4caf50":"#f44336";res.textContent=d.message;}}
    if(d.success) setTimeout(()=>location.reload(),1000);
  }}).catch(e=>{{if(res) res.textContent="Erreur: "+e;}});
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
// ── Modal Config ──────────────────────────────────────────────
function openConfig(id) {{
  var modal = document.getElementById("config-modal");
  var body  = document.getElementById("config-body");
  var title = document.getElementById("config-title");
  if (!modal) return;
  title.textContent = "⚙️ Configuration : " + id;
  body.innerHTML = "<div style='color:#888;text-align:center;padding:20px;'>⏳ Chargement...</div>";
  modal.style.display = "flex";

  fetch("/api/store/" + id + "/config")
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      if (!d.files || Object.keys(d.files).length === 0) {{
        body.innerHTML = "<p style='color:#888;'>Aucun fichier de config trouve (config.yaml, .env).</p>" +
          "<p style='color:#555;font-size:.8rem;'>Lance l'app une fois puis reviens ici.</p>";
        return;
      }}
      var html = "";
      if (d.has_empty) {{
        html += "<div style='background:rgba(244,67,54,.1);border:1px solid rgba(244,67,54,.3);" +
          "border-radius:6px;padding:8px 12px;margin-bottom:12px;font-size:.8rem;color:#f44336;'>" +
          "&#x26A0;&#xFE0F; " + d.empty_count + " cle(s) non configuree(s)</div>";
      }}
      Object.entries(d.files).forEach(function(entry) {{
        var fname  = entry[0];
        var fdata  = entry[1];
        var loc    = fdata.in_appdata ? "&#x1F512; appdata/" : "&#x1F4C1; repo/";
        html += "<div style='margin-bottom:14px;'>";
        html += "<div style='font-size:.78rem;color:#888;margin-bottom:6px;display:flex;justify-content:space-between;'>";
        html += "<strong style='color:#e0e0e0;'>"+fname+"</strong>";
        html += "<span>"+loc+"</span></div>";
          var emptyStyle = f.empty
            ? "border-color:#f44336;background:rgba(244,67,54,.05);"
            : (f.shared ? "border-color:#1e90ff44;" : "border-color:#2a2d3e;");
          var inputType = f.sensitive ? "password" : "text";
          var placeholder = f.empty ? "⚠️ Non configuré" : "";
          var inputId = "inp_" + fname.replace(/[^a-z0-9]/gi,"_") + "_" + f.key.replace(/[^a-z0-9]/gi,"_");
          html += "<div style='display:flex;align-items:center;gap:6px;margin-bottom:6px;'>";
          var labelColor = f.empty ? "#f44336" : (f.shared ? "#1e90ff" : "#888");
          var sharedBadge = f.shared ? "<span title='Valeur partagee AION' style='font-size:.65rem;background:rgba(30,144,255,.15);color:#1e90ff;padding:1px 5px;border-radius:4px;margin-left:4px;'>&#x1F517; AION</span>" : "";
          html += "<label style='width:160px;font-size:.78rem;color:"+labelColor+";flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;' title='"+f.key+"'>" + f.key + sharedBadge + "</label>";
          html += "<input id='"+inputId+"' type='"+inputType+"' value='"+(f.sensitive && !f.empty ? "••••••" : f.value.replace(/'/g, "&#39;"))+"'" +
            " data-key='"+f.key+"' data-file='"+fname+"' data-app='"+id+"'" +
            " data-sensitive='"+f.sensitive+"' data-realvalue='"+f.value.replace(/'/g, "&#39;")+"'" +
            " placeholder='"+placeholder+"'" +
            " style='flex:1;background:#12141f;border:1px solid;"+emptyStyle+
            "color:#e0e0e0;padding:5px 10px;border-radius:5px;font-size:.82rem;'" +
            " onchange='markChanged(this)'>";
          if (f.sensitive) {{
            html += "<button type='button' data-toggle-input='"+inputId+"'" +
              " class='btn-toggle-secret' title='Afficher / Masquer'" +
              " style='background:none;border:1px solid #2a2d3e;border-radius:5px;" +
              "padding:4px 7px;cursor:pointer;color:#888;font-size:.85rem;flex-shrink:0;'>&#128065;</button>";
          }}
          if (f.shared && f.inheritable) {{
            html += "<button type='button' data-inherit-key='"+f.key+"' data-inherit-file='"+fname+"'" +
              " class='btn-inherit-shared' title='Heriter depuis AION shared.env'" +
              " style='background:rgba(30,144,255,.1);border:1px solid #1e90ff44;border-radius:5px;" +
              "padding:4px 7px;cursor:pointer;color:#1e90ff;font-size:.75rem;flex-shrink:0;'>&#x21A9; Heriter</button>";
          }}
          html += "</div>";
          html += "</div>";
        }});
        html += "</div>";
      }});
      html += "<div id='config-save-result' style='font-size:.82rem;margin-top:4px;'></div>";
      body.innerHTML = html;
    }})
    .catch(function(e) {{
      body.innerHTML = "<p style='color:#f44336;'>Erreur: " + e + "</p>";
    }});
}}

function markChanged(input) {{
  input.style.borderColor = "#ff9800";
  input.dataset.changed = "1";
}}

document.addEventListener('click', function(e) {{
  var inh = e.target.closest('.btn-inherit-shared');
  if (inh) {{
    var key   = inh.getAttribute('data-inherit-key');
    var appId = document.getElementById('config-title').textContent.split(': ')[1];
    fetch('/api/store/' + appId + '/config/inherit', {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{keys: [key]}})
    }}).then(r => r.json()).then(d => {{
      var res = document.getElementById('config-save-result');
      if (res) {{
        res.style.color = d.success ? '#4caf50' : '#f44336';
        res.textContent = d.success ? '\u2705 ' + key + ' herite depuis AION' : d.message;
      }}
      if (d.success) setTimeout(function(){{ openConfig(appId); }}, 800);
    }});
    return;
  }}
}});

document.addEventListener('click', function(e) {{
  var btn = e.target.closest('.btn-toggle-secret');
  if (!btn) return;
  var inputId = btn.getAttribute('data-toggle-input');
  var inp = document.getElementById(inputId);
  if (!inp) return;
  if (inp.type === 'password') {{
    inp.type = 'text';
    var real = inp.dataset.realvalue || '';
    if (inp.value === '••••••') inp.value = real;
    btn.style.color = '#1E90FF';
  }} else {{
    inp.type = 'password';
    btn.style.color = '#888';
  }}
}})

function saveConfig(id) {{
  var inputs  = document.querySelectorAll("[data-app='"+id+"'][data-changed='1']");
  var updates = {{}};
  inputs.forEach(function(inp) {{
    var file = inp.dataset.file;
    var key  = inp.dataset.key;
    var val  = inp.value;
    if (val === "••••••") return; // masque non modifie
    if (!updates[file]) updates[file] = {{}};
    updates[file][key] = val;
  }});
  if (Object.keys(updates).length === 0) {{
    document.getElementById("config-save-result").textContent = "Aucune modification.";
    return;
  }}
  var res = document.getElementById("config-save-result");
  res.style.color = "#ff9800"; res.textContent = "⏳ Sauvegarde...";
  fetch("/api/store/" + id + "/config", {{
    method: "POST",
    headers: {{"Content-Type": "application/json"}},
    body: JSON.stringify({{updates: updates}})
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    res.style.color = d.success ? "#4caf50" : "#f44336";
    res.textContent = d.message;
    if (d.success) {{
      document.querySelectorAll("[data-app='"+id+"'][data-changed='1']").forEach(function(i) {{
        i.style.borderColor = "#4caf50"; i.dataset.changed = "0";
      }});
    }}
  }})
  .catch(function(e) {{ res.style.color="#f44336"; res.textContent="Erreur: "+e; }});
}}

function closeConfig() {{
  document.getElementById("config-modal").style.display = "none";
}}
</script>

<!-- Modal Config -->
<div id="config-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);
  z-index:2000;align-items:center;justify-content:center;">
  <div style="background:#1a1d27;border:1px solid #2a2d3e;border-radius:12px;
    width:600px;max-width:95vw;max-height:85vh;display:flex;flex-direction:column;">
    <!-- Header modal -->
    <div style="display:flex;align-items:center;padding:16px 20px;
      border-bottom:1px solid #2a2d3e;flex-shrink:0;">
      <span id="config-title" style="font-weight:600;font-size:1rem;flex:1;"></span>
      <button onclick="closeConfig()"
        style="background:transparent;border:none;color:#888;cursor:pointer;font-size:1.2rem;">&#x2715;</button>
    </div>
    <!-- Body scrollable -->
    <div id="config-body" style="padding:16px 20px;overflow-y:auto;flex:1;"></div>
    <!-- Footer -->
    <div style="padding:12px 20px;border-top:1px solid #2a2d3e;display:flex;
      justify-content:flex-end;gap:8px;flex-shrink:0;">
      <div style="flex:1;font-size:.75rem;color:#555;">
        &#x1F512; Les valeurs sont sauvegardees dans <code style="color:#888;">C:/AION_APPS/appdata/</code>
        — jamais dans git.
      </div>
      <button onclick="var id=document.getElementById('config-title').textContent.split(': ')[1]; saveConfig(id);"
        style="background:#1e90ff;color:#fff;border:none;padding:8px 20px;
        border-radius:6px;cursor:pointer;font-size:.88rem;font-weight:600;">
        &#x1F4BE; Sauvegarder
      </button>
      <button onclick="closeConfig()"
        style="background:transparent;border:1px solid #2a2d3e;color:#888;
        padding:8px 14px;border-radius:6px;cursor:pointer;font-size:.85rem;">
        Fermer
      </button>
    </div>
  </div>
</div>

</body></html>'''
        return HTMLResponse(page)
