# AION-Core 🤖

**AI-First Personal Orchestrator**
*One IA brain. All your apps. Voice, Web, API.*

---

## Vision

AION-Core est la refonte complète d'AION — une plateforme d'orchestration personnelle
où l'IA (Groq) est le **point d'entrée unique** pour gérer toutes tes applications.

```
Tu parles / Tu tapes
        ↓
   🤖 AION IA (Groq)
        ↓
┌───────┬────────────┬────────┬──────────┐
│  QM   │ ProjectMnd │  ADO   │  Sys     │
│ Tasks │  Gantt     │ Items  │  Monitor │
└───────┴────────────┴────────┴──────────┘
```

## Architecture

```
aion_core/
├── ai/              ← Cerveau IA (Groq, routing, mémoire)
├── apps/            ← Connecteurs applications
│   ├── quickmind/
│   ├── projectmind/
│   ├── ado/
│   └── system/
├── api/             ← FastAPI (dashboard + voice + REST)
├── services/        ← Services AION (domaine_action)
├── memory/          ← Mémoire persistante
└── web/             ← Frontend (htmx + Jinja2)
```

## Phases de développement

### Phase 1 — IA Centrale *(en cours)*
- [x] Structure du projet
- [ ] Groq Router intelligent
- [ ] Connecteurs apps (QM, ProjectMind, ADO)
- [ ] Voice API v2 avec page résultat
- [ ] Mémoire contextuelle enrichie

### Phase 2 — QuickMind Web
- [ ] Refonte complète en interface web
- [ ] Kanban drag & drop
- [ ] Éditeur tâches complet
- [ ] Pièces jointes web

### Phase 3 — App Discovery
- [ ] AION peut lire un repo GitHub
- [ ] Auto-intégration de nouvelles apps
- [ ] Création d'app simple par IA

## Stack technique

| Composant | Technologie |
|---|---|
| IA | Groq — llama-3.3-70b-versatile |
| Backend | FastAPI + Python 3.12 |
| Frontend | htmx + Jinja2 (no React overhead) |
| DB | SQLite (simple, portable) |
| Mémoire | JSON persistant |
| Voice | Groq + iPhone Raccourcis |
| Docker | Services tiers uniquement |
| Notifications | plyer (Windows) |

## Démarrage rapide

```bash
git clone https://github.com/beyp/AION-Core
cd AION-Core
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Ajouter GROQ_API_KEY dans .env
python main.py
```

## Héritage AION v0.7

AION-Core réutilise et améliore les meilleurs éléments d'AION :
- Domain Router (commandes naturelles)
- Memory Manager
- Services système (net, sys, ado, qm, timer...)
- Groq Client
- Notifications

---

*Par Pascal Bey — Premier Tech*
