"""
AionBrain — Cerveau IA central (Groq).
Point d entrée unique pour toutes les requêtes IA.
"""
import json
import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"


class AionBrain:
    """
    Cerveau IA AION-Core.
    
    Responsabilités :
    - Comprendre l intention de l utilisateur
    - Router vers la bonne app/action
    - Générer des réponses contextuelles
    - Supporter le texte ET les images (Groq vision)
    """

    def __init__(self) -> None:
        self.api_key  = os.getenv("GROQ_API_KEY", "")
        self.model    = GROQ_MODEL
        self.history: list[dict] = []
        self._max_history = 20

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            r = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers=self._headers(),
                timeout=3,
            )
            return r.status_code == 200
        except Exception:
            return False

    def think(
        self,
        prompt:     str,
        system:     str | None = None,
        image_b64:  str | None = None,
        image_mime: str = "image/jpeg",
        use_history: bool = False,
    ) -> str:
        """
        Envoie un prompt au cerveau IA et retourne la réponse.
        
        Args:
            prompt:      Question/commande de l utilisateur
            system:      Prompt système optionnel
            image_b64:   Image en base64 (active le mode vision)
            image_mime:  Type MIME de l image
            use_history: Inclure l historique de conversation
        """
        if not self.api_key:
            return "GROQ_API_KEY non configurée. Ajoute-la dans .env"

        model = GROQ_VISION if image_b64 else self.model

        # Construire le contenu utilisateur
        if image_b64:
            user_content = [
                {"type": "text", "text": prompt or "Analyse cette image."},
                {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}},
            ]
        else:
            user_content = prompt

        # Construire les messages
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        if use_history:
            messages.extend(self.history[-self._max_history:])
        messages.append({"role": "user", "content": user_content})

        try:
            r = requests.post(
                GROQ_URL,
                headers=self._headers(),
                json={
                    "model":       model,
                    "messages":    messages,
                    "temperature": 0.3,
                    "max_tokens":  2048,
                },
                timeout=30,
            )
            r.raise_for_status()
            response = r.json()["choices"][0]["message"]["content"].strip()

            # Mettre à jour l historique
            if use_history:
                self.history.append({"role": "user",      "content": prompt})
                self.history.append({"role": "assistant",  "content": response})

            return response

        except requests.exceptions.HTTPError as e:
            try:
                err = r.json().get("error", {}).get("message", str(e))
            except Exception:
                err = str(e)
            logger.error("Groq error: %s", err)
            return f"Erreur Groq : {err}"
        except Exception as e:
            logger.error("Brain error: %s", e)
            return f"Erreur : {e}"

    def parse_json_response(self, response: str) -> dict | list | None:
        """Extrait le JSON d une réponse Groq."""
        import re
        # Chercher bloc ```json ... ```
        m = re.search(r"```json\s*(.*?)```", response, re.DOTALL)
        if m:
            response = m.group(1).strip()
        elif "```" in response:
            response = response.split("```")[1].strip()
            if response.startswith("json"):
                response = response[4:].strip()
        try:
            return json.loads(response)
        except Exception:
            return None

    def clear_history(self) -> None:
        self.history.clear()

    def list_models(self) -> list[str]:
        try:
            r = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers=self._headers(),
                timeout=5,
            )
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])
                    if not m["id"].startswith("whisper")]
        except Exception:
            return []

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }
