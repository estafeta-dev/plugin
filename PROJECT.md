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

## AI providers

Decided by the user on 2026-10-15: every available provider except the
Claude (Pricefx) work account. Agents ask before changing this table.
Providers not listed (for example Cursor, Grok or OpenCode, currently
disabled in T3) are refused until the user adds them.

<!-- estafeta:providers:start -->
| Provider | Allowed | Models | Notes |
| --- | --- | --- | --- |
| claude | orchestrate, consult, review, write | any | Personal account: T3 instance `claudeAgent`, Claude Code, `claude -p` |
| claude-pricefx | none | - | Work account (T3 instance `claude-pricefx`): not for this project |
| codex | orchestrate, consult, review, write | any | T3 tasks and `codex exec` (local login) |
| antigravity | orchestrate, consult, review, write | any | T3 tasks; Gemini models without an API key |
| gemini | consult, review, write | any | `gemini -p`; needs a paid API key, none on this host yet |
<!-- estafeta:providers:end -->

## Run and verify

Python 3.9+ and Git are required.

```sh
python3 scripts/workflow.py check
python3 scripts/test_session.py
python3 scripts/test_workflow.py
python3 scripts/test_relay.py
```
