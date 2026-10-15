# Estafeta

## Purpose and rules

Maintain the portable agent session workflow published at https://github.com/pashbel/estafeta.
Preserve cross-provider compatibility and existing project state. Follow docs/MAINTAINING.md.
Do not publish credentials, local runtime state, or personal logs.

## Documentation map

- Plan: docs/plans/relay-hardening.md (3.1.1); previous: docs/plans/multi-provider.md.
- Handover: HANDOVER.md.
- Installation: docs/INSTALL.md; usage: docs/USAGE.md.
- Maintenance and checks: docs/MAINTAINING.md.
- Workflow: estafeta; machine state in .agent-state/session-workflow is local and ignored by Git.

## Current focus

- Multi-provider relay (3.1.0): skill `agent-relay` and runtime `delegate`; see docs/plans/multi-provider.md.
- On another computer, follow docs/CONTINUING.md, then use session-start.

## Run and verify

Python 3.9+ and Git are required.

```sh
python3 scripts/workflow.py check
python3 scripts/test_session.py
python3 scripts/test_workflow.py
python3 scripts/test_relay.py
```
