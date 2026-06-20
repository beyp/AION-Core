"""
QuickMind Web Routes -- AION-Core Phase 2.
Routes FastAPI pour QuickMind (remplace Tkinter).
"""
import logging
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

PRIORITY_META = {
    "urgent": {"label": "Urgent",  "color": "#FF4444", "icon": "R"},
    "high":   {"label": "High",    "color": "#FF8C00", "icon": "O"},
    "normal": {"label": "Normal",  "color": "#1E90FF", "icon": "B"},
    "low":    {"label": "Low",     "color": "#888888", "icon": "L"},
}

STATUS_META = {
    "todo":        {"label": "A faire",  "color": "#888888", "icon": "?"},
    "in_progress": {"label": "En cours", "color": "#FF8C00", "icon": ">"},
    "done":        {"label": "Termine",  "color": "#32CD32", "icon": "V"},
}


def register_routes(app, aion_app):
    """Enregistre les routes QuickMind dans l app FastAPI."""
    from pathlib import Path
    from fastapi.templating import Jinja2Templates

    templates_dir = Path(__file__).parent.parent / "web" / "templates"
    templates = None
    if templates_dir.exists():
        templates = Jinja2Templates(directory=str(templates_dir))

    qm = aion_app.app_router._apps.get("quickmind")

    @app.get("/app/quickmind", response_class=HTMLResponse)
    async def qm_home(request,
                      priority: str = "", status: str = "", category: str = ""):
        filters = {}
        if priority: filters["priority"] = priority
        if status:   filters["status"]   = status

        tasks      = qm.get_tasks(filters) if qm else []
        categories = qm._fetch_categories() if qm else []
        available  = qm.is_available() if qm else False

        if templates:
            return templates.TemplateResponse(
                request=request,
                name="quickmind.html",
                context={
                    "version":         aion_app.VERSION,
                    "active":          "quickmind",
                    "ai_available":    aion_app.brain.is_available(),
                    "tasks":           tasks,
                    "categories":      categories,
                    "qm_online":       available,
                    "filters":         filters,
                    "total":           len(tasks),
                    "priority_filter": priority,
                    "status_filter":   status,
                }
            )
        return HTMLResponse(_qm_fallback(tasks, available))

    @app.get("/qm/tasks", response_class=HTMLResponse)
    async def qm_tasks_fragment(request,
                                 priority: str = "", status: str = ""):
        filters = {}
        if priority: filters["priority"] = priority
        if status:   filters["status"]   = status
        tasks = qm.get_tasks(filters) if qm else []
        return HTMLResponse(_render_task_list(tasks))

    @app.post("/qm/task/add", response_class=HTMLResponse)
    async def qm_add_task(request):
        from fastapi import Form
        body = await request.form()
        title    = body.get("title", "")
        priority = body.get("priority", "normal")
        category = body.get("category", "")
        if not title:
            return HTMLResponse('<div style="color:var(--red);">Titre requis</div>')
        if qm:
            qm.add_task({"title": title, "priority": priority,
                          "category": category or None})
        tasks = qm.get_tasks() if qm else []
        return HTMLResponse(_render_task_list(tasks))

    @app.post("/qm/task/{task_id}/done", response_class=HTMLResponse)
    async def qm_done_task(task_id: int):
        if qm: qm.mark_done({"task_id": task_id})
        tasks = qm.get_tasks() if qm else []
        return HTMLResponse(_render_task_list(tasks))

    @app.delete("/qm/task/{task_id}", response_class=HTMLResponse)
    async def qm_delete_task(task_id: int):
        if qm: qm.delete_task({"task_id": task_id})
        tasks = qm.get_tasks() if qm else []
        return HTMLResponse(_render_task_list(tasks))

    @app.get("/qm/task/{task_id}/detail", response_class=HTMLResponse)
    async def qm_task_detail(task_id: int):
        if not qm:
            return HTMLResponse("<p>QuickMind hors ligne</p>")
        try:
            import requests as _r, os
            base = os.getenv("QUICKMIND_URL", "http://localhost:8765")
            t  = _r.get(base + "/task/" + str(task_id), timeout=5).json()
            st = _r.get(base + "/task/" + str(task_id) + "/subtasks", timeout=5).json()
        except Exception:
            return HTMLResponse("<p>Erreur chargement</p>")
        return HTMLResponse(_render_task_detail(t, st))

    @app.post("/qm/task/{task_id}/subtask", response_class=HTMLResponse)
    async def qm_add_subtask(task_id: int, request):
        body  = await request.form()
        title = body.get("title", "")
        if qm and title:
            qm.add_subtask(task_id, title)
        try:
            import requests as _r, os
            base = os.getenv("QUICKMIND_URL", "http://localhost:8765")
            t  = _r.get(base + "/task/" + str(task_id), timeout=5).json()
            st = _r.get(base + "/task/" + str(task_id) + "/subtasks", timeout=5).json()
        except Exception:
            return HTMLResponse("")
        return HTMLResponse(_render_task_detail(t, st))

    @app.post("/qm/task/{task_id}/subtask/{subtask_id}/toggle", response_class=HTMLResponse)
    async def qm_toggle_subtask(task_id: int, subtask_id: int):
        if qm: qm.toggle_subtask(task_id, subtask_id)
        try:
            import requests as _r, os
            base = os.getenv("QUICKMIND_URL", "http://localhost:8765")
            t  = _r.get(base + "/task/" + str(task_id), timeout=5).json()
            st = _r.get(base + "/task/" + str(task_id) + "/subtasks", timeout=5).json()
        except Exception:
            return HTMLResponse("")
        return HTMLResponse(_render_task_detail(t, st))

    logger.info("QuickMind routes registered")


