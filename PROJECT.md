# Estafeta

## Purpose and rules

Maintain the portable agent session workflow published at https://github.com/pashbel/estafeta.
Preserve cross-provider compatibility and existing project state. Follow docs/MAINTAINING.md.
Do not publish credentials, local runtime state, or personal logs.

## Documentation map

- Plan: none for the current repository synchronization task.
- Handover: HANDOVER.md.
- Installation: docs/INSTALL.md; usage: docs/USAGE.md.
- Maintenance and checks: docs/MAINTAINING.md.
- Workflow: estafeta; machine state in .agent-state/session-workflow is local and ignored by Git.

## Current focus

- Preserve the favicon studies and make the current source and continuation context available through origin/main.
- No new product feature is selected. Continue only with the next requested task.
- On another computer, follow docs/CONTINUING.md, then use session-start.

## Run and verify

Python 3.9+ and Git are required.

```sh
python3 scripts/workflow.py check
python3 scripts/test_session.py
python3 scripts/test_workflow.py
```
