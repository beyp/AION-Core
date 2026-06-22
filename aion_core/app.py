"""
AION-Core Application — Orchestrateur principal.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class AionApp:
    """
    Application principale AION-Core.

    Responsabilites :
    - Initialiser tous les composants
    - Demarrer le serveur web (FastAPI)
    - Gerer le cycle de vie
    """

    VERSION = "1.0.0"

    def __init__(self) -> None:
        self._setup_logging()
        logger.info("AION-Core v%s starting...", self.VERSION)

        self.memory     = None
        self.brain      = None
        self.app_router = None
        self.discovery  = None
        self.launcher   = None   # AppLauncher — autostart des apps
        self.updater    = None   # AionUpdater — veille mise a jour AION-Core

        self._init_components()

    def _setup_logging(self) -> None:
        """Configure le logging."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_dir / "aion.log", encoding="utf-8"),
            ],
        )

    def _init_components(self) -> None:
        """Initialise tous les composants."""
        from aion_core.memory.manager       import MemoryManager
        from aion_core.ai.brain             import AionBrain
        from aion_core.routing.router       import AppRouter
        from aion_core.discovery.app_discovery import AppDiscovery
        from aion_core.discovery.launcher   import AppLauncher

        self.memory     = MemoryManager()
        self.brain      = AionBrain()
        self.app_router = AppRouter(self.brain, self.memory)

        # Updater AION-Core
        from aion_core.updater import AionUpdater
        update_mode     = os.getenv("AION_UPDATE_MODE", "notify")
        update_interval = int(os.getenv("AION_UPDATE_INTERVAL", "3600"))
        self.updater    = AionUpdater(mode=update_mode, check_interval=update_interval)
        self.discovery  = AppDiscovery(self.brain, self.memory)
        self.launcher   = AppLauncher()  # lit apps.json + apps.local.json

        logger.info("Composants initialises — Apps: %s",
                    [a["id"] for a in self.discovery.list_apps()])

    def run(self) -> None:
        """Lance AION-Core."""
        import uvicorn
        from aion_core.api.server import create_app

        host = os.getenv("AION_HOST", "0.0.0.0")
        port = int(os.getenv("AION_PORT", "8000"))

        print(f"\n{'='*50}")
        print(f"  \U0001f916 AION-Core v{self.VERSION}")
        print(f"  AI-First Personal Orchestrator")
        print(f"{'='*50}")
        print(f"  Dashboard : http://localhost:{port}")
        print(f"  Voice API : http://localhost:{port}/api/voice")
        print(f"  API Docs  : http://localhost:{port}/docs")
        print(f"{'='*50}\n")

        app = create_app(self)

        # Lancer les apps autostart en arriere-plan (non bloquant)
        import threading

        def _autostart():
            try:
                logger.info("Demarrage des apps autostart...")
                all_results = self.launcher.start_all()
                for app_id, res in all_results.items():
                    status = "OK" if res.get("success") else "ECHEC"
                    logger.info("  Autostart %s: %s -- %s",
                                app_id, status, res.get("message", ""))
            except Exception as exc:
                logger.error("Erreur autostart (non bloquante): %s", exc)

        t = threading.Thread(target=_autostart, daemon=True, name="autostart")
        t.start()

        # Demarrer le watcher de mise a jour AION-Core
        self.updater.start()

        uvicorn.run(app, host=host, port=port, log_level="info")
