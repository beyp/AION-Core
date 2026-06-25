"""
ado_search.py -- Service AION : Recherche rapide dans Azure DevOps.
"""
import base64 as _b64
import os
from typing import Any


class Service:
    name        = "ado_search"
    description = "Recherche de work items dans Azure DevOps (PTG - TMM)"
    icon        = "🔵"
    actions     = ["search"]

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._search(params)

    def _search(self, params):
        try:
            import requests as _req
        except ImportError:
            return {"success": False, "message": "requests non installe dans le venv"}

        pat     = os.getenv("ADO_PAT", "")
        org     = os.getenv("ADO_ORG", "Premiertech")
        project = str(params.get("project") or "PTG - TMM D2")
        query   = str(params.get("query") or "").strip()
        max_res = int(params.get("max") or 20)

        if not query:
            return {"success": False, "message": "Parametre manquant: query"}
        if not pat:
            return {"success": False,
                    "message": ("ADO_PAT non configure. "
                                "Va dans /store -> Config -> app et herite depuis AION.")}

        token   = _b64.b64encode((":" + pat).encode()).decode()
        hdrs    = {"Authorization": "Basic " + token,
                   "Content-Type":  "application/json"}

        wiql_str = (
            "SELECT [System.Id],[System.Title],[System.State],"
            "[System.AssignedTo],[System.WorkItemType] "
            "FROM WorkItems "
            "WHERE [System.TeamProject] = \'" + project + "\' "
            "AND [System.Title] CONTAINS \'" + query + "\' "
            "ORDER BY [System.ChangedDate] DESC"
        )
        url = ("https://dev.azure.com/" + org + "/" + project
               + "/_apis/wit/wiql?api-version=7.0&$top=" + str(max_res))
        try:
            r = _req.post(url, json={"query": wiql_str}, headers=hdrs, timeout=10)
            if r.status_code == 401:
                return {"success": False, "message": "ADO_PAT invalide ou expire."}
            if r.status_code != 200:
                return {"success": False,
                        "message": "ADO erreur " + str(r.status_code) + ": " + r.text[:200]}
            items = r.json().get("workItems", [])
        except Exception as e:
            return {"success": False, "message": "Connexion ADO impossible: " + str(e)}

        if not items:
            return {"success": True,
                    "message": "Aucun item trouve pour \"" + query + "\".",
                    "rows": [], "headers": []}

        ids  = [str(i["id"]) for i in items[:max_res]]
        url2 = ("https://dev.azure.com/" + org + "/" + project
                + "/_apis/wit/workitems?ids=" + ",".join(ids)
                + "&fields=System.Id,System.Title,System.State,"
                  "System.AssignedTo,System.WorkItemType&api-version=7.0")
        try:
            r2    = _req.get(url2, headers=hdrs, timeout=10)
            datas = r2.json().get("value", []) if r2.status_code == 200 else []
        except Exception:
            datas = []

        ado_base     = "https://dev.azure.com/" + org + "/" + project + "/_workitems/edit/"
        headers_tbl  = ["ID", "Type", "Titre", "Statut", "Assigne a"]
        rows  = []
        cards = []
        for item in datas:
            f       = item.get("fields", {})
            item_id = str(item.get("id", ""))
            title   = str(f.get("System.Title", ""))[:60]
            state   = str(f.get("System.State", ""))
            wit     = str(f.get("System.WorkItemType", ""))
            assigned = f.get("System.AssignedTo") or {}
            user    = str(assigned.get("displayName", "—")) if isinstance(assigned, dict) else "—"
            link    = ('<a href="' + ado_base + item_id + '" target="_blank" '
                       'style="color:var(--accent);">#' + item_id + '</a>')
            rows.append([link, wit, title, state, user])
            if state in ("Done", "Closed", "Resolved"):
                status = "ok"
            elif state in ("In Progress", "Active"):
                status = "warn"
            else:
                status = ""
            cards.append({
                "title":  "#" + item_id + " — " + title,
                "detail": wit + " | " + state + " | " + user,
                "status": status,
            })

        return {
            "success": True,
            "message": "🔵 " + str(len(rows)) + " item(s) pour \"" + query + "\" dans " + project,
            "headers": headers_tbl,
            "rows":    rows,
            "cards":   cards,
        }
