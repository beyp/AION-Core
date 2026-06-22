# Gestion des données d'apps dans AION-Core

## Où sont stockées les données ?

### Situation idéale (app compatible AION)
L'app lit `os.getenv("AION_DATA_DIR")` et stocke sa DB là :
```
C:\AION_APPS\appdata\quickmind\quickmind.db   ← données
C:\AION_APPS\repos\QuickMind\                 ← code uniquement
```

### Situation actuelle (app non modifiée)
L'app crée sa DB dans son propre dossier :
```
C:\AION_APPS\repos\QuickMind\data\quickmind.db  ← données DANS le repo
```
AION copie ce fichier vers appdata/ via le bouton **Scan AppData** après le premier lancement.

## Workflow recommandé après installation

1. Installer l'app via `/store`
2. Cliquer **▶ Start**
3. Attendre 5-10 secondes que l'app démarre et crée sa DB
4. Cliquer **🔍 Scan AppData** → AION détecte et sauvegarde les fichiers
5. Les données sont maintenant dans `C:\AION_APPS\appdata\<app_id>\`

## Rendre une app compatible AION

Ajouter dans le code de l'app :
```python
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("AION_DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "quickmind.db"
```

AION injecte automatiquement `AION_DATA_DIR=C:\AION_APPS\appdata\<app_id>` 
au démarrage de chaque app via `autostart.env`.
