"""
env_checker.py -- Service AION : Verifie les .env de tous les repos.
Detecte les cles manquantes ou avec des valeurs placeholder.
"""
from pathlib import Path
from typing import Any

PLACEHOLDERS = {
    "your_key_here", "your_pat_here", "your_secret_key_change_me",
    "gsk_your_key_here", "change_me", "todo", "your_token_here",
    "", "null", "none", "your_api_key",
}

KNOWN_REQUIRED = {
    "GROQ_API_KEY", "ADO_PAT", "SECRET_KEY", "DB_PATH",
    "GROQ_MODEL", "ADO_ORG",
}


class Service:
    name        = "env_checker"
    description = "Verifie les .env de tous les repos : cles manquantes, placeholders"
    icon        = "\U0001f50d"
    actions     = ["check"]

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._check(params)

    def _check(self, params):
        import os
        default_root = os.getenv("AION_CODE_ROOT", "C:/code/python")
        root = Path(params.get("repos_root") or default_root)
        if not root.exists():
            return {"success": False, "message": f"Repertoire introuvable: {root}"}

        repos  = [d for d in root.iterdir() if d.is_dir()]
        cards  = []
        rows   = []
        headers = ["Repo", "Fichier", "Cle", "Statut", "Valeur"]

        for repo in sorted(repos):
            for env_file in [repo / ".env", repo / "config.yaml"]:
                if not env_file.exists():
                    continue
                try:
                    content = env_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line and ":" not in line:
                        continue
                    sep = "=" if "=" in line else ":"
                    k, _, v = line.partition(sep)
                    k = k.strip()
                    v = v.strip().strip('"\' \'\'').strip()
                    if not k:
                        continue
                    is_ph  = v.lower() in PLACEHOLDERS
                    is_req = k.upper() in KNOWN_REQUIRED
                    if is_ph or (is_req and not v):
                        status = "error"
                        label  = "\u274c Non configure"
                    elif is_req:
                        status = "ok"
                        label  = "\u2705 OK"
                    else:
                        continue  # Ignorer les cles non critiques
                    val_display = ("****" if any(s in k.lower() for s in
                                   ["key","token","pat","secret","password"]) else v[:30])
                    rows.append([repo.name, env_file.name, k, label, val_display])
                    cards.append({"title": repo.name + " / " + k,
                                  "detail": env_file.name + " — " + label,
                                  "status": status})

        if not rows:
            return {"success": True, "message": "\u2705 Tous les .env semblent corrects !", "rows": [], "headers": []}

        nb_err = sum(1 for c in cards if c["status"] == "error")
        summary = f"\U0001f50d {len(rows)} cle(s) verifiee(s) — \u274c {nb_err} probleme(s)"

        return {
            "success": True,
            "message": summary,
            "headers": headers,
            "rows":    rows,
            "cards":   cards,
        }
