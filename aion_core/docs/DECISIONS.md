# Architectural Decisions

## 2026-06-30: App repository migration to AION_CODE_ROOT
- **Decision**: Move official app location from C:\AION_APPS\repos to C:\code\python (AION_CODE_ROOT env var).
- **Rationale**: Consolidate all user code in one place, simplify path management, align with VS Code workspace conventions.
- **Implementation**: Update all service defaults (env_checker, git_status, services_routes) to read AION_CODE_ROOT.
- **Backward compatibility**: AION_APPS_ROOT reserved for internal AION data: appdata, backups, logs.
- **Migration path**: Existing deployments can override via env vars; no code breaking changes.

## 2026-06-30: App manifest standardization (aion_app.yaml)
- **Decision**: Each app can provide an optional aion_app.yaml manifest at its root for standardized configuration.
- **Fields**: name, type, path, port, url, health_endpoint, command, update_command, log_path, env.
- **Rationale**: Reduce registry configuration burden; let apps declare their own metadata.
- **Precedence**: aion_app.yaml (if present) > registry (apps.json / apps.local.json) > auto-detection.
- **Impact**: ProcessManager now reads from manifest + registry instead of hardcoded defaults.

## 2026-06-30: Local app discovery without auto-registration
- **Decision**: AppDiscovery.scan_local_code_root() detects candidate apps but does NOT auto-register them.
- **Rationale**: Users retain control; discovery is a scanning/suggestion tool, not an automatic process.
- **Flow**: Scan → show candidates with suggested config → user approves → register via API.
- **Implementation**: Returns list of dicts with app_id, path, manifest, indicators, suggested_config.

## 2026-06-30: Initialize the repository for agent-assisted development
- Added repository guidance files to make future work easier to understand and safer to execute.
- Kept the scope documentation-focused to avoid changing runtime behavior.

## Python-first backend with FastAPI and Jinja2
- The core app is implemented in Python so it remains easy to run on Windows and in VS Code terminals.
- FastAPI provides the web API surface, while Jinja2 templates keep the UI lightweight.

## Windows-first startup workflow
- The project uses PowerShell-friendly commands and batch wrappers such as [startaion.bat](../../startaion.bat) and [install_startup.bat](../../install_startup.bat).
- This choice keeps the local developer experience aligned with the target environment.

## Environment-driven configuration
- Runtime configuration is loaded from environment variables and shared config files rather than embedding secrets in code.
- This keeps the app portable and supports local development and deployment with minimal changes.
