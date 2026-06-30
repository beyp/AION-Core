# Architecture

## Overview
AION-Core is a Windows-friendly personal orchestration app built around a Python backend and a lightweight web UI. The runtime is centered on a single application bootstrap that initializes AI, routing, discovery, persistence, and startup helpers.

## Runtime flow
1. [main.py](../main.py) loads environment variables and starts the application.
2. [aion_core/app.py](../app.py) initializes the main components.
3. [aion_core/ai/brain.py](../ai/brain.py) provides the core AI interface.
4. [aion_core/routing/router.py](../routing/router.py) routes user intent to the right connector.
5. Connectors under [aion_core/apps](../apps) perform app-specific actions.
6. The web API under [aion_core/api](../api) exposes the dashboard and service endpoints.

## Key subsystems
- AI and reasoning: [aion_core/ai](../ai)
- App connectors: [aion_core/apps](../apps)
- Memory and persistence: [aion_core/memory](../memory)
- Discovery and startup: [aion_core/discovery](../discovery)
- Store and config management: [aion_core/store](../store)
- Web surface: [aion_core/web](../web)
- Data and runtime state: [data](../../data)

## App management architecture (v2.0)

### Path organization
- **AION_CODE_ROOT** (`C:/code/python` default): Location of user applications (QuickMind, ProjectMind, etc).
- **AION_APPS_ROOT** (`C:/AION_APPS` default): Location of internal AION data (appdata, backups, logs).
- All old references to `C:/AION_APPS/repos` have been updated to use AION_CODE_ROOT.

### App registry system
1. **apps.json**: Built-in app definitions (system apps, defaults).
2. **apps.local.json**: User-installed apps (git-ignored, not committed).
3. **aion_app.yaml** (optional): Per-app manifest at app root. If present, overrides registry config.

### App discovery and launch
- **AppDiscovery.scan_local_code_root()**: Scans AION_CODE_ROOT for candidate apps (looks for aion_app.yaml, main.py, app.py, pyproject.toml, requirements.txt).
- **Returns** suggested configurations WITHOUT auto-registering.
- **ProcessManager.read_app_config()**: Reads app config from registry (apps.local.json → apps.json → auto-detect).
- **ProcessManager.extract_launch_config()**: Extracts launch details (port, command, health_endpoint, update_command, log_path, env) from registry or manifest.

### Service defaults update
- `env_checker.py`, `git_status.py`: Now use `AION_CODE_ROOT` via env var (with fallback).
- `services_routes.py` UI: Defaults changed from `C:/AION_APPS/repos` to `C:/code/python`.
- `store_routes.py`, `router.py`: Use `AION_APPS_ROOT` for appdata paths (not repos).

## Design principles
- Keep the app modular so new connectors can be added without changing the central bootstrap.
- Prefer environment-driven configuration over hard-coded values.
- Keep Windows compatibility in mind for startup scripts, tray behavior, and PowerShell commands.
- Preserve existing behavior and use tests to guard regressions.
- App paths and locations are driven by environment variables, enabling flexible deployment.

## Data and configuration
- Runtime state and local memory live under [data](../../data).
- Shared environment settings are managed through `.env` and the shared config layer.
- App registrations and local overrides are tracked in [apps.json](../../apps.json) and [apps.local.json](../../apps.local.json).
- Per-app configuration can be provided via optional `aion_app.yaml` at the app root.
