# Architectural Decisions

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

## Test strategy
- Pytest is the default test runner for regression coverage.
- New features and fixes should include tests wherever practical, especially for logic-heavy modules.
