# estafeta

![estafeta — Pass the context & Keep building.](packs/session-workflow/assets/cover.webp)

estafeta lets coding agents carry one project across many chats, agents
and machines: each new session resumes from the project's own files, not from
chat history.

_In practice:_

- _You open a chat with "Use session-start". The agent finds where work stopped,
  checks what changed since, and continues._
- _Work runs in phases with acceptance criteria. A phase is DONE only after a
  check has actually passed._
- _"Use session-end" saves the exact next step for whoever continues: another
  chat, another agent or another machine._

<picture>
  <source media="(max-width: 600px)" srcset="packs/session-workflow/assets/note-small.svg">
  <source media="(max-width: 1000px)" srcset="packs/session-workflow/assets/note-medium.svg">
  <img src="packs/session-workflow/assets/note.svg" alt="Note: estafeta is built for long, multi-session projects; a small one-off task does not need it. The runtime is covered by tests, but its effect on model results is still being measured.">
</picture>

## Getting started

You need an agent with terminal access (Claude Code, Codex, Gemini CLI and
others) and Python 3.9+.

### Option 1. Ask your agent

```text
Install estafeta from https://github.com/pashbel/estafeta
for this agent: follow "Agent installation" in docs/INSTALL.md.
```

### Option 2. Use the terminal

```sh
git clone https://github.com/pashbel/estafeta.git
cd estafeta
python3 scripts/workflow.py install --all-detected
```

Then ask any agent: "Use session-guide. Explain how this works."

| Say | When |
| --- | --- |
| Use session-start | Opening a chat |
| Use plan-and-orchestrate | Work longer than one step |
| Use session-handover | At a milestone |
| Use session-end | When you stop |

[Installation](docs/INSTALL.md) · [Usage](docs/USAGE.md) ·
[Benchmarks](benchmarks/README.md) · [Validation](packs/session-workflow/VALIDATION.md)

---

## License

This project is licensed under the [Apache License 2.0](LICENSE).
