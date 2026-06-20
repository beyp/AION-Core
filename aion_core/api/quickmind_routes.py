"""
QuickMind Web Routes — AION-Core Phase 2.
Interface web complète pour QuickMind (remplace Tkinter).
"""
import logging
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/qm", tags=["QuickMind"])


def register_routes(app, aion_app):
    """Enregistre les routes QuickMind dans l app FastAPI."""
    from fastapi.templating import Jinja2Templates
    from pathlib import Path

    templates_dir = Path(__file__).parent.parent / "web" / "templates"
    templates = None
    if templates_dir.exists():
        templates = Jinja2Templates(directory=str(templates_dir))

    qm = aion_app.app_router._apps.get("quickmind")

    # ── Page principale QuickMind ────────────────────────────────────────────

    @app.get("/app/quickmind", response_class=HTMLResponse)
    async def qm_home(request: Request,
                      priority: str = "", status: str = "", category: str = ""):
        filters = {}
        if priority: filters["priority"] = priority
        if status:   filters["status"]   = status
        if category: filters["category"] = category

        tasks      = qm.get_tasks(filters) if qm else []
        categories = qm._fetch_categories() if qm else []
        available  = qm.is_available() if qm else False

        if templates:
            return templates.TemplateResponse(
                request=request,
                name="quickmind.html",
                context={
                    "version":    aion_app.VERSION,
                    "active":     "quickmind",
                    "ai_available": aion_app.brain.is_available(),
                    "tasks":      tasks,
                    "categories": categories,
                    "qm_online":  available,
                    "filters":    filters,
                    "total":      len(tasks),
                    "priority_filter": priority,
                    "status_filter":   status,
                }
            )
        # Fallback sans templates
        return HTMLResponse(_qm_fallback_html(tasks, available))

    # ── HTMX fragments ───────────────────────────────────────────────────────

    @app.get("/qm/tasks", response_class=HTMLResponse)
    async def qm_tasks_fragment(request: Request,
                                 priority: str = "", status: str = ""):
        """Fragment htmx — liste des tâches."""
        filters = {}
        if priority: filters["priority"] = priority
        if status:   filters["status"]   = status
        tasks = qm.get_tasks(filters) if qm else []
        return HTMLResponse(_render_task_list(tasks))

    @app.post("/qm/task/add", response_class=HTMLResponse)
    async def qm_add_task(
        title:       str = Form(...),
        priority:    str = Form("normal"),
        category:    str = Form(""),
        description: str = Form(""),
        status:      str = Form("todo"),
    ):
        """Ajouter une tâche via formulaire htmx."""
        if not qm:
            return HTMLResponse('<div style="color:var(--red);">QuickMind hors ligne</div>')
        result = qm.add_task({
            "title": title, "priority": priority,
            "category": category or None, "description": description, "status": status
        })
        tasks = qm.get_tasks()
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
        """Détail d une tâche avec sous-tâches."""
        if not qm:
            return HTMLResponse('<p>QuickMind hors ligne</p>')
        try:
            import requests as _r
            import os
            base = os.getenv("QUICKMIND_URL", "http://localhost:8765")
            t  = _r.get(f"{base}/task/{task_id}", timeout=5).json()
            st = _r.get(f"{base}/task/{task_id}/subtasks", timeout=5).json()
        except Exception:
            return HTMLResponse('<p style="color:var(--red);">Erreur chargement</p>')
        return HTMLResponse(_render_task_detail(t, st))

    @app.post("/qm/task/{task_id}/subtask", response_class=HTMLResponse)
    async def qm_add_subtask(task_id: int, title: str = Form(...)):
        if qm: qm.add_subtask(task_id, title)
        try:
            import requests as _r, os
            base = os.getenv("QUICKMIND_URL", "http://localhost:8765")
            t  = _r.get(f"{base}/task/{task_id}", timeout=5).json()
            st = _r.get(f"{base}/task/{task_id}/subtasks", timeout=5).json()
        except Exception:
            return HTMLResponse("")
        return HTMLResponse(_render_task_detail(t, st))

    @app.post("/qm/task/{task_id}/subtask/{subtask_id}/toggle", response_class=HTMLResponse)
    async def qm_toggle_subtask(task_id: int, subtask_id: int):
        if qm: qm.toggle_subtask(task_id, subtask_id)
        try:
            import requests as _r, os
            base = os.getenv("QUICKMIND_URL", "http://localhost:8765")
            t  = _r.get(f"{base}/task/{task_id}", timeout=5).json()
            st = _r.get(f"{base}/task/{task_id}/subtasks", timeout=5).json()
        except Exception:
            return HTMLResponse("")
        return HTMLResponse(_render_task_detail(t, st))

    logger.info("QuickMind routes registered")


