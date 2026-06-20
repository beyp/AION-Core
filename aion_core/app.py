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
    
    Responsabilités :
    - Initialiser tous les composants
    - Démarrer le serveur web (FastAPI)
    - Gérer le cycle de vie
    """

    VERSION = "1.0.0"

    def __init__(self) -> None:
        self._setup_logging()
        logger.info("AION-Core v%s starting...", self.VERSION)

        # Composants (initialisés dans _init_components)
        self.memory    = None
        self.scheduler = None
        self.notifier  = None
        self.router    = None
        self.ai        = None

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
        from aion_core.memory.manager import MemoryManager
        from aion_core.ai.brain import AionBrain
        from aion_core.routing.router import AppRouter

        self.memory    = MemoryManager()
        self.brain     = AionBrain()
        self.app_router = AppRouter(self.brain, self.memory)

        # App Discovery — Phase 3
        from aion_core.discovery.app_discovery import AppDiscovery
        self.discovery = AppDiscovery(self.brain, self.memory)
        logger.info("Composants initialisés — Apps: %s",
                    [a["id"] for a in self.discovery.list_apps()])

    def run(self) -> None:
        """Lance AION-Core."""
        import uvicorn
        from aion_core.api.server import create_app

        host = os.getenv("AION_HOST", "0.0.0.0")
        port = int(os.getenv("AION_PORT", "8000"))

        print(f"\n{'='*50}")
        print(f"  🤖 AION-Core v{self.VERSION}")
        print(f"  AI-First Personal Orchestrator")
        print(f"{'='*50}")
        print(f"  Dashboard : http://localhost:{port}")
        print(f"  Voice API : http://localhost:{port}/api/voice")
        print(f"  API Docs  : http://localhost:{port}/docs")
        print(f"{'='*50}\n")

        app = create_app(self)

        # Lancer les apps autostart en arriere-plan
        import threading
        def _autostart():
            logger.info("Demarrage des apps autostart...")
            results = self.launcher.start_all()
            for app_id, result in results.items():
                status = "OK" if result.get("success") else "ECHEC"
                logger.info("  Autostart %s: %s -- %s",
                            app_id, status, result.get("message", ""))
        t = threading.Thread(target=_autostart, daemon=True, name="autostart")
        t.start()

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
        )
