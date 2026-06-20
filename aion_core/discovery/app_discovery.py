"""
AppDiscovery -- Moteur de decouverte et d integration d apps.

Supporte 4 methodes d integration :
1. GitHub    -> lit README + code -> genere connecteur via Groq
2. API REST  -> teste l endpoint, genere connecteur HTTP
3. Local     -> importe un module Python existant
4. Docker    -> configure le conteneur

Usage :
    discovery = AppDiscovery(brain, memory)
    result = discovery.discover("beyp/ProjectMind")
"""
import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

REGISTRY_FILE = Path("apps.json")


class AppDiscovery:
    """Moteur de decouverte et d integration d apps pour AION-Core."""

    def __init__(self, brain, memory, registry_path: str = "apps.json") -> None:
        self.brain    = brain
        self.memory   = memory
        self.registry = Path(registry_path)
        self._reg     = self._load_registry()

    def _load_registry(self) -> dict:
        if self.registry.exists():
            try:
                with open(self.registry, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"version": "1.0", "apps": {}, "app_types": {}}

    def _save_registry(self) -> None:
        with open(self.registry, "w", encoding="utf-8") as f:
            json.dump(self._reg, f, indent=2, ensure_ascii=False)

    # -- API Publique -----------------------------------------------------------

    def list_apps(self) -> list:
        return [{"id": k, **v} for k, v in self._reg.get("apps", {}).items()]

    def get_app(self, app_id: str) -> dict | None:
        return self._reg.get("apps", {}).get(app_id)

    def discover(self, source: str, app_id: str | None = None,
                 app_type: str = "auto") -> dict:
        """
        Decouvre et integre une nouvelle app.

        Args:
            source:   GitHub "owner/repo", URL API, chemin local, image Docker
            app_id:   Identifiant de l app (auto-detecte si None)
            app_type: "auto" | "github" | "api" | "local" | "docker"

        Returns:
            {"success": bool, "app_id": str, "message": str}
        """
        logger.info("Decouverte app: source=%s type=%s", source, app_type)

        if app_type == "auto":
            app_type = self._detect_type(source)

        logger.info("Type detecte: %s", app_type)

        if app_type == "github":
            return self._discover_github(source, app_id)
        if app_type == "api":
            return self._discover_api(source, app_id)
        if app_type == "local":
            return self._discover_local(source, app_id)
        if app_type == "docker":
            return self._discover_docker(source, app_id)
        return {"success": False, "message": "Type inconnu: " + app_type}

    def remove_app(self, app_id: str) -> dict:
        if app_id not in self._reg.get("apps", {}):
            return {"success": False, "message": "App '" + app_id + "' introuvable"}
        del self._reg["apps"][app_id]
        self._save_registry()
        return {"success": True, "message": "App '" + app_id + "' retiree du registre"}

    # -- Detection automatique -------------------------------------------------

    def _detect_type(self, source: str) -> str:
        if "/" in source and not source.startswith("http") and not source.startswith("/"):
            return "github"
        if source.startswith("http"):
            return "api"
        if source.startswith("/") or source.startswith("."):
            return "local"
        if ":" in source:
            return "docker"
        return "github"

    # -- GitHub Discovery ------------------------------------------------------

    def _discover_github(self, repo: str, app_id: str | None) -> dict:
        """Decouverte depuis GitHub : lit le repo et genere le connecteur."""
        logger.info("GitHub discovery: %s", repo)

        repo_info = self._fetch_github_repo(repo)
        if not repo_info:
            return {"success": False, "message": "Impossible de lire " + repo}

        if not app_id:
            app_id = repo.split("/")[-1].lower().replace("-", "_")

        connector_code = self._groq_generate_connector(repo, repo_info, app_id)
        if not connector_code:
            connector_code = self._generate_default_connector(app_id, repo_info)

        connector_path = self._save_connector(app_id, connector_code)

        app_type = "api" if repo_info.get("has_api") else "local"
        api_url  = repo_info.get("api_url", "http://localhost:" + str(repo_info.get("port", 8766)))

        self._reg.setdefault("apps", {})[app_id] = {
            "name":             repo_info.get("name", app_id.title()),
            "description":      repo_info.get("description", ""),
            "type":             app_type,
            "status":           "installed",
            "connector":        str(connector_path),
            "url":              api_url,
            "health_endpoint":  repo_info.get("health_endpoint", "/health"),
            "github":           repo,
            "docker_image":     None,
            "web_ui":           "/app/" + app_id,
            "icon":             repo_info.get("icon", "package"),
            "version":          repo_info.get("version", "1.0"),
            "discovered_from":  "github",
        }
        self._save_registry()

        return {
            "success":        True,
            "app_id":         app_id,
            "connector_path": str(connector_path),
            "message":        "App '" + app_id + "' integree depuis " + repo + " !",
            "app_type":       app_type,
            "url":            api_url,
        }

    def _fetch_github_repo(self, repo: str) -> dict | None:
        """Recupere les infos cles d un repo GitHub."""
        tokens = []
        if self.memory:
            for key in ["github_token", "github_pat", "aion_github_token"]:
                t = self.memory.recall(key)
                if t:
                    tokens.append(t)
        env_token = os.getenv("GITHUB_TOKEN", "")
        if env_token:
            tokens.append(env_token)
        if not tokens:
            tokens = [None]

        gh_headers = {"Accept": "application/vnd.github+json"}
        if tokens[0]:
            gh_headers["Authorization"] = "Bearer " + tokens[0]

        base_url = "https://api.github.com/repos/" + repo

        try:
            r = requests.get(base_url, headers=gh_headers, timeout=10)
            if r.status_code != 200:
                return None
            repo_data = r.json()

            info = {
                "name":             repo_data.get("name", ""),
                "description":      repo_data.get("description", ""),
                "has_api":          False,
                "api_url":          "",
                "port":             8766,
                "health_endpoint":  "/health",
                "icon":             "package",
                "version":          "1.0",
                "files":            {},
            }

            key_files = [
                "README.md", "README_API.md", "requirements.txt",
                "main.py", "run_api.py", "docker-compose.yml",
                "Dockerfile", "config.example.yaml",
            ]

            for fname in key_files:
                r2 = requests.get(base_url + "/contents/" + fname,
                                  headers=gh_headers, timeout=5)
                if r2.status_code == 200:
                    try:
                        import base64 as _b64
                        raw = r2.json().get("content", "")
                        decoded = _b64.b64decode(raw).decode("utf-8", errors="replace")
                        info["files"][fname] = decoded[:3000]
                    except Exception:
                        pass

            readme = info["files"].get("README.md", "") + info["files"].get("README_API.md", "")
            if any(kw in readme.lower() for kw in ["api", "fastapi", "flask", "uvicorn", "port"]):
                info["has_api"] = True

            port_match = re.search(r"port[:\s]+(\d{4,5})", readme, re.IGNORECASE)
            if port_match:
                info["port"] = int(port_match.group(1))

            name_lower = info["name"].lower()
            if "mind"    in name_lower: info["icon"] = "brain"
            elif "task"  in name_lower: info["icon"] = "check"
            elif "proj"  in name_lower: info["icon"] = "clipboard"
            elif "mail"  in name_lower: info["icon"] = "mail"

            return info

        except Exception as e:
            logger.error("GitHub fetch error: %s", e)
            return None

    def _groq_generate_connector(self, repo: str, repo_info: dict,
                                  app_id: str) -> str | None:
        """Utilise Groq pour generer le connecteur Python."""
        if not self.brain or not self.brain.is_available():
            return None

        files_summary = ""
        for fname, fcontent in repo_info.get("files", {}).items():
            files_summary += "\n### " + fname + "\n" + fcontent[:800] + "\n"

        port = str(repo_info.get("port", 8766))

        prompt = (
            "Genere un connecteur Python pour AION-Core pour l app GitHub : " + repo + "\n\n"
            "Fichiers du projet :\n" + files_summary + "\n\n"
            "Le connecteur doit :\n"
            "1. Etre une classe NomConnector avec __init__(self, memory=None)\n"
            "2. Avoir execute(self, action: str, params: dict) -> str\n"
            "3. Avoir is_available(self) -> bool\n"
            "4. Utiliser requests pour appeler http://localhost:" + port + "\n"
            "5. Gerer les erreurs proprement\n\n"
            "Retourne UNIQUEMENT le code Python, sans texte avant ou apres."
        )

        response = self.brain.think(prompt)

        if "```python" in response:
            code = response.split("```python")[1].split("```")[0].strip()
        elif "```" in response:
            code = response.split("```")[1].strip()
            if code.startswith("python"):
                code = code[6:].strip()
        else:
            code = response.strip()

        return code if "class " in code and "def execute" in code else None

    def _generate_default_connector(self, app_id: str, repo_info: dict) -> str:
        """Genere un connecteur generique sans Groq."""
        name       = str(repo_info.get("name", app_id.title()))
        port       = str(repo_info.get("port", 8766))
        class_name = app_id.title().replace("_", "")
        env_key    = app_id.upper() + "_URL"

        lines = [
            '"""Connecteur ' + app_id + ' - AION-Core (genere automatiquement)."""',
            "import logging",
            "import os",
            "import requests as _req",
            "",
            "logger = logging.getLogger(__name__)",
            "",
            env_key + " = os.getenv('" + env_key + "', 'http://localhost:" + port + "')",
            "",
            "",
            "class " + class_name + "Connector:",
            '    """' + name + ' connector."""',
            "",
            "    def __init__(self, memory=None) -> None:",
            "        self.memory   = memory",
            "        self.base_url = " + env_key,
            "",
            "    def execute(self, action: str, params: dict) -> str:",
            "        actions = {",
            "            'status': self.status,",
            "            'list':   self.list_items,",
            "            'health': self.health,",
            "        }",
            "        fn = actions.get(action, self.status)",
            "        return fn(params)",
            "",
            "    def status(self, params=None) -> str:",
            "        try:",
            "            r = _req.get(self.base_url + '/', timeout=5)",
            "            r.raise_for_status()",
            "            return '" + name + " : en ligne'",
            "        except Exception as e:",
            "            return '" + name + " indisponible : ' + str(e)",
            "",
            "    def list_items(self, params=None) -> str:",
            "        return self.status()",
            "",
            "    def health(self, params=None) -> str:",
            "        return 'En ligne' if self.is_available() else 'Hors ligne'",
            "",
            "    def is_available(self) -> bool:",
            "        try:",
            "            return _req.get(self.base_url + '/health', timeout=2).status_code == 200",
            "        except Exception:",
            "            return False",
        ]
        return "\n".join(lines)

    def _save_connector(self, app_id: str, code: str) -> Path:
        pkg_dir = Path("aion_core") / "apps" / app_id
        pkg_dir.mkdir(parents=True, exist_ok=True)

        init_file = pkg_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""AION-Core - ' + app_id + ' connector."""\n')

        connector_file = pkg_dir / "connector.py"
        connector_file.write_text(code, encoding="utf-8")
        logger.info("Connecteur sauvegarde: %s", connector_file)
        return connector_file

    # -- API Discovery ---------------------------------------------------------

    def _discover_api(self, url: str, app_id: str | None) -> dict:
        if not app_id:
            app_id = url.split("//")[-1].split(":")[0].replace(".", "_")

        try:
            requests.get(url, timeout=5)
            is_available = True
        except Exception:
            is_available = False

        code           = self._generate_default_connector(app_id, {"name": app_id.title(), "port": url.split(":")[-1].split("/")[0]})
        connector_path = self._save_connector(app_id, code)

        self._reg.setdefault("apps", {})[app_id] = {
            "name":            app_id.title(),
            "type":            "api",
            "status":          "installed" if is_available else "pending",
            "connector":       str(connector_path),
            "url":             url,
            "discovered_from": "api",
        }
        self._save_registry()
        return {"success": True, "app_id": app_id, "message": "App '" + app_id + "' integree depuis " + url}

    # -- Local Discovery -------------------------------------------------------

    def _discover_local(self, path: str, app_id: str | None) -> dict:
        local_path = Path(path)
        if not local_path.exists():
            return {"success": False, "message": "Chemin introuvable: " + path}

        if not app_id:
            app_id = local_path.stem.lower().replace("-", "_")

        code           = self._generate_default_connector(app_id, {"name": app_id.title(), "port": 8766})
        connector_path = self._save_connector(app_id, code)

        self._reg.setdefault("apps", {})[app_id] = {
            "name":            app_id.title(),
            "type":            "local",
            "status":          "installed",
            "connector":       str(connector_path),
            "url":             None,
            "local_path":      str(local_path),
            "discovered_from": "local",
        }
        self._save_registry()
        return {"success": True, "app_id": app_id, "message": "Module local '" + app_id + "' integre"}

    # -- Docker Discovery ------------------------------------------------------

    def _discover_docker(self, image: str, app_id: str | None) -> dict:
        if not app_id:
            app_id = image.split("/")[-1].split(":")[0].lower().replace("-", "_")

        try:
            subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
        except Exception:
            return {"success": False, "message": "Docker non disponible"}

        port = 8800
        code = self._generate_default_connector(app_id, {"name": app_id.title(), "port": port})
        connector_path = self._save_connector(app_id, code)

        self._reg.setdefault("apps", {})[app_id] = {
            "name":            app_id.title(),
            "type":            "docker",
            "status":          "pending",
            "connector":       str(connector_path),
            "url":             "http://localhost:" + str(port),
            "docker_image":    image,
            "docker_port":     port,
            "discovered_from": "docker",
        }
        self._save_registry()

        return {
            "success":  True,
            "app_id":   app_id,
            "message":  "App Docker '" + app_id + "' configuree. Lance: docker-compose up -d " + app_id,
            "port":     port,
        }