# -- Helpers HTML (sans f-strings imbriquees ni line continuation) -------------

def _render_task_list(tasks: list) -> str:
    """Genere le HTML de la liste des taches."""
    if not tasks:
        return '<div style="color:var(--dim);text-align:center;padding:30px;">Aucune tache.</div>'

    rows = []
    for t in tasks:
        pm   = PRIORITY_META.get(t.get("priority", "normal"), PRIORITY_META["normal"])
        sm   = STATUS_META.get(t.get("status", "todo"), STATUS_META["todo"])
        done = t.get("status") == "done"
        tid  = str(t.get("id", 0))
        title = t.get("title", "")
        cat   = t.get("category") or ""

        done_css = "text-decoration:line-through;color:#888;" if done else ""
        cat_html = ('<span class="task-cat">' + cat + "</span>") if cat else ""

        row = (
            '<div class="task-row' + (" done" if done else "") + '" id="task-' + tid + '">'
            + '<span class="task-prio" style="color:' + pm["color"] + ';">'
            + pm["icon"] + "</span>"
            + '<div class="task-body"'
            + ' hx-get="/qm/task/' + tid + '/detail"'
            + ' hx-target="#task-detail" hx-swap="innerHTML" style="cursor:pointer;">'
            + '<span class="task-title" style="' + done_css + '">' + title + "</span>"
            + cat_html
            + "</div>"
            + '<span class="task-status" style="color:' + sm["color"] + ';">'
            + sm["icon"] + "</span>"
            + '<div class="task-actions">'
            + '<button hx-post="/qm/task/' + tid + '/done"'
            + ' hx-target="#task-list" hx-swap="innerHTML" title="Done">V</button>'
            + '<button hx-delete="/qm/task/' + tid + '"'
            + ' hx-target="#task-list" hx-swap="innerHTML"'
            + ' hx-confirm="Supprimer ?" title="Supprimer">X</button>'
            + "</div></div>"
        )
        rows.append(row)

    return chr(10).join(rows)


