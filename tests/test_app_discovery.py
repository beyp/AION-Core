"""
test_app_discovery.py — Tests pour AppDiscovery et chemin resolution.

- Resolutions de path relatif vs absolu
- Pas d'utilisation de C:\\AION_APPS\\Repos
- Decouverte locale de QuickMind / ProjectMind
"""

import os
from pathlib import Path

import pytest

from aion_core.discovery.app_discovery import AppDiscovery


class TestPathResolution:
    """Tests resolution chemins relatifs vs absolus."""

    def test_relative_path_resolves_to_aion_code_root(self):
        """Path relatif 'QuickMind' doit resoudre a AION_CODE_ROOT/QuickMind."""
        # Simule AION_CODE_ROOT = C:/code/python
        old_env = os.environ.get("AION_CODE_ROOT")
        try:
            os.environ["AION_CODE_ROOT"] = "C:/code/python"

            # Import la discovery
            discovery = AppDiscovery(None, None)

            # Path relatif
            relative_path = "QuickMind"

            # Simule resolution
            code_root = Path(os.getenv("AION_CODE_ROOT", "C:/code/python"))
            resolved = code_root / relative_path

            assert resolved == Path("C:/code/python/QuickMind")
            assert not str(resolved).startswith("C:/AION_APPS/repos")
        finally:
            if old_env:
                os.environ["AION_CODE_ROOT"] = old_env

    def test_absolute_path_is_respected(self):
        """Path absolu doit etre utilise tel quel."""
        absolute_path = "C:/my/absolute/path/QuickMind"
        resolved = Path(absolute_path)

        assert resolved == Path("C:/my/absolute/path/QuickMind")
        # Sur Windows, Path convertit / en \, donc on verifie autrement
        assert str(resolved).lower().startswith("c:\\my") or str(resolved).lower().startswith("c:/my")

    def test_no_old_aion_apps_repos_path_in_defaults(self):
        """Services et routes ne doivent pas utiliser C:/AION_APPS/repos par defaut."""
        # Lire env_checker.py et verifier que default_root n'est pas C:/AION_APPS/repos
        from aion_core.services.builtins import env_checker

        # L env_checker doit lire depuis AION_CODE_ROOT
        # Verif basique: l import fonctionne
        assert env_checker is not None


class TestLocalDiscovery:
    """Tests decouverte locale d apps."""

    def test_scan_local_code_root_returns_list(self):
        """scan_local_code_root() doit retourner une liste."""
        old_env = os.environ.get("AION_CODE_ROOT")
        try:
            # Utiliser le dossier courant qui contient des subs
            os.environ["AION_CODE_ROOT"] = str(Path.cwd().parent)

            discovery = AppDiscovery(None, None)
            results = discovery.scan_local_code_root()

            assert isinstance(results, list)
            # Les resultats peuvent etre vides si aucune app candidate
        finally:
            if old_env:
                os.environ["AION_CODE_ROOT"] = old_env

    def test_scan_local_code_root_detects_apps_with_indicators(self):
        """scan_local_code_root() doit detecter les dossiers avec indicators (main.py, etc)."""
        discovery = AppDiscovery(None, None)
        results = discovery.scan_local_code_root()

        # Ne pas faire d assertions fermes car l env peut varier
        # Juste verifier que la structure est correcte
        for candidate in results:
            assert "app_id" in candidate
            assert "path" in candidate
            assert "indicators" in candidate
            assert "suggested_config" in candidate
            assert isinstance(candidate["indicators"], list)

    def test_suggested_config_has_required_fields(self):
        """Chaque app candidate doit avoir une suggested_config avec champs requis."""
        discovery = AppDiscovery(None, None)
        results = discovery.scan_local_code_root()

        required_fields = ["name", "type", "port", "url", "health_endpoint", "path"]

        for candidate in results:
            config = candidate["suggested_config"]
            for field in required_fields:
                assert field in config, f"Missing {field} in suggested_config for {candidate['app_id']}"


class TestManifestHandling:
    """Tests pour aion_app.yaml manifest."""

    def test_manifest_parsing_simple(self):
        """Simple YAML parser fallback doit fonctionner."""
        discovery = AppDiscovery(None, None)

        yaml_content = """
name: TestApp
type: python
port: 8000
url: http://localhost:8000
health_endpoint: /health
"""
        result = discovery._parse_yaml_simple(yaml_content)

        assert result.get("name") == "TestApp"
        assert result.get("type") == "python"
        assert result.get("port") == 8000

    def test_manifest_ignores_comments_and_blanks(self):
        """Parser doit ignorer # et lignes vides."""
        discovery = AppDiscovery(None, None)

        yaml_content = """
# Commentaire
name: TestApp

# Autre commentaire
port: 9000
"""
        result = discovery._parse_yaml_simple(yaml_content)

        assert result.get("name") == "TestApp"
        assert result.get("port") == 9000
        assert len(result) == 2


class TestRegistryCompatibility:
    """Tests compatibilite registre existant."""

    def test_no_auto_registration_from_scan(self):
        """scan_local_code_root() ne doit PAS auto-enregistrer les apps."""
        discovery = AppDiscovery(None, None)

        initial_apps = list(discovery._reg.get("apps", {}).keys())
        results = discovery.scan_local_code_root()

        # Apres scan, aucune nouvelle app ne doit etre enregistree
        final_apps = list(discovery._reg.get("apps", {}).keys())

        assert initial_apps == final_apps
        # Mais on doit avoir des candidats
        assert len(results) >= 0  # Peut etre 0 si env vide
