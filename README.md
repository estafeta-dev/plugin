# Session Workflow

Skills for long-running agent projects (development, prototypes, research)
that span many chats, devices and agents. Four coordinated skills keep a
durable project record and share a deterministic Python runtime for
checkpoints, phase ownership and recorded checks. A fifth, `session-guide`,
explains all of it to a new user in a minute.

**Version 3.0.0** · Python 3.9+ · Standard library only

| Skill | Responsibility |
| --- | --- |
| `session-start` | Resume from the saved checkpoint, reconcile the workspace, continue the task |
| `plan-and-orchestrate` | Plan phases with acceptance criteria and execute them with recorded checks |
| `session-handover` | Record what changed, why, which checks ran and what is left |
| `session-end` | Save a resumable checkpoint and stop processes the session started |
| `session-guide` | Explain to a new user in a few lines how it works and where the project stands (read-only) |

## What it does and does not do

- **Durable record:** PROJECT.md, a plan and HANDOVER.md, so a fresh chat
  continues from files alone. The runtime adds a checkpoint with the next action
  and workspace drift.
- **Honest status:** a phase reaches DONE only with an acceptance note and a
  fresh executed check. The runtime explains every gap. Proof levels (code,
  automated, UI, device, delivery) stay separate.
- **Solo by default:** a new chat in the same checkout takes over from the
  previous one, including its claims and preview servers. A chat that closed
  without session-end no longer blocks anything.
- **Parallel when declared:** one `--parallel` puts the folder in parallel mode
  until all of its sessions end. In parallel mode nobody is taken over, and new
  chats join. Writers claim disjoint paths or separate worktrees. A stopped
  parallel session leaves only through a confirmed `release`.
- **No hidden automation:** no model or network calls, no Git writes, no hooks
  and no daemons. Runtime state stays out of commits. Preview servers stop
  together with their child processes.

## Evidence so far

Paired pilots of 2.3 and 2.4 on three small offline projects (website, game,
web app) passed every functional check with and without the skills. The skills
cost 49–226% more tokens and 5–42% more time there. A control agent told only
to "leave enough project context for a fresh chat" handed over just as well.
See the [2.3 pilot](benchmarks/results/2026-10-12-pilot/README.md) and the
[2.4 rerun](benchmarks/results/2026-10-12-optimized/README.md).

Version 3.0 removes the failure modes found in a review of 2.4.1:

- stuck claims after a crashed chat;
- a locked project after a folder rename or hostname change;
- dependent phases blocking each other;
- checks that could never satisfy DONE;
- runtime logs committed by `git add -A`;
- orphaned dev servers.

It also shrinks the instructions:

- 24% less to load per skill (about 8.8 KB instead of 11.6 KB);
- about half the instruction material in total (26 KB instead of 50 KB).

Its effect on model behaviour has not been benchmarked yet. The prepared [three-arm benchmark](benchmarks/README.md)
compares no skills, conventions only ("lite") and the full workflow.

## Install

### Through an agent chat

Paste this into any agent that has terminal access (Claude Code, Codex, Gemini
CLI and others). You can write it in any language; the agent answers in yours.

```text
Install Session Workflow from https://github.com/pashbel/session-workflow
for this agent: follow "Agent installation" in docs/INSTALL.md.
```

To install for several agents, write "for all my agents" instead of "for this
agent". The agent follows the steps in [docs/INSTALL.md](docs/INSTALL.md#agent-installation),
so updates to the procedure reach everyone without a new prompt.

In Claude Code 2.1.275 or later, one command also works:
`/plugin install session-workflow --marketplace pashbel/session-workflow`.

### From the terminal

```sh
git clone https://github.com/pashbel/session-workflow.git
cd session-workflow
python3 scripts/workflow.py install --all-detected
python3 scripts/workflow.py status --all-detected
```

Upgrading from 2.x backs up and removes the old `handover-changelog` copy. It
leaves same-named skills from other packs untouched. Existing project state is
upgraded on its first write, and a `state.v1.json` copy is kept. See
[installation](docs/INSTALL.md) for native Codex and Claude Code plugins,
individual providers, updates and rollback.

## Use

```text
Use session-guide. Explain how this works and where this project stands.
Use session-start. Resume this project from its saved checkpoint.
Use plan-and-orchestrate. Implement the agreed plan and verify each phase.
Use session-handover. Record the changes and remaining work.
Use session-end. Save a checkpoint for another device.
```

Ask in any language; documents keep their language and machine identifiers stay
English. For a small one-off edit you do not need the skills at all. See
[usage](docs/USAGE.md) and the [command cycle](packs/session-workflow/shared/quickstart.md).

## Validate and maintain

```sh
python3 scripts/workflow.py check
python3 scripts/test_session.py
python3 scripts/test_workflow.py
```

The [validation record](packs/session-workflow/VALIDATION.md) separates
executed checks from untested behaviour. See [maintenance](docs/MAINTAINING.md)
for shared sources, manifests and release archives.

## License

[Apache License 2.0](LICENSE).
