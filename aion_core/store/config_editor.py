"""
config_editor.py -- Editeur de configuration des apps AION.

Lit les fichiers config.yaml et .env d'une app,
detecte les cles non remplies (vides, placeholder),
et permet de les modifier depuis le dashboard AION.

Les fichiers sont TOUJOURS dans appdata/ (git-ignore) :
  C:/AION_APPS/appdata/quickmind/config.yaml
  C:/AION_APPS/appdata/projectmind/.env

Jamais dans le repo git -> cles API en securite.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Valeurs considerees comme 'non remplies' (placeholders)
EMPTY_PLACEHOLDERS = {
    "", "your_key_here", "your_pat_here", "your_secret_key_change_me",
    "gsk_your_key_here", "change_me", "todo", "xxx", "your_token_here",
    "your_api_key", "your_github_token", "<your_key>", "null", "none",
}

# Cles sensibles (masquees dans l'UI)
SENSITIVE_KEYS = {
    "github_token", "groq_api_key", "api_key", "secret_key", "pat",
    "ado_pat", "password", "token", "secret", "key", "private_key",
}


def _is_empty(value: Any) -> bool:
    """Retourne True si la valeur est un placeholder ou vide."""
    if value is None:
        return True
    return str(value).strip().lower() in EMPTY_PLACEHOLDERS


def _is_sensitive(key: str) -> bool:
    """Retourne True si la cle est sensible (a masquer)."""
    k = key.lower().replace("-", "_")
    return any(s in k for s in SENSITIVE_KEYS)


class ConfigEditor:
    """
    Lit et edite les fichiers de configuration d'une app.
    Cherche config.yaml et .env dans appdata/ EN PREMIER,
    puis dans install_path/ si absent.
    """

    def __init__(self, app_id: str, install_path: str, appdata_path: str) -> None:
        self.app_id       = app_id
        self.install_path = Path(install_path)
        self.appdata_path = Path(appdata_path)

    def _find_config_file(self, filename: str) -> Path | None:
        """
        Cherche un fichier de config.
        Priorite : appdata/ > install_path/
        """
        p = self.appdata_path / filename
        if p.exists():
            return p
        p = self.install_path / filename
        if p.exists():
            return p
        return None

    def _ensure_in_appdata(self, filename: str) -> Path:
        """
        S'assure que le fichier de config est dans appdata/.
        Le copie depuis install_path/ si necessaire.
        """
        import shutil
        dest = self.appdata_path / filename
        if not dest.exists():
            src = self.install_path / filename
            if src.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dest))
                logger.info("Config copie dans appdata/: %s", dest)
        return dest

    # -- Lecture --------------------------------------------------

    def read_all(self) -> dict:
        """
        Lit toutes les configs (yaml + env).
        Retourne un dict structure pour l'UI.
        """
        result    = {"files": {}, "has_empty": False, "empty_count": 0}
        cfg_files = ["config.yaml", "config.yml", ".env"]

        for fname in cfg_files:
            path = self._find_config_file(fname)
            if not path:
                continue

            if fname.endswith((".yaml", ".yml")):
                fields = self._parse_yaml(path)
            else:
                fields = self._parse_env(path)

            empty = [f for f in fields if f["empty"]]
            result["files"][fname] = {
                "fields":      fields,
                "path":        str(path),
                "in_appdata":  str(self.appdata_path) in str(path),
                "empty_count": len(empty),
            }
            result["empty_count"] += len(empty)
            if empty:
                result["has_empty"] = True

        return result

    def _parse_yaml(self, path: Path) -> list[dict]:
        """Parse un fichier YAML et retourne les champs plats."""
        try:
            import yaml
            with open(path, encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        except ImportError:
            return self._parse_yaml_simple(path)
        except Exception as e:
            logger.warning("YAML parse error %s: %s", path, e)
            return []
        return self._flatten_yaml(data, prefix="")

    def _flatten_yaml(self, data: dict, prefix: str) -> list[dict]:
        """Aplatit un dict YAML en liste de champs."""
        fields = []
        for k, v in data.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                fields.extend(self._flatten_yaml(v, full_key))
            else:
                fields.append({
                    "key":       full_key,
                    "value":     str(v) if v is not None else "",
                    "empty":     _is_empty(v),
                    "sensitive": _is_sensitive(k),
                    "type":      "yaml",
                })
        return fields

    def _parse_yaml_simple(self, path: Path) -> list[dict]:
        """Parse YAML basique ligne par ligne (sans PyYAML)."""
        fields = []
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
            for line in lines:
                line = line.strip()
                if line.startswith("#") or ":" not in line:
                    continue
                k, _, v = line.partition(":")
                k = k.strip()
                v = v.strip().strip('"\'')
                if k:
                    fields.append({
                        "key":       k,
                        "value":     v,
                        "empty":     _is_empty(v),
                        "sensitive": _is_sensitive(k),
                        "type":      "yaml",
                    })
        except Exception as e:
            logger.warning("YAML simple parse: %s", e)
        return fields

    def _parse_env(self, path: Path) -> list[dict]:
        """Parse un fichier .env et retourne les champs."""
        fields = []
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                fields.append({
                    "key":       k,
                    "value":     v,
                    "empty":     _is_empty(v),
                    "sensitive": _is_sensitive(k),
                    "type":      "env",
                })
        except Exception as e:
            logger.warning(".env parse %s: %s", path, e)
        return fields

    # -- Ecriture -------------------------------------------------

    def save_field(self, filename: str, key: str, value: str) -> dict:
        """
        Sauvegarde une valeur dans le fichier de config.
        Toujours dans appdata/ (cree le fichier si absent).

        Args:
            filename: "config.yaml" ou ".env"
            key:      Cle (ex: "updater.github_token" ou "GROQ_API_KEY")
            value:    Nouvelle valeur

        Returns:
            {"success": bool, "message": str, "path": str}
        """
        dest = self._ensure_in_appdata(filename)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text('', encoding='utf-8')

        try:
            if filename.endswith((".yaml", ".yml")):
                return self._save_yaml_field(dest, key, value)
            else:
                return self._save_env_field(dest, key, value)
        except Exception as e:
            logger.error("save_field error [%s] %s: %s", filename, key, e)
            return {"success": False, "message": str(e), "path": str(dest)}

    def _save_yaml_field(self, path: Path, key: str, value: str) -> dict:
        """Met a jour une cle dans un fichier YAML (edition texte).

        Supporte les cles imbriquees (ex: updater.github_token).
        Utilise re.subn pour remplacer en place, ou ajoute a la fin si absent.
        """
        content = path.read_text(encoding='utf-8')
        leaf_key = key.split('.')[-1]
        # Echapper la valeur : guillemets si contient des caracteres speciaux
        if re.match(r'^[\w\-\./:@]+$', value):
            safe_value = value
        else:
            safe_value = f'"{value}"'
        pattern = rf'(^\s*{re.escape(leaf_key)}\s*:\s*)(.*)$'
        new_content, n = re.subn(
            pattern,
            lambda m: m.group(1) + safe_value,
            content,
            flags=re.MULTILINE,
        )
        if n == 0:
            new_content = content.rstrip() + f'\n{leaf_key}: {safe_value}\n'
        path.write_text(new_content, encoding='utf-8')
        # Synchroniser dans install_path/ pour que l'app lise la valeur
        install_copy = self.install_path / path.name
        if install_copy.resolve() != path.resolve() and install_copy.parent.exists():
            install_copy.write_text(new_content, encoding='utf-8')
        return {"success": True, "message": f"{key} mis a jour", "path": str(path)}

    def _save_env_field(self, path: Path, key: str, value: str) -> dict:
        """Met a jour ou ajoute une cle dans un fichier .env."""
        content = path.read_text(encoding='utf-8')
        pattern = rf'(^{re.escape(key)}\s*=)(.*)$'
        new_content, n = re.subn(
            pattern,
            lambda m: m.group(1) + str(value),
            content,
            flags=re.MULTILINE,
        )
        if n == 0:
            new_content = content.rstrip() + f'\n{key}={value}\n'
        path.write_text(new_content, encoding='utf-8')
        # Synchroniser dans install_path/
        install_copy = self.install_path / '.env'
        if install_copy.resolve() != path.resolve() and install_copy.parent.exists():
            install_copy.write_text(new_content, encoding='utf-8')
        return {"success": True, "message": f"{key} mis a jour", "path": str(path)}

    def save_all_fields(self, updates: dict[str, dict[str, str]]) -> dict:
        """
        Sauvegarde plusieurs champs en une fois.
        updates = {"config.yaml": {"key1": "val1", ...}, ".env": {...}}
        """
        results = []
        for filename, fields in updates.items():
            for key, value in fields.items():
                r = self.save_field(filename, key, value)
                results.append(r)
        ok    = all(r['success'] for r in results)
        saved = sum(1 for r in results if r['success'])
        return {
            "success": ok,
            "saved":   saved,
            "total":   len(results),
            "message": f"{saved}/{len(results)} champ(s) sauvegarde(s)",
            "details": results,
        }
