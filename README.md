# AION-Core 🤖

**AI-First Personal Orchestrator**  
*Un cerveau IA. Toutes tes apps. Voice, Web, API.*

---

## Vision

AION-Core est une plateforme d'orchestration personnelle où l'IA (Groq/Llama)
est le **point d'entrée unique** pour gérer toutes tes applications.

```
Tu parles / Tu tapes
        ↓
   🤖 AION IA (Groq llama-3.3-70b)
        ↓
┌───────┬────────────┬────────┬──────────┐
│  QM   │ ProjectMnd │  ADO   │  System  │
│ Tasks │  Gantt     │ Items  │  Monitor │
└───────┴────────────┴────────┴──────────┘
```

---

## Architecture

```
C:/code/python/AION-Core/      ← repo principal
  aion_core/
  ├── ai/          ← Cerveau IA (Groq, routing, mémoire)
  ├── api/         ← FastAPI (dashboard, voice, REST, services)
  ├── apps/        ← Connecteurs (QuickMind, ADO, System, Timer)
  ├── store/       ← AppStore (ProcessManager, BackupManager, ConfigEditor)
  ├── services/    ← Services intégrés (capacity_calc, git_status, ado_search...)
  ├── tray.py      ← Icône systray Windows
  ├── updater.py   ← Auto-update AION-Core
  └── web/         ← Templates Jinja2 + statiques

C:/AION_APPS/                  ← données AION (hors git)
  appdata/[app]/               ← configs et DB sauvegardées
  backups/[app]/               ← backups quotidiens horodatés

C:/code/python/[App]/          ← tes apps (repos existants)
  startQuickMind.bat           ← script de lancement (généré par AION si absent)
```

---

## Démarrage rapide

### Installation

```powershell
cd C:\code\python\AION-Core
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Editer .env avec ta GROQ_API_KEY
```

### Lancement

```powershell
startaion.bat
# → http://localhost:8000
```

### Démarrage automatique Windows

```powershell
# Installe le démarrage automatique au boot Windows
install_startup.bat

# Désinstaller
uninstall_startup.bat
```

### Ouvrir les ports pour Tailscale

```powershell
# En tant qu'administrateur
open_firewall.bat
```

---

## Variables d'environnement (.env)

```ini
# IA
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# Azure DevOps
ADO_PAT=...
ADO_ORG=Premiertech

# AION
AION_HOST=0.0.0.0
AION_PORT=8000
AION_PUBLIC_URL=http://100.102.139.40:8000

# Répertoires
AION_CODE_ROOT=C:/code/python      # tes repos de dev
AION_APPS_ROOT=C:/AION_APPS        # données AION

# Backup quotidien
AION_BACKUP_HOUR=18                # heure du backup (0-23)

# Auto-update
AION_UPDATE_MODE=notify            # notify | auto
AION_UPDATE_INTERVAL=3600          # secondes entre vérifications
```

---

## AppStore

AION-Core gère tes apps via l'AppStore (`/store`) :

| Action | Description |
|---|---|
| 🔍 Détecter | Scanne `C:/code/python/[App]` et détecte le mode de lancement |
| ▶ Start | Lance l'app via `start[App].bat` ou commande détectée |
| ◼ Stop | Stoppe l'app (via PID ou port) |
| ⚙️ Config | Édite `.env` / `config.yaml` — sauvegardé dans `appdata/` |
| 💾 Backup | Sauvegarde les données vers `C:/AION_APPS/backups/` |
| 🔄 Update | `git pull` dans le repo de l'app |
| 🗑️ Supprimer | Retire du registre — **ne supprime JAMAIS** `C:/code/python/[App]` |

---

## Services intégrés (/services)

Scripts Python exécutés directement dans AION (pas de port séparé) :

| Service | Description |
|---|---|
| 📊 capacity_calc | Calcul de charge projet (durée, personnes, répartition) |
| 🔀 git_status | Statut git de tous les repos dans `C:/code/python/` |
| 🔍 env_checker | Vérifie les clés manquantes dans les `.env` |
| 🔵 ado_search | Recherche work items Azure DevOps |

---

## Commandes IA (chat)

```
"lance quickmind"           → démarre QuickMind
"arrete projectmind"        → stoppe ProjectMind
"statut de mes apps"        → liste toutes les apps
"liste les services"        → liste les services disponibles
"supprime le service xxx"   → retire un service
"mets en veille"            → Sleep Windows
"veille prolongée"          → Hibernate Windows
"liste ma mémoire"          → affiche les clés en mémoire
```

---

## Stack technique

- **Backend** : Python 3.12 / FastAPI / Uvicorn
- **IA** : Groq API (llama-3.3-70b-versatile)
- **Frontend** : htmx + Jinja2 (pas de framework JS)
- **Systray** : pystray + Pillow
- **Apps** : QuickMind (FastAPI:8765) / ProjectMind (FastAPI:8766)
- **ADO** : Azure DevOps REST API (org: Premiertech)