# ══ Helpers HTML ══════════════════════════════════════════════════════════════

PRIORITY_META = {
    "urgent": {"color": "#FF4444", "icon": "🔴", "label": "Urgent"},
    "high":   {"color": "#FF8C00", "icon": "🟠", "label": "High"},
    "normal": {"color": "#1E90FF", "icon": "🔵", "label": "Normal"},
    "low":    {"color": "#888888", "icon": "⚪", "label": "Low"},
}
STATUS_META = {
    "todo":        {"color": "#888", "icon": "📋", "label": "À faire"},
    "in_progress": {"color": "#FF8C00", "icon": "⚙️", "label": "En cours"},
    "done":        {"color": "#32CD32", "icon": "✅", "label": "Terminé"},
}


def _render_task_list(tasks: list) -> str:
    if not tasks:
        return '<div style="color:var(--dim);text-align:center;padding:30px;">Aucune tâche.</div>'
    rows = []
    for t in tasks:
        pm   = PRIORITY_META.get(t.get("priority","normal"), PRIORITY_META["normal"])
        sm   = STATUS_META.get(t.get("status","todo"), STATUS_META["todo"])
        done = t.get("status") == "done"
        rows.append(
            f'<div class="task-row {\'done\' if done else \'\'}" id="task-{t[\'id\']}">' +
            f'<span class="task-prio" style="color:{pm[\'color\']};">{pm[\'icon\']}</span>' +
            f'<div class="task-body" hx-get="/qm/task/{t[\'id\']}/detail" hx-target="#task-detail" hx-swap="innerHTML" style="cursor:pointer;">' +
            f'<span class="task-title {\'done-title\' if done else \'\'}">{t[\'title\']}</span>' +
            (f'<span class="task-cat">{t[\'category\']}</span>' if t.get("category") else "") +
            f'</div>' +
            f'<span class="task-status" style="color:{sm[\'color\']};">{sm[\'icon\']}</span>' +
            f'<div class="task-actions">' +
            f'<button hx-post="/qm/task/{t[\'id\']}/done" hx-target="#task-list" hx-swap="innerHTML" title="Done">✅</button>' +
            f'<button hx-delete="/qm/task/{t[\'id\']}" hx-target="#task-list" hx-swap="innerHTML" hx-confirm="Supprimer ?" title="Supprimer">🗑️</button>' +
            f'</div></div>'
        )
    return "\n".join(rows)


