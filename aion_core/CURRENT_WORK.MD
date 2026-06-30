# Current Work

Last updated: 2026-06-30

## Status
- Repository guidance has been initialized for agent-assisted development.
- The main runtime structure and existing test layout have been reviewed.
- The documentation now describes install, run, and test commands for Windows and VS Code.

## Active focus
- Keep future edits behavior-preserving.
- Document the architecture, roadmap, and decisions clearly for long-term maintenance.
- Preserve the current Windows-first startup workflow.

## Known gaps
- The current test suite does not yet cover all runtime modules.
- The app startup and launcher flows still merit regression tests.
- Windows tray and update behavior should be exercised in future work.

## Verification note
- The current pytest run was validated after installing pytest into the project virtual environment.
- A malformed test string in [tests/test_brain.py](../tests/test_brain.py) was corrected so the suite can be collected properly.
