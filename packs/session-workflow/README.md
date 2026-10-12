# Session Workflow 3.0.0

Four skills act on one durable project record:

`session-start → plan-and-orchestrate → session-handover → session-end`

`session-guide` explains all of this to a new user in a few lines and shows
where the project stands, without changing anything. Handover updates can
happen at any milestone; they do not end the session.
Ending a session checkpoints unfinished work and never marks it complete.

## How to invoke

Use the same plain request with any provider; slash or dollar syntax is optional.

| Intent | Example prompt |
| --- | --- |
| Learn how it works | Use session-guide. Explain how this works. |
| Start / resume | Use session-start. Resume the project from its saved checkpoint. |
| Plan only | Use plan-and-orchestrate. Plan this change without implementing it. |
| Execute | Use plan-and-orchestrate. Execute the ready phases of this plan. |
| Record a milestone | Use session-handover. Record the current changes and evidence. |
| End / hand off | Use session-end. Save context to continue on another device. |

## Project record

Existing projects keep their documents. New projects get:

- PROJECT.md: goal, constraints, documentation map, current focus, next action.
- docs/plans/<workstream>.md: acceptance, decisions, phase notes.
- HANDOVER.md: changes and reasons, checks with results, gaps, next steps.
- AGENTS.md / CLAUDE.md: a short pointer to these files.

The runtime keeps execution state (phases, owners, checks, checkpoints) in
`.agent-state/session-workflow`, ignored by Git. The
[contract](shared/workflow-contract.md) holds all shared rules, and the
[quickstart](shared/quickstart.md) holds every command an ordinary session needs.

## Changes in 3.0.0

All changes come from a review of 2.4.1. Each failure listed below was
reproduced first and now has a regression test.

| 2.4.1 problem | 3.0.0 behaviour |
| --- | --- |
| A chat closed without session-end kept its claims forever. | Solo is the default: a new chat in the same checkout takes over the earlier chat's claims and preview servers. A running check proves a session is alive and blocks the takeover. |
| No way to free a crashed parallel or other-machine session. | `release --confirm-stopped --reason`, after user confirmation, is recorded with who released it. |
| A forgotten "parallel" in a new chat could take over a live one. | One `--parallel` puts the folder in parallel mode until all of its sessions end. In parallel mode nobody is taken over, and new chats join with a warning. |
| Renaming the folder or a hostname change locked the project. | A hashed hardware machine ID replaces the hostname. Sessions from a vanished path are superseded; nothing depends on `source_key`. |
| A later phase editing shared files blocked its own VERIFY/DONE. | Dependencies must be DONE. Stale dependency evidence is a warning. |
| Commits and handover edits staled whole-checkout evidence. | Fingerprints use file content (Git blob IDs) and exclude the narrative documents. |
| A check writing a report into its scope could never reach DONE, and the error did not say why. | `changed_during_check` lists the files; the phase `exclude` list or .gitignore fixes it; every DONE refusal lists its gaps. |
| Non-Git prototypes with node_modules failed at begin. | Dependency and build directories plus simple .gitignore patterns are skipped. Oversized workspaces degrade with a warning instead of failing. |
| `git add -A` committed state, check logs and machine facts. | The state directory carries its own `.gitignore`, unless the project already versions it. |
| Stopping a dev server left its child processes running. | Runtimes and checks run in their own process group, and stopping ends the whole group. |
| Concurrent writers failed at once with `busy` (flaky test). | The lock waits up to 10 seconds. |
| Output and handover grew with every past chat; Cyrillic printed as `\u...`. | Output lists active sessions and counts the ended ones. History is bounded. Output is UTF-8. |
| Command lines hid in JSON files that permission prompts never show. | Commands go after `--` and are visible to host permission prompts. |
| The bare name `handover-changelog` collided with another plugin and its CHANGELOG-handover.md. | The skill is renamed `session-handover`, with HANDOVER.md as the default. Projects run by another workflow are left to it. |

Removed:

- the operation ledger (`operation ...`);
- the `start` and `--relocate` commands;
- the Eco mode name;
- efficiency.md and recovery.md;
- the legacy shell installer.

Recovery now lives in one table in the quickstart. Revision guards are required
only for `plan`, `batch` and `release`.

State schema 1 is upgraded on its first write, and the original is kept as
`state.v1.json`. Unresolved operations from the dropped ledger are reported
once.

## Limits

- Claims rely on cooperating agents: they do not block direct file edits, and
  the local lock does not coordinate separate machines.
- Process-group cleanup is POSIX. Windows uses `taskkill /T` for a live child
  and is untested.
- Instructions are identical across providers, but model behaviour is not.
  Check the first real session on each new provider before treating its
  behaviour as validated.

## Install

Claude Code 2.1.275 or later:

```text
/plugin install session-workflow --marketplace pashbel/session-workflow
```

For Codex, standalone copies for other providers, updates and rollback, see
the [repository guide](../../README.md). License: [Apache 2.0](LICENSE). The [validation record](VALIDATION.md)
lists what was executed.
