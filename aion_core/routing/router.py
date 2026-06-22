"""
AppRouter — Router intelligent AION-Core.
Comprend l intention et délègue à la bonne app.
"""
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

ROUTER_SYSTEM = """Tu es AION, un orchestrateur IA personnel.
Tu reçois une commande et tu retournes un JSON indiquant quelle app appeler.

Apps disponibles :
- quickmind  : gestion de tâches (ajouter, lister, modifier, supprimer)
- ado        : Azure DevOps (items, statuts, recherche)
- projectmind: gestion de projets (ProjectMind)
- system     : système (CPU, RAM, réseau, disque, uptime)
- timer      : compte à rebours avec notification
- memory     : memoire AION (remember, recall, forget, list, import_json, clear)
- search     : recherche dans plusieurs apps simultanément
- direct     : répondre directement sans app

Retourne UNIQUEMENT ce JSON :
{
  "app": "nom_app",
  "action": "action_specifique",
  "params": {},
  "confidence": 0.95,
  "response_hint": "courte phrase de réponse vocale"
}

Exemples :
"ajoute RDV demain" → {"app":"quickmind","action":"add_task","params":{"title":"RDV demain","priority":"normal"},"confidence":0.99,"response_hint":"J ajoute RDV demain."}
"mes items ADO en cours" → {"app":"ado","action":"search","params":{"state":"In Progress","assigned":"@me"},"confidence":0.95,"response_hint":"Je cherche vos items en cours."}
"CPU et RAM" → {"app":"system","action":"cpu_ram","params":{},"confidence":0.99,"response_hint":"Je vérifie CPU et RAM."}
"cherche formation" → {"app":"search","action":"universal","params":{"keyword":"formation"},"confidence":0.90,"response_hint":"Je cherche formation partout."}
"timer 25 minutes" → {"app":"timer","action":"start","params":{"duration":"25m","message":"Temps ecoulé !"},"confidence":0.99,"response_hint":"Timer 25 minutes lance."}
"importe ces clés en mémoire: {..." → {"app":"memory","action":"import_json","params":{"data":{...}},"confidence":0.97,"response_hint":"J'importe les clés en mémoire."}
"liste ma mémoire" → {"app":"memory","action":"list","params":{},"confidence":0.98,"response_hint":"Voici ta mémoire."}
"souviens-toi que mon projet = AION" → {"app":"memory","action":"remember","params":{"key":"mon_projet","value":"AION"},"confidence":0.99,"response_hint":"Je mémorise."}
"qu'est-ce que AIOnPath ?" → {"app":"memory","action":"recall","params":{"key":"AIOnPath"},"confidence":0.95,"response_hint":"Je cherche dans ma mémoire."}
"""


