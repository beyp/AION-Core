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

## Design principles
- Keep the app modular so new connectors can be added without changing the central bootstrap.
- Prefer environment-driven configuration over hard-coded values.
- Keep Windows compatibility in mind for startup scripts, tray behavior, and PowerShell commands.
- Preserve existing behavior and use tests to guard regressions.

## Data and configuration
- Runtime state and local memory live under [data](../../data).
- Shared environment settings are managed through `.env` and the shared config layer.
- App registrations and local overrides are tracked in [apps.json](../../apps.json) and [apps.local.json](../../apps.local.json).
