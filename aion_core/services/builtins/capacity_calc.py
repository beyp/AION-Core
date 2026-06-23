"""
capacity_calc.py — Service AION : Calcul de capacité projet.

Calcule la charge de travail quotidienne pour une tâche donnée
en fonction de sa durée, du nombre de personnes et de leur répartition.

Exemples d'utilisation via l'IA :
  "1 tâche de 20 jours, 2 personnes, 50/50"
  "tâche 15 jours, 1 personne"
  "capacity 30 jours, 3 personnes, 60/20/20"
"""
from __future__ import annotations
import math
from typing import Any


# ── Constantes ────────────────────────────────────────────────────────────────
HOURS_PER_DAY   = 8.0   # heures de travail par jour
WORK_DAYS_WEEK  = 5     # jours ouvrables par semaine


class Service:
    """
    Service AION — Calcul de capacité projet.

    Contrat :
      name        : identifiant unique (snake_case)
      description : phrase courte affichée dans /api/services
      actions     : liste des actions disponibles
      execute()   : point d'entrée unique
    """

    name        = "capacity_calc"
    description = "Calcul de charge quotidienne par personne sur une tâche projet"
    actions     = ["calculate", "help"]

    # ── Point d'entrée ─────────────────────────────────────────────────────────
    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Dispatch vers la bonne méthode selon l'action.

        Args:
            action : "calculate" | "help"
            params : dict libre selon l'action

        Returns:
            dict avec toujours {"success": bool, "message": str, ...}
        """
        if action == "help":
            return self._help()
        if action in ("calculate", "calc", "capacity", "charge"):
            return self._calculate(params)
        return {
            "success": False,
            "message": f"Action '{action}' inconnue. Actions disponibles : {self.actions}",
        }

    # ── Action : calculate ─────────────────────────────────────────────────────
    def _calculate(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Calcule la charge quotidienne pour une tâche.

        Params attendus :
            duration_days  (int)   : durée de la tâche en jours ouvrables
            people         (int)   : nombre de personnes (défaut: 1)
            split          (str)   : répartition ex "50/50", "80/20", "60/20/20"
                                     Si absent -> répartition égale
            hours_per_day  (float) : heures de travail/jour (défaut: 8.0)
            task_name      (str)   : nom optionnel de la tâche

        Retourne :
            {
              "success": True,
              "message": str,           # résumé texte pour l'IA Chat
              "task_name": str,
              "duration_days": int,
              "total_hours": float,     # charge totale de la tâche
              "people": int,
              "split_pct": [float],     # répartition en %
              "daily_hours": [float],   # heures/jour par personne
              "weeks": float,           # durée en semaines
            }
        """
        # ── Extraction et validation des paramètres ────────────────────────────
        try:
            duration_days = int(params.get("duration_days", params.get("days", params.get("duration", 0))))
        except (TypeError, ValueError):
            duration_days = 0

        if duration_days <= 0:
            return {"success": False, "message": "Paramètre manquant : duration_days (nombre de jours de la tâche)."}

        try:
            people = int(params.get("people", params.get("persons", params.get("nb_people", 1))))
        except (TypeError, ValueError):
            people = 1
        people = max(1, people)

        hours_per_day = float(params.get("hours_per_day", HOURS_PER_DAY))
        task_name     = str(params.get("task_name", params.get("task", params.get("name", "Tâche")))).strip()

        # ── Répartition (split) ────────────────────────────────────────────────
        split_raw = params.get("split", params.get("repartition", params.get("distribution", "")))
        split_pct = self._parse_split(split_raw, people)

        if split_pct is None:
            return {
                "success": False,
                "message": f"Répartition invalide '{split_raw}'. "
                           f"Format attendu: '50/50', '80/20', '60/20/20'... "
                           f"Le total doit faire 100%.",
            }

        # ── Calculs ────────────────────────────────────────────────────────────
        total_hours      = duration_days * hours_per_day          # charge totale tâche
        weeks            = duration_days / WORK_DAYS_WEEK

        # Heures par jour pour chaque personne
        daily_hours = [round((pct / 100.0) * hours_per_day, 2) for pct in split_pct]

        # Charge totale accumulée par personne sur toute la durée
        total_hours_per_person = [round(dh * duration_days, 2) for dh in daily_hours]

        # ── Message texte pour l'IA Chat ──────────────────────────────────────
        lines = [
            f"📋 **{task_name}** — {duration_days} jours ({weeks:.1f} semaines)",
            f"👥 {people} personne(s) | {hours_per_day}h/jour",
            "",
        ]

        for i, (pct, dh, th) in enumerate(zip(split_pct, daily_hours, total_hours_per_person), 1):
            lines.append(f"  Personne {i} ({pct:.0f}%) : **{dh}h/jour** → {th}h total")

        lines += [
            "",
            f"⏱ Charge totale tâche : **{total_hours}h**",
        ]

        # Alerte surcharge (> 8h/jour pour une personne)
        warnings = []
        for i, dh in enumerate(daily_hours, 1):
            if dh > hours_per_day:
                warnings.append(f"⚠️ Personne {i} dépasse {hours_per_day}h/jour ({dh}h) !")
        if warnings:
            lines += [""] + warnings

        message = "\n".join(lines)

        return {
            "success":               True,
            "message":               message,
            "task_name":             task_name,
            "duration_days":         duration_days,
            "weeks":                 round(weeks, 2),
            "total_hours":           total_hours,
            "hours_per_day_config":  hours_per_day,
            "people":                people,
            "split_pct":             split_pct,
            "daily_hours":           daily_hours,
            "total_hours_per_person": total_hours_per_person,
        }

    # ── Action : help ──────────────────────────────────────────────────────────
    def _help(self) -> dict[str, Any]:
        return {
            "success": True,
            "message": (
                "**capacity_calc** — Calcul de charge projet\n\n"
                "**Action :** calculate\n"
                "**Paramètres :**\n"
                "  - duration_days (int) : durée en jours ouvrables\n"
                "  - people        (int) : nombre de personnes (défaut: 1)\n"
                "  - split         (str) : répartition ex '50/50', '80/20' (défaut: égale)\n"
                "  - hours_per_day (float): heures/jour (défaut: 8.0)\n"
                "  - task_name     (str) : nom de la tâche (optionnel)\n\n"
                "**Exemples :**\n"
                "  '1 tâche de 20 jours, 2 personnes, 50/50'\n"
                "  'calcule capacité 15j, 1 personne'\n"
                "  'charge 30 jours, 3 personnes, 60/20/20'"
            ),
            "actions": self.actions,
        }

    # ── Utilitaires ────────────────────────────────────────────────────────────
    @staticmethod
    def _parse_split(split_raw: Any, people: int) -> list[float] | None:
        """
        Parse la répartition et retourne une liste de % validée.

        Exemples :
            "50/50"    → [50.0, 50.0]
            "80/20"    → [80.0, 20.0]
            "60/20/20" → [60.0, 20.0, 20.0]
            ""  + 2p   → [50.0, 50.0]   (répartition égale)
            None+ 1p   → [100.0]
        """
        if not split_raw:
            # Répartition égale
            pct = round(100.0 / people, 4)
            result = [pct] * people
            # Correction arrondi sur le dernier
            result[-1] = round(100.0 - sum(result[:-1]), 4)
            return result

        raw = str(split_raw).strip()
        # Accepter "/" ou ":" ou "," comme séparateur
        for sep in ["/", ":", ","]:
            if sep in raw:
                parts = raw.split(sep)
                break
        else:
            # Un seul nombre → 1 personne à 100%
            try:
                v = float(raw)
                return [100.0] if abs(v - 100.0) < 0.1 else None
            except ValueError:
                return None

        try:
            values = [float(p.strip().rstrip("%")) for p in parts]
        except ValueError:
            return None

        # Validation : somme = 100 (tolérance 0.5%)
        total = sum(values)
        if abs(total - 100.0) > 0.5:
            return None

        # Normaliser à exactement 100
        factor = 100.0 / total
        values = [round(v * factor, 4) for v in values]
        values[-1] = round(100.0 - sum(values[:-1]), 4)

        return values
