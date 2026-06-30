# AION-Core — Changelog

## v1.0.0 — 2026-06-30 (En cours)

### Architecture
- **AppStore** — Gestion complète des apps locales (`C:/code/python/[App]`)
  - Détection automatique du mode de lancement (FastAPI, Docker, Python)
  - Modal de validation avec liste des options trouvées
  - Vérification du `start[App].bat` existant — génération si absent
  - Ne supprime **jamais** le répertoire de dev lors du "Supprimer"
- **BackupManager** — Backup quotidien automatique à 18h
  - Destination : `C:/AION_APPS/backups/[app]/data_backup_YYYY-MM-DD/`
  - Confirmation avant écrasement si backup du jour existe
  - Restauration depuis un backup spécifique
- **ProcessManager** — Gestion robuste des processus
  - Health check HTTP prioritaire, PID en fallback
  - Génération de `start[App].bat` dans `C:/code/python/[App]`
- **ConfigEditor** — Édition `.env` / `config.yaml` dans `/store`
  - Sauvegardé dans `C:/AION_APPS/appdata/` (hors git)
  - Héritage des clés partagées depuis AION (GROQ_API_KEY, ADO_PAT...)
  - Import depuis `C:/code/python/[App]/.env`

### Nouvelles fonctionnalités
- **Systray Windows** — Icône dans la barre des tâches
  - Menu : Dashboard, IA Chat, App Store, Docker, Services
  - Notification au démarrage
- **Favicon** — Icône AION dans les onglets navigateur
- **Démarrage automatique** — `install_startup.bat` pour le boot Windows
- **Docker Manager** (`/docker`) — Start/Stop/Logs des containers
- **Services** (`/services`) — Scripts Python exécutés directement dans AION
  - capacity_calc, git_status, env_checker, ado_search
- **Auto-update** — Vérification GitHub + git pull + redémarrage même console
- **Sidebar collapse** — Bouton pour réduire/agrandir le menu latéral
- **Veille système** — Sleep et Hibernate via l'IA ou les boutons du header

### Corrections
- Boutons AppStore : réécriture JS avec guillemets doubles (fin des SyntaxError)
- `uninstall()` ne supprime plus `C:/code/python/[App]`
- Health check parallèle (0.5s max) au lieu de séquentiel (6s+)
- Port 8001 AION-Services supprimé — services exécutés directement

---

## v0.9.0 — 2026-06-22

### Architecture initiale
- AppStore avec `C:/AION_APPS/repos/` (remplacé par `C:/code/python/` en v1.0)
- ProcessManager avec PID persisté dans `data/pids.json`
- Router IA : quickmind, ado, system, timer, memory, appctl, service_admin
- Dashboard htmx avec sidebar dynamique depuis `apps.json` + `apps.local.json`
- App proxy (`/app/{id}`) — iframe ou page de contrôle selon le type
- Voice API — endpoint iPhone Raccourcis / Siri

### Apps connectées
- **QuickMind** (FastAPI port 8765) — Gestionnaire de tâches
- **ProjectMind** (FastAPI port 8766) — Gestion de projets Gantt
- **Azure DevOps** — Work items Premiertech (PTG-TMM)
- **System Monitor** — CPU, RAM, disques, réseau
- **Timer** — Compte à rebours avec notification

---

## v0.7.x — 2026-06 (Fondations)

- Point d'entrée vocal FastAPI
- Cerveau IA Groq (llama-3.3-70b-versatile)
- Mémoire persistante JSON
- Connecteur QuickMind + ADO
- Dashboard v1 avec htmx
