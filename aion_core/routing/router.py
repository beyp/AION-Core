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
- memory     : mémoire AION (remember, recall, forget)
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
"timer 25 minutes" → {"app":"timer","action":"start","params":{"duration":"25m","message":"Temps écoulé !"},"confidence":0.99,"response_hint":"Timer 25 minutes lancé."}
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
        """Charge les connecteurs d apps disponibles."""
        from aion_core.apps.quickmind.connector  import QuickMindConnector
        from aion_core.apps.ado.connector         import ADOConnector
        from aion_core.apps.system.connector      import SystemConnector
        from aion_core.apps.timer.connector       import TimerConnector

        self._apps = {
            "quickmind": QuickMindConnector(self.memory),
            "ado":       ADOConnector(self.memory),
            "system":    SystemConnector(),
            "timer":     TimerConnector(self.memory),
        }
        logger.info("Apps chargées: %s", list(self._apps.keys()))

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

    def _handle_memory(self, action: str, params: dict) -> str:
        """Gère les actions mémoire."""
        if action == "remember":
            key = params.get("key", "")
            val = params.get("value", "")
            if key and val:
                self.memory.remember(key, val)
                return f"Mémorisé : {key} = {val}"
        elif action == "recall":
            key = params.get("key", "")
            val = self.memory.recall(key)
            return f"{key} = {val}" if val else f"Aucune mémoire pour '{key}'"
        elif action == "forget":
            key = params.get("key", "")
            return f"Oublié : {key}" if self.memory.forget(key) else f"Clé '{key}' introuvable"
        return "Action mémoire non reconnue"

    @property
    def available_apps(self) -> list[str]:
        return list(self._apps.keys())
