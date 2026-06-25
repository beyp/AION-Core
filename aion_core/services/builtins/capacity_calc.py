"""
capacity_calc.py -- Service AION : Calcul de capacite projet.
Retourne rows+headers pour affichage en tableau cote droit.
"""
from __future__ import annotations
from typing import Any

HOURS_PER_DAY  = 8.0
WORK_DAYS_WEEK = 5


class Service:
    name        = "capacity_calc"
    description = "Calcul de charge quotidienne par personne sur une tache projet"
    icon        = "📊"
    actions     = ["calculate", "help"]

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "help":
            return {"success": True, "message": (
                "**capacity_calc** -- Calcul de charge projet\n"
                "Params: duration_days, people, split (50/50), hours_per_day, task_name\n"
                "Ex: 20 jours, 2 personnes, 50/50"
            )}
        return self._calculate(params)

    def _calculate(self, params):
        try:
            duration_days = int(params.get("duration_days") or params.get("days") or 0)
        except (TypeError, ValueError):
            duration_days = 0
        if duration_days <= 0:
            return {"success": False, "message": "Parametre manquant: duration_days"}

        try:
            people = max(1, int(params.get("people") or 1))
        except (TypeError, ValueError):
            people = 1

        hours_per_day = float(params.get("hours_per_day") or HOURS_PER_DAY)
        task_name     = str(params.get("task_name") or "Tache").strip()
        weeks         = duration_days / WORK_DAYS_WEEK
        total_hours   = duration_days * hours_per_day

        split_raw = params.get("split") or ""
        split_pct = self._parse_split(split_raw, people)
        if split_pct is None:
            return {"success": False,
                    "message": f"Repartition invalide: {split_raw!r}. Format: 50/50, 80/20..."}

        daily_hours = [round((p / 100.0) * hours_per_day, 2) for p in split_pct]
        total_per   = [round(dh * duration_days, 2) for dh in daily_hours]

        # Message texte (pour IA Chat)
        lines = [
            f"\U0001f4cb {task_name} -- {duration_days}j ({weeks:.1f} sem.)",
            f"\U0001f465 {people} personne(s) | {hours_per_day}h/j | {total_hours}h total",
            "",
        ]
        for i, (pct, dh, th) in enumerate(zip(split_pct, daily_hours, total_per), 1):
            lines.append(f"  Personne {i} ({pct:.0f}%) : {dh}h/j -> {th}h total")
        warnings = [f"\u26a0\ufe0f Personne {i} depasse {hours_per_day}h/j ({dh}h) !"
                    for i, dh in enumerate(daily_hours, 1) if dh > hours_per_day]
        if warnings:
            lines += [""] + warnings

        # Tableau pour affichage web (rows + headers)
        headers = ["Personne", "Repartition", "H / jour", "H total", "Statut"]
        rows = []
        for i, (pct, dh, th) in enumerate(zip(split_pct, daily_hours, total_per), 1):
            status = "\u26a0\ufe0f Surcharge" if dh > hours_per_day else "\u2705 OK"
            rows.append([
                f"Personne {i}",
                f"{pct:.0f} %",
                f"{dh} h/j",
                f"{th} h",
                status,
            ])
        rows.append(["TOTAL", "100 %", f"{hours_per_day} h/j", f"{total_hours} h", ""])

        return {
            "success":      True,
            "message":      "\n".join(lines),
            "headers":      headers,
            "rows":         rows,
            "task_name":    task_name,
            "duration_days": duration_days,
            "weeks":        round(weeks, 2),
            "total_hours":  total_hours,
            "people":       people,
        }

    @staticmethod
    def _parse_split(raw, people):
        if not raw:
            pct    = round(100.0 / people, 4)
            result = [pct] * people
            result[-1] = round(100.0 - sum(result[:-1]), 4)
            return result
        for sep in ["/", ":", ","]:
            if sep in str(raw):
                parts = str(raw).split(sep)
                break
        else:
            return None
        try:
            values = [float(p.strip().rstrip("%")) for p in parts]
        except ValueError:
            return None
        if abs(sum(values) - 100.0) > 0.5:
            return None
        factor = 100.0 / sum(values)
        values = [round(v * factor, 4) for v in values]
        values[-1] = round(100.0 - sum(values[:-1]), 4)
        return values
