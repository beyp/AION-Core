# AION-Core — Changelog

## Phase 2 — QuickMind Web UI (En cours)

### Nouvelles fonctionnalités
- **QuickMind Web complet** — Remplace l interface Tkinter
  - Vue liste avec filtres (priorité, statut, catégorie)
  - Layout 2 colonnes (liste + détail)
  - Ajout de tâches inline
  - Sous-tâches avec progression
  - Marquer Done / Supprimer via htmx (sans rechargement)
  - Détail tâche en temps réel
- **Connecteur QuickMind enrichi**
  - Toutes les opérations CRUD
  - Sous-tâches
  - Catégories
  - Archives
  - Recherche dans titres + descriptions

### Architecture
- Fichiers ajoutés :
  - `aion_core/api/quickmind_routes.py` — Routes htmx QuickMind
  - `aion_core/web/templates/quickmind.html` — Template web
  - `aion_core/apps/quickmind/connector.py` — Connecteur complet

## Phase 1 — Fondations IA (Terminé)

### Fonctionnalités
- Cerveau IA Groq (llama-3.3-70b + llama-4-scout vision)
- Router intelligent (intent → app)
- Connecteurs : QuickMind, ADO, System, Timer
- Mémoire persistante JSON
- Voice API + page résultat mobile
- Dashboard web (FastAPI + htmx)
- IA Chat avec images
- Tests unitaires

## Roadmap

### Phase 3 — App Discovery
- [ ] AION lit un repo GitHub et intègre une nouvelle app
- [ ] Création d app simple par IA
- [ ] Registre d apps (apps.json)

### Phase 4 — Enrichissements
- [ ] ProjectMind intégré
- [ ] Notifications temps réel (WebSocket)
- [ ] Mobile-first design
