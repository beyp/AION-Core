"""
git_status.py -- Service AION : Statut Git de tous les repos dans AION_APPS.
"""
import subprocess
from pathlib import Path
from typing import Any


class Service:
    name        = "git_status"
    description = "Statut git (branch, modifs, retard) de tous les repos AION_APPS"
    icon        = "\U0001f500"
    actions     = ["status"]

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._status(params)

    def _status(self, params):
        root = Path(params.get("repos_root") or "C:/AION_APPS/repos")
        if not root.exists():
            return {"success": False, "message": f"Repertoire introuvable: {root}"}

        repos = [d for d in root.iterdir() if d.is_dir() and (d / ".git").exists()]
        if not repos:
            return {"success": False, "message": f"Aucun repo git dans {root}"}

        headers = ["Repo", "Branche", "Statut", "Modifs locales", "Retard origin"]
        rows    = []
        cards   = []

        for repo in sorted(repos):
            name = repo.name

            def git(cmd):
                try:
                    r = subprocess.run(
                        ["git"] + cmd, cwd=str(repo),
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=10
                    )
                    return r.stdout.strip(), r.returncode == 0
                except Exception:
                    return "", False

            # Branche courante
            branch, _ = git(["rev-parse", "--abbrev-ref", "HEAD"])
            branch = branch or "?"

            # Modifs locales
            status_out, _ = git(["status", "--porcelain"])
            nb_modifs = len([l for l in status_out.splitlines() if l.strip()])

            # Fetch silencieux + retard
            git(["fetch", "origin", "--quiet"])
            behind_out, _ = git(["rev-list", "--count", "HEAD..origin/" + branch])
            try:
                behind = int(behind_out)
            except ValueError:
                behind = 0

            # Statut global
            if nb_modifs > 0 and behind > 0:
                status = "warn"
                status_txt = "\u26a0\ufe0f Modifs + retard"
            elif nb_modifs > 0:
                status = "warn"
                status_txt = "\u270f\ufe0f Modifs locales"
            elif behind > 0:
                status = "warn"
                status_txt = "\U0001f504 En retard"
            else:
                status = "ok"
                status_txt = "\u2705 A jour"

            rows.append([name, branch,
                         status_txt,
                         str(nb_modifs) + " fichier(s)" if nb_modifs else "\u2014",
                         str(behind) + " commit(s)" if behind else "\u2014"])
            cards.append({
                "title":  name + "  (" + branch + ")",
                "detail": status_txt + ("  |  " + str(nb_modifs) + " modif(s)" if nb_modifs else "")
                         + ("  |  " + str(behind) + " commit(s) en retard" if behind else ""),
                "status": status,
            })

        nb_ok   = sum(1 for c in cards if c["status"] == "ok")
        nb_warn = len(cards) - nb_ok
        summary = f"{len(repos)} repos : \u2705 {nb_ok} OK, \u26a0\ufe0f {nb_warn} attention"

        return {
            "success": True,
            "message": summary,
            "headers": headers,
            "rows":    rows,
            "cards":   cards,
        }
