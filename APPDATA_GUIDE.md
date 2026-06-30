# Gestion des données d'apps dans AION-Core

## Architecture (à jour — juin 2026)

```
C:/code/python/[App]/          ← TON repo de développement (JAMAIS supprimé par AION)
  data/quickmind.db            ← DB locale (dev)
  .env                         ← config locale (dev)
  config.yaml                  ← config locale (dev)

C:/AION_APPS/
  appdata/[app]/               ← données sauvegardées par AION (hors git)
    quickmind.db               ← copie de backup
    .env                       ← copie de backup
  backups/[app]/               ← backups quotidiens horodatés
    data_backup_2026-06-30/    ← backup du jour
      quickmind.db
      .env
```

---

## Où sont stockées les données ?

### Répertoire de travail
AION utilise **ton repo existant** dans `C:/code/python/[App]` — il ne clone pas
un nouveau repo. Tes données restent là où tu les as toujours eues.

### AppData
`C:/AION_APPS/appdata/[app]/` contient des **copies de sauvegarde** de tes fichiers
importants (.db, .env, config.yaml). Ces copies sont :
- Mises à jour manuellement via le bouton **💾 Backup**
- Mises à jour automatiquement à **18h chaque jour** (configurable via `AION_BACKUP_HOUR`)
- **Jamais dans git** (protégées avec .gitignore)

---

## Workflow recommandé

### Ajouter une app dans l'AppStore

1. Dans `/store`, saisir le chemin `C:/code/python/QuickMind`
2. Cliquer **🔍 Détecter** → AION scanne le dossier et propose les modes de lancement
3. Choisir le mode (FastAPI, Docker, Python...) et le port
4. Cliquer **✅ Confirmer et installer**
5. AION génère `startQuickMind.bat` si absent
6. Cliquer **▶ Start** pour lancer l'app

### Sauvegarder les données

```
▶ Start QuickMind
→ L'app crée data/quickmind.db

💾 Backup (bouton dans /store)
→ Copie vers C:/AION_APPS/backups/quickmind/data_backup_YYYY-MM-DD/
→ Confirmation si backup du jour existe déjà

Le backup quotidien se déclenche automatiquement à 18h.
```

### Restaurer après problème

```
📥 Restaurer (bouton dans /store)
→ Recopie depuis C:/AION_APPS/appdata/quickmind/ vers C:/code/python/QuickMind/
```

---

## Rendre une app compatible AION (optionnel)

Si tu veux que l'app utilise directement le répertoire appdata/ :

```python
import os
from pathlib import Path

# AION injecte AION_DATA_DIR au lancement de l'app
DATA_DIR = Path(os.getenv("AION_DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH  = DATA_DIR / "quickmind.db"
```

AION injecte automatiquement `AION_DATA_DIR=C:/AION_APPS/appdata/[app]`
dans les variables d'environnement au démarrage de chaque app.

---

## Config ⚙️

```ini
# .env AION-Core
AION_CODE_ROOT=C:/code/python     # répertoire racine de tes repos
AION_APPS_ROOT=C:/AION_APPS       # répertoire AION (appdata, backups, etc.)
AION_BACKUP_HOUR=18               # heure du backup quotidien (0-23)
```

---

## Sécurité

| Fichier | Dans git | Supprimé par AION |
|---|---|---|
| `C:/code/python/[App]/` | Selon ton .gitignore | **Jamais** |
| `.env`, `config.yaml` | Non (dans .gitignore) | Jamais |
| `C:/AION_APPS/appdata/` | Non | Jamais |
| `C:/AION_APPS/backups/` | Non | Jamais |
| `apps.local.json` | Non (git-ignoré) | Jamais |