class AppRouter:
    """
    Router intelligent — analyse l intention et délègue.
    """

    def __init__(self, brain, memory) -> None:
        self.brain  = brain
        self.memory = memory
        self._apps: dict[str, Any] = {}
        self._load_apps()

    def _load_apps(self) -> None:
        """
        Charge les connecteurs d apps disponibles.
        Charge d abord les apps hardcodées, puis les apps du registre apps.json.
        """
        from aion_core.apps.quickmind.connector import QuickMindConnector
        from aion_core.apps.ado.connector        import ADOConnector
        from aion_core.apps.system.connector     import SystemConnector
        from aion_core.apps.timer.connector      import TimerConnector

        # Apps de base — toujours disponibles
        self._apps = {
            "quickmind": QuickMindConnector(self.memory),
            "ado":       ADOConnector(self.memory),
            "system":    SystemConnector(),
            "timer":     TimerConnector(self.memory),
        }

        # Charger les apps découvertes dynamiquement depuis apps.json
        self._load_discovered_apps()

        logger.info("Apps chargées: %s", list(self._apps.keys()))

    def _load_discovered_apps(self) -> None:
        """Charge les apps enregistrées dans apps.json."""
        import importlib.util, json
        from pathlib import Path

        registry_file = Path("apps.json")
        if not registry_file.exists():
            return

        try:
            with open(registry_file, encoding="utf-8") as f:
                registry = json.load(f)
        except Exception:
            return

        for app_id, app_info in registry.get("apps", {}).items():
            # Ignorer les apps déjà chargées
            if app_id in self._apps:
                continue
            # Ignorer les apps non installées
            if app_info.get("status") not in ("active", "installed"):
                continue
            # Charger le connecteur
            connector_path = app_info.get("connector")
            if not connector_path:
                continue
            try:
                spec   = importlib.util.spec_from_file_location(f"app_{app_id}", connector_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                # Trouver la classe Connector
                connector_class = None
                for name in dir(module):
                    if name.endswith("Connector") and not name.startswith("_"):
                        connector_class = getattr(module, name)
                        break
                if connector_class:
                    self._apps[app_id] = connector_class(self.memory)
                    logger.info("App dynamique chargée: %s", app_id)
            except Exception as e:
                logger.warning("Impossible de charger %s: %s", app_id, e)

    def reload_apps(self) -> None:
        """Recharge toutes les apps (après discover)."""
        self._apps = {}
        self._load_apps()
        logger.info("Apps rechargées: %s", list(self._apps.keys()))

    def route(self, text: str, image_b64: str | None = None,
              image_mime: str = "image/jpeg") -> dict:
        """
        Route une requête vers la bonne app.
        
        Returns:
            {
                "app":      str,
                "action":   str,
                "params":   dict,
                "result":   str,   # résultat brut de l app
                "response": str,   # réponse courte pour vocal/UI
                "url":      str | None,  # URL page de résultat
            }
        """
        # 1. Demander au cerveau IA quelle app appeler
        routing_response = self.brain.think(
            prompt     = text,
            system     = ROUTER_SYSTEM,
            image_b64  = image_b64,
            image_mime = image_mime,
        )

        routing = self.brain.parse_json_response(routing_response)
        if not routing:
            routing = {"app": "direct", "action": "answer", "params": {},
                       "response_hint": routing_response}

        app_name   = routing.get("app", "direct")
        action     = routing.get("action", "")
        params     = routing.get("params", {})
        voice_hint = routing.get("response_hint", "")

        # 2. Exécuter l action dans l app
        result_text = ""
        if app_name in self._apps:
            try:
                result_text = self._apps[app_name].execute(action, params)
            except Exception as e:
                logger.error("App %s error: %s", app_name, e)
                result_text = f"Erreur {app_name}: {e}"
        elif app_name == "search":
            result_text = self._universal_search(params.get("keyword", text))
        elif app_name == "memory":
            result_text = self._handle_memory(action, params)

        # 3. Construire la réponse finale
        final_response = voice_hint
        if result_text and len(result_text) > 5:
            # Résumé vocal des résultats (max 2 phrases)
            lines = [l.strip() for l in result_text.splitlines() if l.strip()][:3]
            if lines:
                final_response = voice_hint + " " + " — ".join(lines[:2])

        return {
            "app":      app_name,
            "action":   action,
            "params":   params,
            "result":   result_text,
            "response": final_response.strip(),
            "routing":  routing,
        }

    def _universal_search(self, keyword: str) -> str:
        """Recherche dans toutes les apps simultanément."""
        results = []
        for app_name, connector in self._apps.items():
            try:
                if hasattr(connector, "search"):
                    r = connector.search(keyword)
                    if r:
                        results.append(f"[{app_name.upper()}] {r}")
            except Exception:
                pass
        return "\n".join(results) if results else f"Aucun résultat pour '{keyword}'"

    def _handle_launcher(self, action: str, params: dict) -> str:
        """Gere les actions de demarrage/arret d apps."""
        try:
            from aion_core.discovery.launcher import AppLauncher
            launcher = AppLauncher()

            if action == "start":
                app_id = params.get("app_id", "")
                if not app_id:
                    return "Quel app demarrer ? (ex: demarre quickmind)"
                result = launcher.start_app(app_id)
                return result.get("message", "Demarre")

            if action == "stop":
                app_id = params.get("app_id", "")
                result = launcher.stop_app(app_id)
                return result.get("message", "Arrete")

            if action == "configure":
                result = launcher.configure_autostart(
                    app_id  = params.get("app_id", ""),
                    enabled = params.get("enabled", True),
                    mode    = params.get("mode", "fastapi"),
                    path    = params.get("path", ""),
                    port    = int(params.get("port", 0)),
                    order   = int(params.get("order", 99)),
                )
                if params.get("enabled", True) and result.get("success"):
                    start = launcher.start_app(params.get("app_id", ""))
                    return result.get("message", "") + " -- " + start.get("message", "")
                return result.get("message", "Configure")

            if action == "status":
                apps  = launcher.status()
                lines = ["Statut des apps :"]
                for a in apps:
                    icon = "OK" if a.get("running") else "OFF"
                    name = a.get("name", a.get("app_id", "?"))
                    mode = a.get("mode", "")
                    lines.append("  [" + icon + "] " + name + " (" + mode + ")")
                return chr(10).join(lines)

        except Exception as e:
            return "Erreur launcher: " + str(e)

        return "Action launcher inconnue: " + action

    def _handle_memory(self, action: str, params: dict) -> str:
        """
        Gere toutes les actions memoire AION.

        Actions supportees :
          remember    : memorise une cle/valeur
          recall      : recupere une valeur
          forget      : supprime une cle
          list        : liste toutes les cles (ou par type)
          import_json : importe un dict JSON {key:val} ou {key:{value,type}} en memoire
          clear_type  : supprime toutes les cles d'un type donne
          stats       : statistiques de la memoire
        """
        # ── remember ──────────────────────────────────────────────
        if action in ("remember", "set", "save", "store", "add", "memorise"):
            key  = params.get("key", "") or params.get("name", "")
            val  = params.get("value", "") or params.get("val", "")
            mtype = params.get("type", "info")
            if not key:
                return "Cle manquante. Ex: souviens-toi que mon projet = AION"
            if not val:
                return f"Valeur manquante pour la cle '{key}'"
            self.memory.remember(key, str(val), mtype)
            return f"\u2705 Memorise : {key} = {val}"

        # ── recall ────────────────────────────────────────────────
        elif action in ("recall", "get", "what_is", "valeur", "rappel"):
            key = params.get("key", "") or params.get("name", "")
            if not key:
                return "Quelle cle veux-tu rappeler ?"
            val = self.memory.recall(key)
            return f"{key} = {val}" if val else f"Aucune memoire pour '{key}'"

        # ── forget ────────────────────────────────────────────────
        elif action in ("forget", "delete", "remove", "oublie", "supprime"):
            key = params.get("key", "") or params.get("name", "")
            if not key:
                return "Quelle cle supprimer ?"
            ok = self.memory.forget(key)
            return f"\U0001f5d1 Oublie : {key}" if ok else f"Cle '{key}' introuvable"

        # ── list ──────────────────────────────────────────────────
        elif action in ("list", "show", "all", "liste", "affiche", "display"):
            mtype = params.get("type", None)
            mem   = self.memory.list_memory(mtype)
            if not mem:
                return "Memoire vide." if not mtype else f"Aucune memoire de type '{mtype}'"
            lines = [f"\U0001f9e0 Memoire AION ({len(mem)} entree(s)) :"]
            for k, v in list(mem.items())[:20]:
                val_short = str(v.get("value", ""))[:50]
                lines.append(f"  {k}: {val_short}")
            if len(mem) > 20:
                lines.append(f"  ... et {len(mem)-20} autres")
            return "\n".join(lines)

        # ── import_json ───────────────────────────────────────────
        elif action in ("import_json", "import", "bulk_import", "charger", "load"):
            data = params.get("data", params.get("json", params.get("content", {})))
            if isinstance(data, str):
                import json
                try:
                    data = json.loads(data)
                except Exception:
                    return "JSON invalide. Fournis un dictionnaire {cle: valeur}"
            if not isinstance(data, dict):
                return "Format invalide. Attends un dictionnaire {cle: valeur}"

            imported = []
            skipped  = []
            for k, v in data.items():
                if k.startswith("_"):
                    skipped.append(k)
                    continue
                if isinstance(v, dict) and "value" in v:
                    self.memory.remember(k, str(v["value"]), v.get("type", "imported"))
                elif isinstance(v, (str, int, float, bool)):
                    self.memory.remember(k, str(v), "imported")
                else:
                    skipped.append(k)
                    continue
                imported.append(k)

            msg = f"\u2705 {len(imported)} cle(s) importee(s) en memoire"
            if imported:
                msg += f"\nCles : {", ".join(imported[:8])}"
                if len(imported) > 8:
                    msg += f" +{len(imported)-8} autres"
            if skipped:
                msg += f"\n\u23ed Ignorees : {", ".join(skipped[:5])}"
            return msg

        # ── stats ─────────────────────────────────────────────────
        elif action in ("stats", "info", "status"):
            s = self.memory.stats()
            lines = [
                f"\U0001f9e0 Memoire AION :",
                f"  Total     : {s.get('total', 0)} entrees",
                f"  Temporaire: {s.get('temporary_total', 0)} entrees",
            ]
            for t, n in s.get("by_type", {}).items():
                lines.append(f"  Type '{t}': {n}")
            return "\n".join(lines)

        # ── clear par type ────────────────────────────────────────
        elif action in ("clear_type", "clear"):
            mtype = params.get("type", "imported")
            mem   = self.memory.list_memory(mtype)
            for k in list(mem.keys()):
                self.memory.forget(k)
            return f"\U0001f5d1 {len(mem)} entree(s) de type '{mtype}' supprimee(s)"

        return f"Action memoire inconnue : '{action}'. Actions : remember, recall, forget, list, import_json, stats"

    @property
    def available_apps(self) -> list[str]:
        return list(self._apps.keys())
