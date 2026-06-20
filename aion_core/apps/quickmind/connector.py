"""QuickMind Connector — Interface avec l API QuickMind."""
import logging
import os
import requests as _req

logger = logging.getLogger(__name__)

QM_URL = os.getenv("QUICKMIND_URL", "http://localhost:8765")


class QuickMindConnector:
    """Connecteur QuickMind — toutes les actions tâches."""

    def __init__(self, memory) -> None:
        self.memory  = memory
        self.base_url = self.memory.recall("quickmind_url") or QM_URL

    def execute(self, action: str, params: dict) -> str:
        actions = {
            "add_task":    self.add_task,
            "list_tasks":  self.list_tasks,
            "done":        self.mark_done,
            "search":      self.search,
            "health":      self.health,
        }
        fn = actions.get(action, self.list_tasks)
        return fn(params)

    def add_task(self, params: dict) -> str:
        try:
            r = _req.post(f"{self.base_url}/task", json=params, timeout=5)
            r.raise_for_status()
            data = r.json()
            return f"Tache #{data.get('id','?')} creee : {params.get('title','')}"
        except Exception as e:
            return f"QuickMind indisponible : {e}"

    def list_tasks(self, params: dict = None) -> str:
        try:
            r = _req.get(f"{self.base_url}/tasks", timeout=5)
            r.raise_for_status()
            tasks = r.json()
            if not tasks:
                return "Aucune tache dans QuickMind."
            lines = [f"  [{t.get('priority','normal').upper()[:1]}] #{t['id']} {t['title'][:40]}"
                     for t in tasks[:10]]
            return f"QuickMind ({len(tasks)} taches) :\n" + "\n".join(lines)
        except Exception as e:
            return f"QuickMind indisponible : {e}"

    def mark_done(self, params: dict) -> str:
        task_id = params.get("task_id") or params.get("id")
        if not task_id:
            return "ID de tache manquant."
        try:
            r = _req.post(f"{self.base_url}/task/{task_id}/done", timeout=5)
            r.raise_for_status()
            return f"Tache #{task_id} marquee Done."
        except Exception as e:
            return f"Erreur : {e}"

    def search(self, keyword: str) -> str:
        try:
            r = _req.get(f"{self.base_url}/tasks", timeout=5)
            r.raise_for_status()
            tasks = r.json()
            kw    = keyword.lower()
            found = [t for t in tasks
                     if kw in (t.get("title","") or "").lower()
                     or kw in (t.get("description","") or "").lower()]
            if not found:
                return ""
            return f"{len(found)} tache(s) QM : " + ", ".join(
                f"#{t['id']} {t['title'][:30]}" for t in found[:3])
        except Exception:
            return ""

    def health(self, params: dict = None) -> str:
        try:
            r = _req.get(f"{self.base_url}/health", timeout=3)
            return "QuickMind actif." if r.status_code == 200 else "QuickMind hors ligne."
        except Exception:
            return "QuickMind hors ligne."
