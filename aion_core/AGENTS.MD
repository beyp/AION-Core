# Agent Instructions for AION-Core

This repository is intended for long-term, agent-assisted development. Keep changes small, explicit, and behavior-preserving unless the task explicitly asks for a new feature or a bug fix.

## Operating rules
- Do not change application behavior unless the request requires it.
- Prefer additive changes, regression tests, and documentation updates.
- Keep the setup compatible with Windows PowerShell and VS Code.
- When you make code changes, update the relevant documentation and tests in the same pass.
- Do not create a new git branch if the current branch is already a feature branch.

## Repository map
- Main entry point: [main.py](../main.py)
- Core application bootstrap: [aion_core/app.py](app.py)
- AI brain and routing: [aion_core/ai/brain.py](ai/brain.py) and [aion_core/routing/router.py](routing/router.py)
- App connectors: [aion_core/apps](apps)
- Persistence and config: [aion_core/memory](memory), [aion_core/store](store), [data](../data)
- Tests: [tests](../tests)

## Install, run, and test commands
Run these from the repository root in PowerShell:

```powershell
cd C:\code\python\AION-Core
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the app:

```powershell
python main.py
# or
startaion.bat
```

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
## Project context files

Before changing code, read these files when they exist:

- CURRENT_WORK.md: current branch, active feature, current goals
- docs/ROADMAP.md: planned features and priorities
- docs/ARCHITECTURE.md: architecture and module responsibilities
- docs/DECISIONS.md: important technical decisions

If one of these files is missing or outdated, propose an update before making large code changes.

## Branch policy

Reuse the current feature branch when the requested work belongs to the same topic.

Do not create a new branch unless:
- the user explicitly asks for it
- the work is clearly unrelated
- the current branch is main/master
- the requested work starts a new feature area

Prefer long-lived feature branches for coherent development.

## Testing expectations
- Use pytest with the existing configuration in [pytest.ini](../pytest.ini).
- Add or update tests for any code you change.
- Prefer focused unit tests for memory, routing, connectors, and service helpers.

## Current testing gaps
The current suite covers a subset of the system. Missing coverage includes:
- App startup and lifecycle behavior in [aion_core/app.py](app.py)
- Router dispatch decisions in [aion_core/routing/router.py](routing/router.py) — partially covered (dispatch, but not all paths)
- Discovery and launcher flows in [aion_core/discovery](discovery) — NEW: test_app_discovery.py covers scan_local_code_root, manifest parsing, path resolution
- Backup and updater behavior in [aion_core/store](store) and [aion_core/updater.py](updater.py)
- API route wiring in [aion_core/api](api)
- Windows-specific tray behavior in [aion_core/tray.py](tray.py)

## Notes for future agents
- Keep environment-driven configuration in `.env` and the shared config files under [data](../data).
- Preserve the existing Windows-first workflow and batch wrappers.
- When changing runtime behavior, document the reason and the impact.
