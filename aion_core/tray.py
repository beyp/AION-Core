"""
tray.py -- Icone systray Windows pour AION-Core.

Fonctionnalites :
- Icone dans la barre des taches Windows
- Menu clic droit : Ouvrir, Apps, Services, Quitter
- Clic gauche : ouvre le dashboard dans le navigateur
- Notification au demarrage
- Lance/arrete proprement AION-Core
"""
import os
import sys
import threading
import webbrowser
from pathlib import Path


def _get_icon():
    """Charge l'icone depuis les fichiers statiques."""
    from PIL import Image
    icon_path = Path(__file__).parent / "web" / "static" / "icon.png"
    if icon_path.exists():
        return Image.open(str(icon_path))
    # Fallback : generer une icone simple
    img  = Image.new("RGBA", (64, 64), (15, 17, 23, 255))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], outline=(30, 144, 255, 255), width=4)
    d.text((16, 18), "AI", fill=(30, 144, 255, 255))
    return img


def _open_url(path="/"):
    """Ouvre une URL dans le navigateur par defaut."""
    port = int(os.getenv("AION_PORT", "8000"))
    webbrowser.open(f"http://localhost:{port}{path}")


def run_tray(aion_app=None, port: int = 8000):
    """
    Lance l'icone systray en thread daemon.
    Doit etre appele depuis le thread principal apres le demarrage d'uvicorn.

    Args:
        aion_app : instance AionApp (pour stop propre)
        port     : port du serveur web
    """
    try:
        import pystray
        from pystray import MenuItem as Item, Menu
    except ImportError:
        # pystray non disponible (Linux sans display, etc.)
        return

    def _open(_icon=None, _item=None):
        webbrowser.open(f"http://localhost:{port}")

    def _open_store(_icon=None, _item=None):
        webbrowser.open(f"http://localhost:{port}/store")

    def _open_services(_icon=None, _item=None):
        webbrowser.open(f"http://localhost:{port}/services")

    def _open_docker(_icon=None, _item=None):
        webbrowser.open(f"http://localhost:{port}/docker")

    def _open_chat(_icon=None, _item=None):
        webbrowser.open(f"http://localhost:{port}/chat")

    def _quit(icon, _item=None):
        icon.stop()
        # Arret propre d'AION
        if aion_app:
            try:
                if hasattr(aion_app, "launcher"):
                    aion_app.launcher.stop_all()
            except Exception:
                pass
        os._exit(0)

    menu = Menu(
        Item("🤖 AION-Core", _open, default=True),
        Menu.SEPARATOR,
        Item("📊 Dashboard",  _open),
        Item("🤖 IA Chat",    _open_chat),
        Item("🏪 App Store",  _open_store),
        Item("🐳 Docker",     _open_docker),
        Item("⚡ Services",   _open_services),
        Menu.SEPARATOR,
        Item("❌ Quitter AION-Core", _quit),
    )

    icon = pystray.Icon(
        name  = "AION-Core",
        icon  = _get_icon(),
        title = f"AION-Core — http://localhost:{port}",
        menu  = menu,
    )

    # Notification de demarrage
    def _notify():
        import time
        time.sleep(2)
        try:
            icon.notify(
                title   = "AION-Core démarré",
                message = f"Dashboard : http://localhost:{port}",
            )
        except Exception:
            pass

    t = threading.Thread(target=_notify, daemon=True, name="tray-notify")
    t.start()

    # Lancer le tray (bloquant — doit tourner dans un thread)
    icon.run()


def run_tray_background(aion_app=None, port: int = 8000):
    """Lance le systray dans un thread daemon (non bloquant)."""
    if sys.platform != "win32":
        return  # Systray Windows seulement
    t = threading.Thread(
        target = run_tray,
        args   = (aion_app, port),
        daemon = True,
        name   = "aion-tray",
    )
    t.start()
    return t
