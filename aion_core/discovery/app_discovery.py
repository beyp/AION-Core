"""
AppDiscovery — Moteur de découverte et d intégration d apps.

Supporte 4 méthodes d intégration :
1. GitHub    → lit README + code → génère connecteur via Groq
2. API REST  → teste l endpoint, génère connecteur HTTP
3. Local     → importe un module Python existant
4. Docker    → pull l image, configure le conteneur

Usage :
    discovery = AppDiscovery(brain, memory, registry_path="apps.json")
    result = await discovery.discover("beyp/ProjectMind")
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
    """
    Moteur de découverte et d intégration d apps pour AION-Core.
    """

    def __init__(self, brain, memory, registry_path: str = "apps.json") -> None:
        self.brain    = brain
        self.memory   = memory
        self.registry = Path(registry_path)
        self._reg     = self._load_registry()

    def _load_registry(self) -> dict:
        if self.registry.exists():
            with open(self.registry, encoding="utf-8") as f:
                return json.load(f)
        return {"version": "1.0", "apps": {}, "app_types": {}}

    def _save_registry(self) -> None:
        with open(self.registry, "w", encoding="utf-8") as f:
            json.dump(self._reg, f, indent=2, ensure_ascii=False)

    # ── API Publique ───────────────────────────────────────────────────────────

    def list_apps(self) -> list[dict]:
        """Retourne la liste de toutes les apps enregistrées."""
        return [
            {"id": k, **v}
            for k, v in self._reg.get("apps", {}).items()
        ]

    def get_app(self, app_id: str) -> dict | None:
        return self._reg.get("apps", {}).get(app_id)

    def discover(self, source: str, app_id: str | None = None,
                 app_type: str = "auto") -> dict:
        """
        Découvre et intègre une nouvelle app.

        Args:
            source:   GitHub "owner/repo", URL API, chemin local, image Docker
            app_id:   Identifiant de l app (auto-détecté si None)
            app_type: "auto" | "github" | "api" | "local" | "docker"

        Returns:
            {"success": bool, "app_id": str, "message": str, "connector_path": str}
        """
        logger.info("Découverte app: source=%s type=%s", source, app_type)

        # Détecter le type automatiquement
        if app_type == "auto":
            app_type = self._detect_type(source)

        logger.info("Type détecté: %s", app_type)

        if app_type == "github":
            return self._discover_github(source, app_id)
        elif app_type == "api":
            return self._discover_api(source, app_id)
        elif app_type == "local":
            return self._discover_local(source, app_id)
        elif app_type == "docker":
            return self._discover_docker(source, app_id)
        else:
            return {"success": False, "message": f"Type inconnu: {app_type}"}

    def remove_app(self, app_id: str) -> dict:
        """Retire une app du registre."""
        if app_id not in self._reg.get("apps", {}):
            return {"success": False, "message": f"App '{app_id}' introuvable"}
        del self._reg["apps"][app_id]
        self._save_registry()
        return {"success": True, "message": f"App '{app_id}' retirée du registre"}

    # ── Détection automatique ──────────────────────────────────────────────────

    def _detect_type(self, source: str) -> str:
        if "/" in source and not source.startswith("http") and not source.startswith("/"):
            return "github"
        if source.startswith("http"):
            return "api"
        if source.startswith("/") or source.startswith("."):
            return "local"
        if ":" in source or source.startswith("docker"):
            return "docker"
        return "github"

    # ── GitHub Discovery ───────────────────────────────────────────────────────

    def _discover_github(self, repo: str, app_id: str | None) -> dict:
        """
        Découverte depuis GitHub :
        1. Lire README + requirements + main files
        2. Groq analyse et génère le connecteur
        3. Sauvegarder dans apps/
        4. Enregistrer dans apps.json
        """
        logger.info("GitHub discovery: %s", repo)

        # Récupérer le contenu du repo
        repo_info = self._fetch_github_repo(repo)
        if not repo_info:
            return {"success": False, "message": f"Impossible de lire {repo}"}

        # Auto-détecter l app_id depuis le nom du repo
        if not app_id:
            app_id = repo.split("/")[-1].lower().replace("-", "_")

        # Demander à Groq d analyser et générer le connecteur
        connector_code = self._groq_generate_connector(repo, repo_info, app_id)
        if not connector_code:
            return {"success": False, "message": "Groq n a pas pu générer le connecteur"}

        # Sauvegarder le connecteur
        connector_path = self._save_connector(app_id, connector_code)

        # Détecter le type d app et l URL
        app_type = "api" if repo_info.get("has_api") else "local"
        api_url  = repo_info.get("api_url", f"http://localhost:{repo_info.get('port', 8766)}")

        # Enregistrer dans le registre
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
            "web_ui":           f"/app/{app_id}",
            "icon":             repo_info.get("icon", "📦"),
            "version":          repo_info.get("version", "1.0"),
            "discovered_from":  "github",
        }
        self._save_registry()

        return {
            "success":        True,
            "app_id":         app_id,
            "connector_path": str(connector_path),
            "message":        f"✅ App '{app_id}' intégrée depuis {repo} !",
            "app_type":       app_type,
            "url":            api_url,
        }

    def _fetch_github_repo(self, repo: str) -> dict | None:
        """Récupère les infos clés d un repo GitHub."""
        # Essayer plusieurs tokens mémorisés
        tokens = []
        for key in ["github_token", "github_pat", "aion_github_token"]:
            t = self.memory.recall(key) if self.memory else None
            if t: tokens.append(t)
        # Token env
        env_token = os.getenv("GITHUB_TOKEN", "")
        if env_token: tokens.append(env_token)
        if not tokens:
            tokens = [None]  # Essayer sans token (repos publics)

        gh_headers = {"Accept": "application/vnd.github+json"}
        if tokens[0]:
            gh_headers["Authorization"] = f"Bearer {tokens[0]}"

        base_url = f"https://api.github.com/repos/{repo}"

        try:
            # Infos du repo
            r = requests.get(base_url, headers=gh_headers, timeout=10)
            if r.status_code != 200:
                return None
            repo_data = r.json()

            info = {
                "name":        repo_data.get("name", ""),
                "description": repo_data.get("description", ""),
                "has_api":     False,
                "api_url":     "",
                "port":        8766,
                "health_endpoint": "/health",
                "icon":        "📦",
                "version":     "1.0",
                "files":       {},
            }

            # Lire les fichiers clés
            key_files = ["README.md", "README_API.md", "requirements.txt",
                         "main.py", "run_api.py", "docker-compose.yml",
                         "Dockerfile", "config.example.yaml"]

            for fname in key_files:
                r2 = requests.get(f"{base_url}/contents/{fname}",
                                  headers=gh_headers, timeout=5)
                if r2.status_code == 200:
                    try:
                        content = base64.b64decode(r2.json()["content"]).decode("utf-8", errors="replace")
                        info["files"][fname] = content[:3000]
                    except Exception:
                        pass

            # Détecter si c est une API
            readme = info["files"].get("README.md", "") + info["files"].get("README_API.md", "")
            if any(kw in readme.lower() for kw in ["api", "fastapi", "flask", "uvicorn", "port"]):
                info["has_api"] = True

            # Détecter le port
            port_match = re.search(r"port[:\s]+(\d{4,5})", readme, re.IGNORECASE)
            if port_match:
                info["port"] = int(port_match.group(1))

            # Détecter l icone depuis le nom
            name_lower = info["name"].lower()
            if "mind" in name_lower:  info["icon"] = "🧠"
            elif "task" in name_lower: info["icon"] = "✅"
            elif "project" in name_lower: info["icon"] = "📋"
            elif "mail" in name_lower: info["icon"] = "📧"
            elif "cal" in name_lower:  info["icon"] = "📅"

            return info

        except Exception as e:
            logger.error("GitHub fetch error: %s", e)
            return None

    def _groq_generate_connector(self, repo: str, repo_info: dict,
                                  app_id: str) -> str | None:
        """Utilise Groq pour générer le connecteur Python."""
        if not self.brain or not self.brain.is_available():
            return self._generate_default_connector(app_id, repo_info)

        # Construire le contexte
        files_summary = ""
        for fname, content in repo_info.get("files", {}).items():
            files_summary += f"\n### {fname}\n{content[:1000]}\n"

        prompt = f"""Génère un connecteur Python pour AION-Core pour l app GitHub : {repo}