def _render_task_detail(task: dict, subtasks: list) -> str:
    """Genere le HTML du detail d une tache."""
    pm  = PRIORITY_META.get(task.get("priority", "normal"), PRIORITY_META["normal"])
    sm  = STATUS_META.get(task.get("status", "todo"), STATUS_META["todo"])
    tid = str(task.get("id", 0))

    # Sous-taches
    st_rows = []
    for st in subtasks:
        checked  = "checked" if st.get("done") else ""
        st_css   = "text-decoration:line-through;color:#888;" if st.get("done") else ""
        st_rows.append(
            '<div class="subtask-row">'
            + '<input type="checkbox" ' + checked
            + ' hx-post="/qm/task/' + tid + '/subtask/' + str(st.get("id", 0)) + '/toggle"'
            + ' hx-target="#detail-' + tid + '" hx-swap="innerHTML">'
            + '<span style="' + st_css + '">' + st.get("title", "") + "</span>"
            + "</div>"
        )
    st_html = chr(10).join(st_rows)

    # Progression
    progress = 0
    if subtasks:
        done_count = sum(1 for s in subtasks if s.get("done"))
        progress   = int(done_count / len(subtasks) * 100)

    desc    = task.get("description") or ""
    desc_html = (
        '<p style="color:var(--dim);font-size:0.85rem;margin-bottom:12px;">'
        + desc + "</p>"
    ) if desc else ""

    prog_html = ""
    if subtasks:
        prog_html = (
            '<div style="margin-bottom:12px;">'
            '<div style="font-size:0.72rem;color:var(--dim);margin-bottom:4px;">'
            "Progression " + str(progress) + "%</div>"
            '<div style="background:var(--border);border-radius:4px;height:6px;">'
            '<div style="background:var(--green);width:' + str(progress) + "%;height:100%;"
            + 'border-radius:4px;transition:width 0.3s;"></div></div></div>'
        )

    return (
        '<div id="detail-' + tid + '">'
        + '<h3 style="color:var(--accent);margin-bottom:12px;">'
        + pm["icon"] + " #" + tid + " " + task.get("title", "") + "</h3>"
        + '<div style="display:flex;gap:10px;margin-bottom:12px;">'
        + '<span style="background:' + pm["color"] + '22;color:' + pm["color"]
        + ';padding:3px 10px;border-radius:10px;font-size:0.78rem;">'
        + pm["label"] + "</span>"
        + '<span style="background:' + sm["color"] + '22;color:' + sm["color"]
        + ';padding:3px 10px;border-radius:10px;font-size:0.78rem;">'
        + sm["label"] + "</span>"
        + "</div>"
        + desc_html
        + prog_html
        + '<div class="subtasks-list">' + st_html + "</div>"
        + '<form hx-post="/qm/task/' + tid + '/subtask"'
        + ' hx-target="#detail-' + tid + '" hx-swap="innerHTML"'
        + ' style="display:flex;gap:6px;margin-top:10px;">'
        + '<input name="title" type="text" placeholder="Ajouter une sous-tache..."'
        + ' style="flex:1;background:#12141f;border:1px solid var(--border);'
        + 'color:var(--text);padding:5px 8px;border-radius:5px;font-size:0.8rem;">'
        + '<button type="submit" style="background:var(--accent);color:white;'
        + 'border:none;padding:5px 12px;border-radius:5px;cursor:pointer;">+</button>'
        + "</form></div>"
    )


def _qm_fallback(tasks: list, available: bool) -> str:
    """Page fallback quand les templates ne sont pas disponibles."""
    status_color = "#4caf50" if available else "#f44336"
    status_text  = "En ligne" if available else "Hors ligne"
    tasks_html   = _render_task_list(tasks)
    return (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        "<script src='https://unpkg.com/htmx.org@1.9.12'></script>"
        "<style>"
        "body{font-family:Segoe UI;background:#0f1117;color:#e0e0e0;padding:0;margin:0;}"
        ".header{background:#151821;border-bottom:2px solid #1e90ff;padding:14px 20px;"
        "display:flex;align-items:center;gap:12px;}"
        "h1{color:#1e90ff;margin:0;font-size:1.1rem;}"
        ".main{padding:20px;}"
        ".task-row{display:flex;align-items:center;gap:10px;background:#1a1d27;"
        "border-radius:8px;padding:10px 14px;margin-bottom:6px;border:1px solid #2a2d3e;}"
        ".task-row.done{opacity:0.55;}"
        ".task-body{flex:1;cursor:pointer;}"
        ".task-cat{display:inline-block;background:#1e90ff22;color:#1e90ff;"
        "padding:1px 7px;border-radius:8px;font-size:0.7rem;margin-left:8px;}"
        ".task-actions{display:flex;gap:4px;}"
        ".task-actions button{background:none;border:none;cursor:pointer;font-size:0.85rem;}"
        "</style></head><body>"
        "<div class='header'>"
        "<span style='font-size:1.3rem;'>V</span>"
        "<h1>QuickMind</h1>"
        "<span style='color:" + status_color + ";font-size:0.78rem;margin-left:8px;'>"
        + status_text + "</span>"
        "<a href='/' style='margin-left:auto;color:#888;text-decoration:none;font-size:0.82rem;'>"
        "&larr; AION</a>"
        "</div>"
        "<div class='main'>"
        "<div id='task-list'>" + tasks_html + "</div>"
        "</div></body></html>"
    )
