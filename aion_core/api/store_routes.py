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


    # ── Backup routes ─────────────────────────────────────────────

    @app.post("/api/store/backup/{app_id}")
    async def store_backup(app_id: str, request: Request):
        """Backup manuel. Body: {"force": false}"""
        from pathlib import Path as _P
        from aion_core.store.backup_manager import BackupManager
        import json as _j
        body  = {}
        try: body = await request.json()
        except Exception: pass
        force = body.get("force", False)
        install_path, extra_files = "", []
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    d = _j.loads(rf.read_text(encoding="utf-8"))
                    s = d.get("apps", {}).get(app_id, {}).get("store", {})
                    install_path = s.get("install_path", "")
                    extra_files  = s.get("appdata_files", [])
                    if install_path: break
                except Exception: pass
        if not install_path:
            return {"success": False, "message": f"App '{app_id}' introuvable"}
        bm  = BackupManager()
        res = bm.backup_app(app_id, install_path, extra_files=extra_files, force=force)
        if not res.get("confirmed") and res.get("already_existed"):
            return {
                "success": False, "already_existed": True,
                "message": res["message"], "backup_path": res.get("backup_path", ""),
            }
        return res

    @app.get("/api/store/backups/{app_id}")
    async def store_list_backups(app_id: str):
        """Liste les backups disponibles pour une app."""
        from aion_core.store.backup_manager import BackupManager
        return {"app_id": app_id, "backups": BackupManager().list_backups(app_id)}

    @app.post("/api/store/restore-backup/{app_id}")
    async def store_restore_backup(app_id: str, request: Request):
        """Restaure un backup specifique. Body: {"backup_path": "..."}"""
        from pathlib import Path as _P
        from aion_core.store.backup_manager import BackupManager
        import json as _j
        body         = await request.json()
        backup_path  = body.get("backup_path", "")
        install_path = ""
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    d = _j.loads(rf.read_text(encoding="utf-8"))
                    install_path = d.get("apps", {}).get(app_id, {}).get("store", {}).get("install_path", "")
                    if install_path: break
                except Exception: pass
        if not backup_path or not install_path:
            return {"success": False, "message": "backup_path et install_path requis"}
        return BackupManager().restore_backup(backup_path, install_path)

    # ── Detection auto pour installation ──────────────────────────

    @app.post("/api/store/detect")
    async def store_detect(request: Request):
        """
        Detecte les possibilites de lancement d'un repo existant.
        Body: {"install_path": "C:/code/python/QuickMind"}
        Retourne: options detectees avec recommandation + start_bat existant.
        """
        from pathlib import Path as _P
        from aion_core.store.process_manager import ProcessManager
        body         = await request.json()
        install_path = body.get("install_path", "")
        if not install_path or not _P(install_path).exists():
            return {"success": False, "message": f"Dossier introuvable: {install_path}"}

        root     = _P(install_path)
        app_name = root.name

        # 1. Detection du type principal
        detected = ProcessManager.detect_launch_type(install_path)

        # 2. Scanner TOUTES les possibilites disponibles
        options = []

        # Docker ?
        for dc in ["docker-compose.yml", "docker-compose.yaml", "compose.yml"]:
            if (root / dc).exists():
                options.append({
                    "type": "docker", "label": "Docker Compose",
                    "icon": "\U0001f433", "file": dc,
                    "command": ["docker", "compose", "-f", dc, "up", "-d", "--build"],
                    "recommended": detected["type"] == "docker",
                })
                break

        # Dockerfile seul ?
        if (root / "Dockerfile").exists() and not any(o["type"] == "docker" for o in options):
            options.append({
                "type": "docker_build", "label": "Docker (build manuel)",
                "icon": "\U0001f433", "file": "Dockerfile",
                "command": ["docker", "build", "-t", app_name.lower(), "."],
                "recommended": False,
            })

        # Scripts Python
        venv_py = root / ".venv" / "Scripts" / "python.exe"
        python  = str(venv_py) if venv_py.exists() else "python"
        for script in ["run_api.py", "run.py", "main.py", "app.py", "server.py"]:
            if (root / script).exists():
                # Detecter si FastAPI/uvicorn
                is_fastapi = False
                try:
                    content = (root / script).read_text(encoding="utf-8", errors="replace")
                    is_fastapi = "fastapi" in content.lower() or "uvicorn" in content
                except Exception:
                    pass
                label = ("FastAPI/Uvicorn" if is_fastapi else "Python script")
                stype = ("uvicorn" if is_fastapi else "python")
                options.append({
                    "type": stype, "label": label + " (" + script + ")",
                    "icon": ("\u26a1" if is_fastapi else "\U0001f40d"),
                    "file": script,
                    "command": [python, script],
                    "recommended": detected["type"] in ("uvicorn", "fastapi", "python") and detected.get("info", "").startswith("Script"),
                })

        # start[App].bat existant ?
        bat_name    = "start" + app_name + ".bat"
        bat_path    = root / bat_name
        bat_exists  = bat_path.exists()
        bat_content = ""
        if bat_exists:
            try:
                bat_content = bat_path.read_text(encoding="utf-8", errors="replace")[:500]
            except Exception:
                pass

        # Config files detectes
        config_files = []
        for cf in [".env", "config.yaml", "config.yml", ".env.example", "config.example.yaml"]:
            if (root / cf).exists():
                config_files.append(cf)

        # Requirements
        req_files = [f.name for f in root.glob("requirements*.txt")]

        # Venv present ?
        venv_exists = venv_py.exists()

        return {
            "success":      True,
            "app_name":     app_name,
            "install_path": install_path,
            "detected":     detected,
            "options":      options,
            "bat_exists":   bat_exists,
            "bat_name":     bat_name,
            "bat_path":     str(bat_path) if bat_exists else "",
            "bat_preview":  bat_content,
            "config_files": config_files,
            "req_files":    req_files,
            "venv_exists":  venv_exists,
            "venv_path":    str(venv_py) if venv_exists else "",
        }

    @app.get("/api/store/cards", response_class=HTMLResponse)
    async def store_cards(request: Request):
        """Fragment htmx : liste les cards des apps installées via AppStore."""
        from pathlib import Path as _P
        from fastapi.templating import Jinja2Templates as _Jinja
        apps_status = _get_store().status()
        templates_dir = _P(__file__).parent.parent / "web" / "templates"
        if templates_dir.exists():
            _tmpl = _Jinja(directory=str(templates_dir))
            return _tmpl.TemplateResponse(
                request=request,
                name="store_cards.html",
                context={"apps": apps_status}
            )
        return HTMLResponse("<p style='color:#888;'>Template introuvable.</p>")

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
        github_repo   = body.get("github", "") or ""
        install_path  = body.get("install_path", "") or ""  # C:/code/python/[App]
        app_id        = body.get("app_id") or None
        appdata_files = body.get("appdata_files") or None
        port          = int(body.get("port", 0))
        app_type      = body.get("app_type", "auto")
        command       = body.get("command") or None  # depuis la modal de detection

        from pathlib import Path as _PI

        # ── Cas 1 : dossier local existant (C:/code/python/[App]) ──────────
        # On enregistre directement dans apps.local.json sans git clone
        if install_path and _PI(install_path).exists():
            root = _PI(install_path)
            if not app_id:
                app_id = root.name.lower().replace("-", "_")
            app_name = root.name

            # Generer start[App].bat si absent
            bat_generated = None
            try:
                bat_generated = ProcessManager.generate_start_bat(
                    app_id, install_path, command=command)
                if bat_generated:
                    logger.info("Bat genere: %s", bat_generated)
            except Exception as _be:
                logger.warning("generate_start_bat: %s", _be)

            # Fichiers appdata : seulement DB, .env, config — pas les attachements
            import json as _j, os as _os
            from pathlib import Path as _PP
            _root = _PP(install_path)
            scanned_files = []
            for _pat in ["*.db", "*.sqlite", "*.sqlite3"]:
                for _f in _root.glob(_pat):
                    scanned_files.append(str(_f.relative_to(_root)).replace("\\", "/"))
            for _pat in ["data/*.db", "data/*.sqlite"]:
                for _f in _root.glob(_pat):
                    _rel = str(_f.relative_to(_root)).replace("\\", "/")
                    if _rel not in scanned_files:
                        scanned_files.append(_rel)
            for _name in [".env", "config.yaml", "config.yml", "settings.json"]:
                if (_root / _name).exists():
                    scanned_files.append(_name)

            # Enregistrer dans apps.local.json
            reg_file = _P("apps.local.json")
            try:
                reg = _j.loads(reg_file.read_text(encoding="utf-8")) if reg_file.exists() else {"version":"1.0","apps":{}}
            except Exception:
                reg = {"version":"1.0","apps":{}}

            today        = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
            # AION_DATA_DIR = le dossier de l'app lui-meme (C:/code/python/[App])
            # L'app y trouve ses donnees comme d'habitude
            aion_data_dir = install_path.replace("\\", "/")
            url_val       = f"http://localhost:{port}" if port else ""

            reg.setdefault("apps", {})[app_id] = {
                "name":            app_name,
                "type":            app_type if app_type != "auto" else "fastapi",
                "status":          "installed",
                "github":          github_repo or None,
                "url":             url_val,
                "health_endpoint": "/health",
                "icon":            "package",
                "autostart": {
                    "enabled":      True,
                    "mode":         app_type if app_type != "auto" else "fastapi",
                    "path":         install_path,
                    "command":      command or [],
                    "port":         port,
                    "health_check": False,
                    "env": {
                        "AION_DATA_DIR": aion_data_dir,
                        "AION_APP_ID":   app_id,
                    }
                },
                "store": {
                    "install_path":  install_path,
                    "appdata_path":  install_path,
                    "appdata_files": scanned_files,
                    "github":        github_repo or "",
                    "installed_at":  today,
                    "last_update":   today,
                }
            }
            try:
                reg_file.write_text(_j.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                logger.warning("apps.local.json write: %s", e)

            # Recharger le router
            try:
                aion_app.app_router.reload_apps()
            except Exception:
                pass

            installed_id = app_id
            result = {
                "success":       True,
                "app_id":        app_id,
                "install_path":  install_path,
                "appdata_files": scanned_files,
                "detected_type": app_type,
                "detected_info": f"Dossier local {install_path}",
                "message":       f"'{app_name}' ajout&eacute; depuis {install_path}" +
                                 (f" | {len(scanned_files)} fichier(s) d&eacute;tect&eacute;(s)" if scanned_files else "") +
                                 (f" | {bat_generated.split('/')[-1]} g&eacute;n&eacute;r&eacute;" if bat_generated else ""),
            }

        # ── Cas 2 : git clone depuis GitHub ───────────────────────────────
        elif github_repo:
            result = _get_store().install(github_repo, app_id=app_id,
                                          appdata_files=appdata_files)
            if not result.get("success"):
                return result
            installed_id = result.get("app_id", app_id or github_repo.split("/")[-1].lower())
            install_path = result.get("install_path", "")

        else:
            return JSONResponse({"success": False,
                "message": "Fournis un chemin local (install_path) ou un repo GitHub"},
                status_code=400)

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
            "AION_DATA_DIR":  installed_id,
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


    @app.post("/api/store/{app_id}/import-env")
    async def store_import_env(app_id: str, request: Request):
        """
        Importe un .env ou config.yaml depuis un chemin local vers appdata/.
        Utile pour récupérer le .env de ton répertoire de dev local
        (C:/code/python/[Repo]/.env) apres un git clone.

        Body: {
            "source_path": "C:/code/python/QuickMind/.env",
            "overwrite": true   (default: false — ne remplace que les clés manquantes)
        }
        """
        from pathlib import Path as _P
        from aion_core.store.config_editor import ConfigEditor
        import json as _j, shutil as _sh

        body = await request.json()
        source_path = body.get("source_path", "")
        overwrite   = body.get("overwrite", False)

        if not source_path:
            return {"success": False, "message": "source_path requis"}

        src = _P(source_path)
        if not src.exists():
            return {"success": False,
                    "message": f"Fichier introuvable: {source_path}"}

        # Récupérer appdata_path depuis le registre
        appdata_path = install_path = ""
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    d = _j.loads(rf.read_text(encoding="utf-8"))
                    s = d.get("apps",{}).get(app_id,{}).get("store",{})
                    install_path = s.get("install_path","")
                    appdata_path = s.get("appdata_path","")
                    if appdata_path: break
                except Exception: pass

        if not appdata_path:
            return {"success": False,
                    "message": f"App '{app_id}' non trouvée ou sans appdata configuré"}

        # Copier vers appdata/
        dest_dir = _P(appdata_path)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name

        if dest.exists() and not overwrite:
            # Mode non-écrasant : fusionner les clés manquantes
            try:
                existing_keys = set()
                for line in dest.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.startswith("#"):
                        existing_keys.add(line.split("=")[0].strip())

                new_lines = []
                added = []
                for line in src.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.startswith("#"):
                        key = line.split("=")[0].strip()
                        if key not in existing_keys:
                            new_lines.append(line)
                            added.append(key)

                if new_lines:
                    with open(dest, "a", encoding="utf-8") as f:
                        f.write("\n# Imported from " + str(src) + "\n")
                        f.write("\n".join(new_lines) + "\n")
                    # Synchroniser dans install_path aussi
                    if install_path:
                        _sh.copy2(str(dest), str(_P(install_path) / src.name))
                    return {
                        "success": True,
                        "message": f"{len(added)} clé(s) ajoutée(s) depuis {src.name} : {', '.join(added[:5])}",
                        "added": added,
                        "dest": str(dest),
                    }
                else:
                    return {"success": True,
                            "message": "Aucune nouvelle clé à ajouter (toutes déjà présentes).",
                            "added": []}
            except Exception as e:
                return {"success": False, "message": f"Erreur fusion: {e}"}
        else:
            # Copie directe (overwrite=True ou fichier absent)
            try:
                _sh.copy2(str(src), str(dest))
                # Synchroniser dans install_path aussi
                if install_path:
                    _sh.copy2(str(src), str(_P(install_path) / src.name))
                return {
                    "success": True,
                    "message": f"{src.name} importé dans appdata/{app_id}/ et dans le repo.",
                    "dest": str(dest),
                }
            except Exception as e:
                return {"success": False, "message": f"Erreur copie: {e}"}

    @app.get("/api/store/{app_id}/config-html", response_class=HTMLResponse)
    async def store_get_config_html(app_id: str, request: Request):
        """HTML de la modale config via Jinja2 — pas de generation JS."""
        from pathlib import Path as _P
        from fastapi.templating import Jinja2Templates as _Jinja
        from aion_core.store.config_editor import ConfigEditor
        import json as _j
        install_path = appdata_path = ""
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    d = _j.loads(rf.read_text(encoding="utf-8"))
                    s = d.get("apps",{}).get(app_id,{}).get("store",{})
                    install_path = s.get("install_path","")
                    appdata_path = s.get("appdata_path","")
                    if install_path: break
                except Exception: pass
        tdir = _P(__file__).parent.parent / "web" / "templates"
        T    = _Jinja(directory=str(tdir))
        ctx  = {"app_id": app_id, "files": {}, "has_empty": False, "empty_count": 0, "error": None}
        if not install_path:
            ctx["error"] = f"App {app_id!r} introuvable"
        else:
            try:
                ed   = ConfigEditor(app_id, install_path, appdata_path)
                data = ed.read_all()
                ctx.update({"files": data.get("files",{}), "has_empty": data.get("has_empty",False),
                            "empty_count": data.get("empty_count",0)})
            except Exception as e:
                ctx["error"] = str(e)
        return T.TemplateResponse(request=request, name="config_modal.html", context=ctx)

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
            "AION_DATA_DIR": install_path.replace("\\\\", "/"),
            "AION_APP_ID":   app_id,
        }
        env.update(autostart.get("env", {}))

        pm = ProcessManager()

        # Déterminer la commande de lancement
        cmd          = autostart.get("command", [])
        install_root = _P(install_path)
        explicit_cmd = None

        if cmd:
            exe = _P(cmd[0])
            if exe.exists():
                explicit_cmd = cmd
                logger.info("Start %s: commande configuree %s", app_id, cmd)
            else:
                # Exe du venv manquant → chercher le venv ou utiliser detect_launch_type
                logger.warning("Start %s: exe manquant %s, auto-detection", app_id, cmd[0])
                # Essayer de trouver run_api.py ou main.py avec le venv local
                for venv_py in [
                    install_root / ".venv" / "Scripts" / "python.exe",
                    install_root / "venv"  / "Scripts" / "python.exe",
                ]:
                    if venv_py.exists():
                        for script in ["run_api.py", "main.py", "app.py"]:
                            if (install_root / script).exists():
                                explicit_cmd = [str(venv_py), script]
                                logger.info("Start %s: venv trouve %s", app_id, explicit_cmd)
                                break
                    if explicit_cmd:
                        break

        if not explicit_cmd and not cmd:
            # Pas de commande du tout → auto-detection
            from aion_core.store.process_manager import _detect_launch_command
            detected = _detect_launch_command(install_path)
            if detected:
                explicit_cmd = detected
                logger.info("Start %s: auto-detect %s", app_id, detected)

        if not explicit_cmd:
            return {
                "success": False,
                "message": (
                    f"Impossible de trouver comment lancer {app_id}.\n"
                    f"Repo: {install_path}\n"
                    f"Venv attendu: {install_root / '.venv' / 'Scripts' / 'python.exe'}\n"
                    f"Conseil: reinstalle l'app via /store pour recréer le venv."
                )
            }

        result = pm.start(
            app_id       = app_id,
            install_path = install_path,
            app_type     = autostart.get("mode", "fastapi"),
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



    # ── Docker Manager routes ─────────────────────────────────────

    @app.get("/api/docker/status")
    async def docker_status():
        """Statut de Docker Desktop."""
        from aion_core.store.docker_manager import DockerManager
        return DockerManager.get_docker_status()

    @app.get("/api/docker/containers")
    async def docker_containers():
        """Liste tous les containers (running + stopped)."""
        from aion_core.store.docker_manager import DockerManager
        dm = DockerManager()
        return {"containers": dm.list_containers()}

    @app.post("/api/docker/start/{app_id}")
    async def docker_start(app_id: str, request: Request):
        """Lance un container via docker compose.
        Body: {"install_path": "...", "build": false}
        """
        from pathlib import Path as _P
        from aion_core.store.docker_manager import DockerManager
        import json as _j
        body = {}
        try: body = await request.json()
        except Exception: pass

        # Chercher l'install_path depuis le registre si non fourni
        install_path = body.get("install_path", "")
        if not install_path:
            for rf in [_P("apps.local.json"), _P("apps.json")]:
                if rf.exists():
                    try:
                        d = _j.loads(rf.read_text(encoding="utf-8"))
                        install_path = d.get("apps",{}).get(app_id,{}).get("store",{}).get("install_path","")
                        if install_path: break
                    except Exception: pass

        if not install_path:
            return {"success": False, "message": f"install_path introuvable pour {app_id}"}

        dm = DockerManager()
        return dm.start(app_id, install_path, build=body.get("build", False))

    @app.post("/api/docker/stop/{app_id}")
    async def docker_stop(app_id: str):
        """Stoppe un container."""
        from pathlib import Path as _P
        from aion_core.store.docker_manager import DockerManager
        import json as _j
        install_path = ""
        for rf in [_P("apps.local.json"), _P("apps.json")]:
            if rf.exists():
                try:
                    d = _j.loads(rf.read_text(encoding="utf-8"))
                    install_path = d.get("apps",{}).get(app_id,{}).get("store",{}).get("install_path","")
                    if install_path: break
                except Exception: pass
        dm = DockerManager()
        return dm.stop(app_id, install_path)

    @app.get("/api/docker/running/{app_id}")
    async def docker_is_running(app_id: str):
        """Verifie si un container tourne."""
        from aion_core.store.docker_manager import DockerManager
        dm = DockerManager()
        return {"app_id": app_id, "running": dm.is_running(app_id)}

    @app.get("/api/docker/logs/{app_id}")
    async def docker_logs(app_id: str, lines: int = 50):
        """Retourne les derniers logs d'un container."""
        from aion_core.store.docker_manager import DockerManager
        dm = DockerManager()
        return {"app_id": app_id, "logs": dm.get_logs(app_id, lines)}

    @app.get("/docker", response_class=HTMLResponse)
    async def docker_page(request: Request):
        """Page de gestion Docker."""
        from pathlib import Path as _P
        from fastapi.templating import Jinja2Templates as _Jinja
        tdir = _P(__file__).parent.parent / "web" / "templates"
        T    = _Jinja(directory=str(tdir))
        return T.TemplateResponse(request=request, name="docker.html", context={})

    @app.get("/store", response_class=HTMLResponse)
    async def store_page(request: Request):
        """Page App Store — utilise le template store.html + htmx pour les cards."""
        from pathlib import Path as _P
        from fastapi.templating import Jinja2Templates as _Jinja
        templates_dir = _P(__file__).parent.parent / "web" / "templates"
        if templates_dir.exists():
            _tmpl = _Jinja(directory=str(templates_dir))
            return _tmpl.TemplateResponse(request=request, name="store.html", context={})
        return HTMLResponse("<h1>App Store</h1><p>Template store.html introuvable.</p>")