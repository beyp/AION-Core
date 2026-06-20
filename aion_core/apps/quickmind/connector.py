"""
QuickMind Connector — Interface complète avec l API QuickMind.
Toutes les fonctionnalités de l app Tkinter, accessibles via API.
"""
import logging
import os
from typing import Any

import requests as _req

logger = logging.getLogger(__name__)

QM_URL = os.getenv("QUICKMIND_URL", "http://localhost:8765")

PRIORITY_META = {
    "urgent": {"label": "Urgent",  "color": "#FF4444", "icon": "🔴"},
    "high":   {"label": "High",    "color": "#FF8C00", "icon": "🟠"},
    "normal": {"label": "Normal",  "color": "#1E90FF", "icon": "🔵"},
    "low":    {"label": "Low",     "color": "#888888", "icon": "⚪"},
}

STATUS_META = {
    "todo":        {"label": "À faire",   "color": "#888888", "icon": "📋"},
    "in_progress": {"label": "En cours",  "color": "#FF8C00", "icon": "⚙️"},
    "done":        {"label": "Terminé",   "color": "#32CD32", "icon": "✅"},
}


class QuickMindConnector:
    """Connecteur QuickMind complet — toutes les fonctionnalités."""

    def __init__(self, memory=None) -> None:
        self.memory   = memory
        self.base_url = (memory.recall("quickmind_url") if memory else None) or QM_URL

    def execute(self, action: str, params: dict) -> str:
        actions = {
            "add_task":    self.add_task,
            "list_tasks":  self.list_tasks,
            "get_task":    self.get_task,
            "update_task": self.update_task,
            "done":        self.mark_done,
            "delete":      self.delete_task,
            "search":      lambda p: self.search(p.get("keyword", "")),
            "health":      self.health,
            "categories":  self.get_categories,
            "archived":    self.get_archived,
        }
        fn = actions.get(action, self.list_tasks)
        return fn(params)

    # ── Tasks ──────────────────────────────────────────────────────────────────

    def get_tasks(self, filters: dict | None = None) -> list[dict]:
        """Retourne la liste des tâches (dict Python)."""
        try:
            r = _req.get(f"{self.base_url}/tasks", timeout=5)
            r.raise_for_status()
            tasks = r.json()
            if filters:
                priority = filters.get("priority")
                status   = filters.get("status")
                cat      = filters.get("category")
                if priority: tasks = [t for t in tasks if t.get("priority") == priority]
                if status:   tasks = [t for t in tasks if t.get("status")   == status]
                if cat:      tasks = [t for t in tasks if t.get("category") == cat]
            return tasks
        except Exception as e:
            logger.error("QM get_tasks: %s", e)
            return []

    def list_tasks(self, params: dict | None = None) -> str:
        tasks = self.get_tasks(params)
        if not tasks:
            return "Aucune tâche dans QuickMind."
        lines = [f"QuickMind — {len(tasks)} tâche(s) :"]
        for t in tasks[:15]:
            pm = PRIORITY_META.get(t.get("priority","normal"), {})
            sm = STATUS_META.get(t.get("status","todo"), {})
            lines.append(
                f"  {pm.get('icon','🔵')} #{t['id']} {t['title'][:40]} "
                f"[{sm.get('label','?')}]"
            )
        return "\n".join(lines)

    def get_task(self, params: dict) -> str:
        task_id = params.get("task_id") or params.get("id")
        if not task_id:
            return "ID manquant."
        try:
            r = _req.get(f"{self.base_url}/task/{task_id}", timeout=5)
            r.raise_for_status()
            t  = r.json()
            pm = PRIORITY_META.get(t.get("priority","normal"), {})
            sm = STATUS_META.get(t.get("status","todo"), {})
            result = (
                f"Tâche #{t['id']}\n"
                f"  Titre      : {t['title']}\n"
                f"  Priorité   : {pm.get('label','')} {pm.get('icon','')}\n"
                f"  Statut     : {sm.get('label','')} {sm.get('icon','')}\n"
            )
            if t.get("description"):
                result += f"  Description: {t['description'][:100]}\n"
            if t.get("category"):
                result += f"  Catégorie  : {t['category']}\n"
            if t.get("reminder_at"):
                result += f"  Rappel     : {t['reminder_at']}\n"
            return result
        except Exception as e:
            return f"Erreur : {e}"

    def add_task(self, params: dict) -> str:
        try:
            r = _req.post(f"{self.base_url}/task", json={
                "title":       params.get("title", ""),
                "description": params.get("description", ""),
                "priority":    params.get("priority", "normal"),
                "category":    params.get("category"),
                "status":      params.get("status", "todo"),
            }, timeout=5)
            r.raise_for_status()
            data = r.json()
            return f"✅ Tâche #{data.get('id','?')} créée : {params.get('title','')}"
        except Exception as e:
            return f"QuickMind indisponible : {e}"

    def update_task(self, params: dict) -> str:
        task_id = params.pop("task_id", None) or params.pop("id", None)
        if not task_id:
            return "ID manquant."
        try:
            r = _req.put(f"{self.base_url}/task/{task_id}", json=params, timeout=5)
            r.raise_for_status()
            return f"✅ Tâche #{task_id} mise à jour."
        except Exception as e:
            return f"Erreur : {e}"

    def mark_done(self, params: dict) -> str:
        task_id = params.get("task_id") or params.get("id")
        if not task_id:
            return "ID manquant."
        try:
            r = _req.post(f"{self.base_url}/task/{task_id}/done", timeout=5)
            r.raise_for_status()
            return f"✅ Tâche #{task_id} marquée Done."
        except Exception as e:
            return f"Erreur : {e}"

    def delete_task(self, params: dict) -> str:
        task_id = params.get("task_id") or params.get("id")
        if not task_id:
            return "ID manquant."
        try:
            r = _req.delete(f"{self.base_url}/task/{task_id}", timeout=5)
            r.raise_for_status()
            return f"🗑️ Tâche #{task_id} supprimée."
        except Exception as e:
            return f"Erreur : {e}"

    # ── Subtasks ───────────────────────────────────────────────────────────────

    def get_subtasks(self, task_id: int) -> list[dict]:
        try:
            r = _req.get(f"{self.base_url}/task/{task_id}/subtasks", timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception:
            return []

    def add_subtask(self, task_id: int, title: str) -> dict:
        try:
            r = _req.post(f"{self.base_url}/task/{task_id}/subtask",
                          json={"title": title}, timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception:
            return {}

    def toggle_subtask(self, task_id: int, subtask_id: int) -> dict:
        try:
            r = _req.post(f"{self.base_url}/task/{task_id}/subtask/{subtask_id}/toggle",
                          timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception:
            return {}

    # ── Categories ─────────────────────────────────────────────────────────────

    def get_categories(self, params: dict | None = None) -> str:
        cats = self._fetch_categories()
        if not cats:
            return "Aucune catégorie."
        return "Catégories : " + ", ".join(f"{c['name']}" for c in cats)

    def _fetch_categories(self) -> list[dict]:
        try:
            r = _req.get(f"{self.base_url}/categories", timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception:
            return []

    # ── Archives ───────────────────────────────────────────────────────────────

    def get_archived(self, params: dict | None = None) -> str:
        try:
            r = _req.get(f"{self.base_url}/tasks?archived=true", timeout=5)
            if r.status_code == 200:
                tasks = r.json()
                return f"{len(tasks)} tâche(s) archivée(s)."
        except Exception:
            pass
        return "Archives non disponibles."

    # ── Search ─────────────────────────────────────────────────────────────────

    def search(self, keyword: str) -> str:
        tasks = self.get_tasks()
        kw    = keyword.lower()
        found = [t for t in tasks
                 if kw in (t.get("title","") or "").lower()
                 or kw in (t.get("description","") or "").lower()]
        if not found:
            return ""
        return (f"{len(found)} tâche(s) QM pour '{keyword}' : " +
                ", ".join(f"#{t['id']} {t['title'][:25]}" for t in found[:3]))

    # ── Health ─────────────────────────────────────────────────────────────────

    def health(self, params: dict | None = None) -> str:
        try:
            r = _req.get(f"{self.base_url}/health", timeout=3)
            return "QuickMind actif ✅" if r.status_code == 200 else "QuickMind hors ligne ❌"
        except Exception:
            return "QuickMind hors ligne ❌"

    def is_available(self) -> bool:
        try:
            return _req.get(f"{self.base_url}/health", timeout=2).status_code == 200
        except Exception:
            return False