def _render_task_detail(task: dict, subtasks: list) -> str:
    pm  = PRIORITY_META.get(task.get("priority","normal"), PRIORITY_META["normal"])
    sm  = STATUS_META.get(task.get("status","todo"), STATUS_META["todo"])
    tid = task.get("id")
    st_html = ""
    for st in subtasks:
        checked = "checked" if st.get("done") else ""
        st_html += (
            f'<div class="subtask-row">' +
            f'<input type="checkbox" {checked}' +
            f' hx-post="/qm/task/{tid}/subtask/{st[\'id\']}/toggle"' +
            f' hx-target="#detail-{tid}" hx-swap="innerHTML">' +
            f'<span style="{\'text-decoration:line-through;color:#888;\' if st.get(\'done\') else \'\'}">{st[\'title\']}</span>' +
            f'</div>'
        )
    progress = 0
    if subtasks:
        done_count = sum(1 for s in subtasks if s.get("done"))
        progress   = int(done_count / len(subtasks) * 100)
    return (
        f'<div id="detail-{tid}">' +
        f'<h3 style="color:var(--accent);margin-bottom:12px;">{pm[\'icon\\']} #{tid} {task[\'title\']}</h3>' +
        f'<div style="display:flex;gap:10px;margin-bottom:12px;">' +
        f'<span style="background:{pm[\'color\']}22;color:{pm[\'color\']};padding:3px 10px;border-radius:10px;font-size:0.78rem;">{pm[\'label\']}</span>' +
        f'<span style="background:{sm[\'color\']}22;color:{sm[\'color\']};padding:3px 10px;border-radius:10px;font-size:0.78rem;">{sm[\'label\']}</span>' +
        (f'<span style="color:var(--dim);font-size:0.78rem;">{task[\'category\']}</span>' if task.get("category") else "") +
        f'</div>' +
        (f'<p style="color:var(--dim);font-size:0.85rem;margin-bottom:12px;">{task["description"]}</p>' if task.get("description") else "") +
        (f'<div style="margin-bottom:12px;">' +
         f'<div style="font-size:0.72rem;color:var(--dim);margin-bottom:4px;">Progression {progress}%</div>' +
         f'<div style="background:var(--border);border-radius:4px;height:6px;">' +
         f'<div style="background:var(--green);width:{progress}%;height:100%;border-radius:4px;transition:width 0.3s;"></div></div>' +
         f'</div>' if subtasks else "") +
        f'<div class="subtasks-list">{st_html}</div>' +
        f'<form hx-post="/qm/task/{tid}/subtask" hx-target="#detail-{tid}" hx-swap="innerHTML" style="display:flex;gap:6px;margin-top:10px;">' +
        f'<input name="title" type="text" placeholder="Ajouter une sous-tâche..." style="flex:1;background:#12141f;border:1px solid var(--border);color:var(--text);padding:5px 8px;border-radius:5px;font-size:0.8rem;">' +
        f'<button type="submit" style="background:var(--accent);color:white;border:none;padding:5px 12px;border-radius:5px;cursor:pointer;">+</button>' +
        f'</form></div>'
    )


def _qm_fallback_html(tasks: list, available: bool) -> str:
    status_color = "#4caf50" if available else "#f44336"
    status_text  = "En ligne" if available else "Hors ligne"
    tasks_html = _render_task_list(tasks)
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
    <style>body{{font-family:Segoe UI;background:#0f1117;color:#e0e0e0;padding:0;margin:0;}}
    .header{{background:#151821;border-bottom:2px solid #1e90ff;padding:14px 20px;
      display:flex;align-items:center;gap:12px;}}
    h1{{color:#1e90ff;margin:0;font-size:1.1rem;}}
    .main{{padding:20px;}}
    .task-row{{display:flex;align-items:center;gap:10px;background:#1a1d27;
      border-radius:8px;padding:10px 14px;margin-bottom:6px;border:1px solid #2a2d3e;}}
    .task-row.done{{opacity:0.6;}}
    .task-body{{flex:1;cursor:pointer;}}
    .task-title{{font-size:0.88rem;}}
    .done-title{{text-decoration:line-through;color:#888;}}
    .task-cat{{display:inline-block;background:#1e90ff22;color:#1e90ff;
      padding:1px 7px;border-radius:8px;font-size:0.72rem;margin-left:8px;}}
    .task-actions{{display:flex;gap:6px;}}
    .task-actions button{{background:none;border:none;cursor:pointer;font-size:1rem;}}
    </style>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    </head><body>
    <div class="header">
      <span style="font-size:1.3rem;">✅</span>
      <h1>QuickMind</h1>
      <span style="color:{status_color};font-size:0.78rem;margin-left:8px;">● {status_text}</span>
      <a href="/" style="margin-left:auto;color:#888;text-decoration:none;font-size:0.82rem;">← AION</a>
    </div>
    <div class="main">
      <div id="task-list">{tasks_html}</div>
    </div></body></html>"""
