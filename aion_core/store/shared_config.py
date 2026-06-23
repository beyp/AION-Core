"""
shared_config.py — Gestion des valeurs partagées entre AION-Core et les apps.

Principe :
  data/shared.env  contient les clés communes (GROQ_API_KEY, ADO_PAT, etc.)
  Ce fichier est git-ignoré — jamais dans le repo.

  Les apps déclarent leurs clés partagées dans apps.local.json :
    "shared_keys": ["GROQ_API_KEY", "GROQ_MODEL", "ADO_PAT"]

  La modale Config détecte automatiquement les clés partagées et propose
  de les hériter depuis shared.env en un clic.
"""
from __future__ import annotations
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Clés globalement reconnues comme partagées (détection automatique)
KNOWN_SHARED_KEYS = {
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "ADO_PAT",
    "ADO_ORG",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "AION_HOST",
    "AION_PORT",
}

SHARED_ENV_PATH = Path("data/shared.env")


class SharedConfig:
    """
    Gestionnaire des valeurs partagées AION-Core.
    Source de vérité : data/shared.env (git-ignoré).
    """

    def __init__(self, shared_path: Path | None = None) -> None:
        self.path = Path(shared_path) if shared_path else SHARED_ENV_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── Lecture ───────────────────────────────────────────────────────────────

    def read_all(self) -> dict[str, str]:
        """Retourne toutes les clés partagées sous forme {KEY: value}."""
        if not self.path.exists():
            return {}
        result = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
        return result

    def get(self, key: str, default: str = "") -> str:
        """Lit une clé partagée."""
        return self.read_all().get(key, default)

    def is_shared_key(self, key: str, app_shared_keys: list[str] | None = None) -> bool:
        """
        Retourne True si la clé est partagée.
        Vérifie d'abord la liste de l'app, puis KNOWN_SHARED_KEYS.
        """
        if app_shared_keys and key in app_shared_keys:
            return True
        return key.upper() in KNOWN_SHARED_KEYS

    # ── Écriture ──────────────────────────────────────────────────────────────

    def set(self, key: str, value: str) -> bool:
        """Met à jour ou ajoute une clé dans shared.env."""
        try:
            content = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
            pattern = rf"(^{re.escape(key)}\s*=)(.*)$"
            new_content, n = re.subn(pattern, lambda m: m.group(1) + value,
                                     content, flags=re.MULTILINE)
            if n == 0:
                new_content = content.rstrip() + f"\n{key}={value}\n"
            self.path.write_text(new_content, encoding="utf-8")
            return True
        except Exception as e:
            logger.error("SharedConfig.set error: %s", e)
            return False

    def set_many(self, updates: dict[str, str]) -> dict[str, bool]:
        """Met à jour plusieurs clés en une fois."""
        return {k: self.set(k, v) for k, v in updates.items()}

    # ── Propagation ───────────────────────────────────────────────────────────

    def propagate_to_app(self, app_id: str, appdata_path: str,
                         keys: list[str] | None = None) -> dict:
        """
        Propage les valeurs partagées vers le .env d'une app dans appdata/.

        Args:
            app_id       : identifiant de l'app
            appdata_path : chemin appdata de l'app
            keys         : liste de clés à propager (None = toutes les partagées connues)

        Returns:
            {"success": bool, "propagated": [str], "skipped": [str]}
        """
        shared = self.read_all()
        if not shared:
            return {"success": True, "propagated": [], "skipped": [], "message": "shared.env vide"}

        env_path = Path(appdata_path) / ".env"
        if not env_path.exists():
            env_path.parent.mkdir(parents=True, exist_ok=True)
            env_path.write_text("", encoding="utf-8")

        content    = env_path.read_text(encoding="utf-8")
        propagated = []
        skipped    = []

        keys_to_push = keys if keys else list(shared.keys())

        for key in keys_to_push:
            value = shared.get(key)
            if value is None:
                skipped.append(key)
                continue
            pattern = rf"(^{re.escape(key)}\s*=)(.*)$"
            new_content, n = re.subn(pattern, lambda m, v=value: m.group(1) + v,
                                     content, flags=re.MULTILINE)
            if n == 0:
                new_content = content.rstrip() + f"\n{key}={value}\n"
            content = new_content
            propagated.append(key)

        env_path.write_text(content, encoding="utf-8")
        logger.info("SharedConfig propagated to %s: %s", app_id, propagated)

        return {
            "success":    True,
            "propagated": propagated,
            "skipped":    skipped,
            "message":    f"{len(propagated)} clé(s) propagée(s) vers {app_id}",
            "env_path":   str(env_path),
        }

    def propagate_to_all_apps(self, registry_files: list[str] | None = None) -> dict:
        """
        Propage vers toutes les apps déclarées dans apps.local.json.
        Utilisé après modification d'une valeur partagée.
        """
        import json
        from pathlib import Path as _P

        files = registry_files or ["apps.local.json", "apps.json"]
        results = {}

        for rf in files:
            p = _P(rf)
            if not p.exists():
                continue
            try:
                reg = json.loads(p.read_text(encoding="utf-8"))
                for app_id, app_cfg in reg.get("apps", {}).items():
                    appdata = app_cfg.get("store", {}).get("appdata_path", "")
                    shared_keys = app_cfg.get("shared_keys", None)
                    if appdata:
                        results[app_id] = self.propagate_to_app(
                            app_id, appdata, shared_keys
                        )
            except Exception as e:
                logger.warning("propagate_to_all_apps error (%s): %s", rf, e)

        total = sum(len(r.get("propagated", [])) for r in results.values())
        return {
            "success": True,
            "apps":    results,
            "total_propagated": total,
            "message": f"Propagation terminée — {total} clé(s) mise(s) à jour dans {len(results)} app(s)",
        }

    # ── Enrichissement pour la modale Config ──────────────────────────────────

    def enrich_fields(self, fields: list[dict],
                      app_shared_keys: list[str] | None = None) -> list[dict]:
        """
        Enrichit une liste de champs config avec les infos de partage.
        Ajoute à chaque champ :
          - shared      : bool — est-ce une clé partagée ?
          - shared_value: str  — valeur dans shared.env (vide si non définie)
          - inheritable : bool — peut-on hériter ? (partagée ET valeur dispo dans shared.env)
        """
        shared_data = self.read_all()
        for f in fields:
            key = f.get("key", "")
            is_shared = self.is_shared_key(key, app_shared_keys)
            shared_val = shared_data.get(key, "")
            f["shared"]       = is_shared
            f["shared_value"] = shared_val
            f["inheritable"]  = is_shared and bool(shared_val)
        return fields