Voici les fichiers du projet :
{files_summary}

Le connecteur doit :
1. Hériter de BaseConnector ou être une classe autonome
2. Avoir une méthode execute(action, params) -> str
3. Utiliser l URL : http://localhost:{repo_info.get('port', 8766)}
4. Gérer les erreurs proprement
5. Implémenter les actions principales détectées dans le README/API
6. Avoir une méthode is_available() -> bool
7. Suivre exactement ce template :

```python
"""Connecteur {app_id} — AION-Core."""
import logging
import os
import requests as _req

logger = logging.getLogger(__name__)

{app_id.upper()}_URL = os.getenv("{app_id.upper()}_URL", "http://localhost:{repo_info.get('port', 8766)}")


class {app_id.title().replace('_','')}Connector:
    """Connecteur {repo_info.get('name', app_id)}."""

    def __init__(self, memory=None) -> None:
        self.memory   = memory
        self.base_url = ({app_id.upper()}_URL)

    def execute(self, action: str, params: dict) -> str:
        # Dispatcher vers les bonnes méthodes
        ...

    def is_available(self) -> bool:
        try:
            return _req.get(f"{{self.base_url}}/health", timeout=2).status_code == 200
        except Exception:
            return False
```

Retourne UNIQUEMENT le code Python du connecteur, sans texte avant ou après."""

        response = self.brain.think(prompt, system=None)

        # Extraire le code Python
        if "```python" in response:
            code = response.split("```python")[1].split("```")[0].strip()
        elif "```" in response:
            code = response.split("```")[1].strip()
        else:
            code = response.strip()

        return code if "class " in code else None

    def _generate_default_connector(self, app_id: str, repo_info: dict) -> str:
        """Génère un connecteur générique sans Groq."""
        name     = repo_info.get("name", app_id.title())
        port     = repo_info.get("port", 8766)
        class_name = app_id.title().replace("_", "")

        return f'''"""Connecteur {app_id} — AION-Core (généré automatiquement)."""
import logging
import os
import requests as _req

logger = logging.getLogger(__name__)

{app_id.upper()}_URL = os.getenv("{app_id.upper()}_URL", "http://localhost:{port}")


class {class_name}Connector:
    """{name} connector."""

    def __init__(self, memory=None) -> None:
        self.memory   = memory
        self.base_url = {app_id.upper()}_URL

    def execute(self, action: str, params: dict) -> str:
        actions = {{
            "status":  self.status,
            "list":    self.list_items,
            "health":  self.health,
        }}
        fn = actions.get(action, self.status)
        return fn(params)

    def status(self, params: dict = None) -> str:
        try:
            r = _req.get(f"{{self.base_url}}/", timeout=5)
            r.raise_for_status()
            return f"{name} : en ligne ({{r.status_code}})"
        except Exception as e:
            return f"{name} indisponible : {{e}}"

    def list_items(self, params: dict = None) -> str:
        return self.status()

    def health(self, params: dict = None) -> str:
        return "En ligne ✅" if self.is_available() else "Hors ligne ❌"

    def is_available(self) -> bool:
        try:
            return _req.get(f"{{self.base_url}}/health", timeout=2).status_code == 200
        except Exception:
            return False
'''

    def _save_connector(self, app_id: str, code: str) -> Path:
        """Sauvegarde le connecteur généré."""
        pkg_dir = Path("aion_core") / "apps" / app_id
        pkg_dir.mkdir(parents=True, exist_ok=True)

        init_file = pkg_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text(f'"""AION-Core — {app_id} connector."""\n')

        connector_file = pkg_dir / "connector.py"
        connector_file.write_text(code, encoding="utf-8")
        logger.info("Connecteur sauvegardé: %s", connector_file)
        return connector_file

    # ── API Discovery ──────────────────────────────────────────────────────────

    def _discover_api(self, url: str, app_id: str | None) -> dict:
        """Découverte d une API REST par son URL."""
        if not app_id:
            app_id = url.split("//")[-1].split(":")[0].replace(".", "_").replace("/", "_")

        # Tester l API
        try:
            r = requests.get(url, timeout=5)
            is_available = r.status_code < 500
        except Exception:
            is_available = False

        # Générer un connecteur simple
        code = self._generate_default_connector(app_id, {
            "name": app_id.title(), "port": url.split(":")[-1].split("/")[0]
        })
        connector_path = self._save_connector(app_id, code)

        self._reg.setdefault("apps", {})[app_id] = {
            "name":        app_id.title(),
            "type":        "api",
            "status":      "installed" if is_available else "pending",
            "connector":   str(connector_path),
            "url":         url,
            "discovered_from": "api",
        }
        self._save_registry()

        return {
            "success":   True,
            "app_id":    app_id,
            "message":   f"✅ App '{app_id}' intégrée depuis {url}",
            "available": is_available,
        }

    # ── Local Discovery ────────────────────────────────────────────────────────

    def _discover_local(self, path: str, app_id: str | None) -> dict:
        """Découverte d un module Python local."""
        local_path = Path(path)
        if not local_path.exists():
            return {"success": False, "message": f"Chemin introuvable: {path}"}

        if not app_id:
            app_id = local_path.stem.lower().replace("-", "_")

        # Copier ou créer un lien vers le module
        connector_path = self._save_connector(app_id,
            f'"""Connecteur local {app_id}."""\nimport sys\nsys.path.insert(0, "{path}")\n')

        self._reg.setdefault("apps", {})[app_id] = {
            "name":        app_id.title(),
            "type":        "local",
            "status":      "installed",
            "connector":   str(connector_path),
            "url":         None,
            "local_path":  str(local_path),
            "discovered_from": "local",
        }
        self._save_registry()
        return {"success": True, "app_id": app_id, "message": f"✅ Module local '{app_id}' intégré"}

    # ── Docker Discovery ───────────────────────────────────────────────────────

    def _discover_docker(self, image: str, app_id: str | None) -> dict:
        """Découverte via Docker — pull l image et configure."""
        if not app_id:
            app_id = image.split("/")[-1].split(":")[0].lower().replace("-", "_")

        # Vérifier que Docker est disponible
        try:
            subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
        except Exception:
            return {"success": False, "message": "Docker non disponible sur ce système"}

        # Trouver un port libre (simplifié)
        port = 8800  # à améliorer avec socket

        # Générer docker-compose snippet
        compose_snippet = f"""  {app_id}:
    image: {image}
    container_name: {app_id}
    ports:
      - "{port}:{port}"
    restart: unless-stopped
"""
        code = self._generate_default_connector(app_id, {"name": app_id.title(), "port": port})
        connector_path = self._save_connector(app_id, code)

        self._reg.setdefault("apps", {})[app_id] = {
            "name":         app_id.title(),
            "type":         "docker",
            "status":       "pending",
            "connector":    str(connector_path),
            "url":          f"http://localhost:{port}",
            "docker_image": image,
            "docker_port":  port,
            "discovered_from": "docker",
        }
        self._save_registry()

        return {
            "success":        True,
            "app_id":         app_id,
            "message":        f"✅ App Docker '{app_id}' configurée (image: {image}). Lance : docker-compose up -d {app_id}",
            "docker_compose": compose_snippet,
            "port":           port,
        }
