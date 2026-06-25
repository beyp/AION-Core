"""System Connector — Infos systeme + controle energie."""
import logging
import platform
import sys
from datetime import datetime

logger = logging.getLogger(__name__)


class SystemConnector:
    """Connecteur systeme — CPU, RAM, disques, reseau, uptime, veille."""

    def execute(self, action: str, params: dict) -> str:
        actions = {
            "cpu_ram":   self.cpu_ram,
            "disk":      self.disk,
            "uptime":    self.uptime,
            "info":      self.info,
            "network":   self.network,
            "myip":      self.myip,
            "sleep":     self.sleep,
            "hibernate": self.hibernate,
            "status":    self.status,
        }
        fn = actions.get(action, self.info)
        return fn(params)

    def cpu_ram(self, params: dict = None) -> str:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            return (f"CPU : {cpu:.1f}% | "
                    f"RAM : {ram.used/1e9:.1f}/{ram.total/1e9:.1f} GB ({ram.percent:.1f}%)")
        except ImportError:
            return "psutil non installe."

    def disk(self, params: dict = None) -> str:
        try:
            import psutil
            lines = []
            for p in psutil.disk_partitions():
                try:
                    u = psutil.disk_usage(p.mountpoint)
                    alert = " \u26a0\ufe0f" if u.percent >= 85 else ""
                    lines.append(f"  {p.device} : {u.used/1e9:.1f}/{u.total/1e9:.1f} GB ({u.percent:.1f}%){alert}")
                except Exception:
                    pass
            return "Disques :\n" + "\n".join(lines)
        except ImportError:
            return "psutil non installe."

    def uptime(self, params: dict = None) -> str:
        try:
            import psutil
            boot  = datetime.fromtimestamp(psutil.boot_time())
            delta = datetime.now() - boot
            h, r  = divmod(int(delta.total_seconds()), 3600)
            m, s  = divmod(r, 60)
            return f"Uptime : {delta.days}j {h%24:02d}h {m:02d}m | Demarrage : {boot.strftime('%d/%m %H:%M')}"
        except ImportError:
            return "psutil non installe."

    def info(self, params: dict = None) -> str:
        return (f"OS : {platform.system()} {platform.release()} | "
                f"Python : {sys.version.split()[0]}")

    def network(self, params: dict = None) -> str:
        import socket
        hostname = socket.gethostname()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "inconnu"
        return f"Machine : {hostname} | IP locale : {local_ip}"

    def myip(self, params: dict = None) -> str:
        try:
            import requests as _req
            r = _req.get("https://api.ipify.org?format=json", timeout=5)
            return f"IP publique : {r.json()['ip']}"
        except Exception:
            return "IP publique indisponible."

    def status(self, params: dict = None) -> str:
        """Retourne un resume complet du systeme."""
        lines = [
            self.info(),
            self.cpu_ram(),
            self.uptime(),
            self.network(),
        ]
        return "\n".join(lines)

    def sleep(self, params: dict = None) -> str:
        """
        Met le PC en veille simple (Sleep/Suspend).
        RAM conservee, reveil rapide (~2s).
        Windows : rundll32 powrprof.dll,SetSuspendState 0,1,0
        """
        import subprocess, sys as _sys
        if _sys.platform != "win32":
            return "\u274c Veille simple : Windows uniquement."
        try:
            subprocess.Popen(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
                shell=False
            )
            return "\U0001f4a4 Mise en veille simple dans quelques secondes..."
        except Exception as e:
            return f"\u274c Erreur veille simple : {e}"

    def hibernate(self, params: dict = None) -> str:
        """
        Met le PC en veille prolongee (Hibernate).
        RAM sauvegardee sur disque, coupure totale, reveil ~15s.
        Windows : shutdown /h
        """
        import subprocess, sys as _sys
        if _sys.platform != "win32":
            return "\u274c Veille prolongee : Windows uniquement."
        try:
            # Verifier si l'hibernation est activee
            check = subprocess.run(
                ["powercfg", "/availablesleepstates"],
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            if "Mise en veille prolongee" not in check.stdout and "Hibernate" not in check.stdout:
                # Activer l'hibernation d'abord
                subprocess.run(["powercfg", "/hibernate", "on"], capture_output=True)

            subprocess.Popen(["shutdown", "/h"], shell=False)
            return "\U0001f4be Mise en veille prolongee dans quelques secondes... (sauvegarde RAM)"
        except Exception as e:
            return f"\u274c Erreur veille prolongee : {e}"
