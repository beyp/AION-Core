"""ADO Connector — Interface Azure DevOps."""
import base64
import logging
import os
import requests as _req

logger = logging.getLogger(__name__)


class ADOConnector:
    """Connecteur Azure DevOps."""

    ORG = "Premiertech"
    BASE_URL = f"https://dev.azure.com/{ORG}"
    DEFAULT_PROJECT = "PTG - TMM D2"

    def __init__(self, memory) -> None:
        self.memory      = memory
        self._pat        = None
        self._project    = memory.recall("ado_project") or self.DEFAULT_PROJECT

    def _get_pat(self) -> str:
        if self._pat:
            return self._pat
        pat = os.getenv("ADO_PAT", "") or self.memory.recall("ado_pat") or ""
        self._pat = pat
        return pat

    def _headers(self) -> dict:
        token = base64.b64encode(f":{self._get_pat()}".encode()).decode()
        return {"Authorization": f"Basic {token}", "Accept": "application/json",
                "Content-Type": "application/json"}

    def execute(self, action: str, params: dict) -> str:
        if not self._get_pat():
            return "ADO_PAT non configure. Ajoute-le dans .env ou : remember ado_pat=ton_token"
        actions = {
            "search":     self.search_items,
            "get":        self.get_item,
            "update":     self.update_item,
        }
        fn = actions.get(action, self.search_items)
        return fn(params)

    def search_items(self, params: dict) -> str:
        project  = params.get("project", self._project)
        state    = params.get("state", "")
        wi_type  = params.get("type", "")
        assigned = params.get("assigned", "")
        limit    = int(params.get("limit", 8))
        conditions = [f"[System.TeamProject] = '{project}'"]
        if state:    conditions.append(f"[System.State] = '{state}'")
        if wi_type:  conditions.append(f"[System.WorkItemType] = '{wi_type}'")
        if assigned == "@me": conditions.append("[System.AssignedTo] = @Me")
        elif assigned:        conditions.append(f"[System.AssignedTo] contains '{assigned}'")
        where = " AND ".join(conditions)
        wiql  = {"query": f"SELECT [System.Id],[System.Title],[System.WorkItemType],[System.State] FROM WorkItems WHERE {where} ORDER BY [System.ChangedDate] DESC"}
        proj_enc = _req.utils.quote(project)
        try:
            r = _req.post(f"{self.BASE_URL}/{proj_enc}/_apis/wit/wiql?$top={limit}&api-version=7.1",
                         headers=self._headers(), json=wiql, timeout=10)
            r.raise_for_status()
            items = r.json().get("workItems", [])
            if not items:
                return "Aucun item trouve."
            ids = ",".join(str(i["id"]) for i in items[:limit])
            r2  = _req.get(f"{self.BASE_URL}/_apis/wit/workitems?ids={ids}&fields=System.Id,System.Title,System.WorkItemType,System.State&api-version=7.1",
                           headers=self._headers(), timeout=10)
            r2.raise_for_status()
            lines = []
            icons = {"Bug":"🔴","Task":"✅","User Story":"📖","Feature":"⭐","Epic":"🚀"}
            for item in r2.json().get("value", []):
                f = item.get("fields", {})
                icon = icons.get(f.get("System.WorkItemType",""), "📌")
                lines.append(f"  {icon} #{item['id']} [{f.get('System.State','')}] {f.get('System.Title','')[:45]}")
            return f"ADO ({len(lines)} items) :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur ADO : {e}"

    def get_item(self, params: dict) -> str:
        item_id = params.get("item_id") or params.get("id")
        if not item_id:
            return "ID item manquant."
        try:
            r = _req.get(f"{self.BASE_URL}/_apis/wit/workitems/{item_id}?api-version=7.1",
                        headers=self._headers(), timeout=10)
            r.raise_for_status()
            f = r.json().get("fields", {})
            return (f"ADO #{item_id}\n"
                    f"  Titre  : {f.get('System.Title','')}\n"
                    f"  Type   : {f.get('System.WorkItemType','')}\n"
                    f"  Statut : {f.get('System.State','')}\n"
                    f"  Projet : {f.get('System.TeamProject','')}")
        except Exception as e:
            return f"Erreur ADO : {e}"

    def update_item(self, params: dict) -> str:
        item_id = params.get("item_id")
        state   = params.get("state", "")
        if not item_id or not state:
            return "item_id et state requis."
        patch = [{"op": "replace", "path": "/fields/System.State", "value": state}]
        hdrs  = dict(self._headers())
        hdrs["Content-Type"] = "application/json-patch+json"
        try:
            r = _req.patch(f"{self.BASE_URL}/_apis/wit/workitems/{item_id}?api-version=7.1",
                          headers=hdrs, json=patch, timeout=10)
            r.raise_for_status()
            return f"ADO #{item_id} mis a jour : {state}"
        except Exception as e:
            return f"Erreur ADO : {e}"

    def search(self, keyword: str) -> str:
        result = self.search_items({"title_contains": keyword, "limit": 3})
        return result if "item" in result.lower() else ""
