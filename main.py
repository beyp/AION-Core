"""
AION-Core — Point d entrée principal.
Lance le serveur web + console + systray.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from aion_core.app import AionApp

if __name__ == "__main__":
    app = AionApp()
    app.run()
