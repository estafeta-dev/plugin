# Usage

New users can start with `session-guide`: a short, read-only explanation of the
workflow and of where the current project stands.

Use the same skill names with every provider. Plain-language requests work
everywhere. Native plugin hosts may add a namespace; in Claude Code, for example,
it is `/session-workflow:session-start`.

Use the workflow for projects that span sessions, devices, agents or phased work.
A small isolated edit does not need it.

## Session lifecycle

1. **Start:** `session-start` begins a session. It reads the saved checkpoint and
   reconciles the documents with the workspace, then continues the requested task.
2. **Plan and work:** `plan-and-orchestrate` records phases with acceptance
   criteria and claims a phase before editing. It verifies with recorded checks.
   A request to plan only never starts execution.
3. **Handover:** `session-handover` records what changed, why, the evidence and
   what is left, at any milestone.
4. **End:** `session-end` saves the next action, renders the final facts and
   stops processes the session started. Unfinished work stays unfinished.

| Intent | Example |
| --- | --- |
| Resume | Use session-start. Resume the checkout and continue the saved task. |
| Plan only | Use plan-and-orchestrate. Plan this change without implementing it yet. |
| Execute | Use plan-and-orchestrate. Complete the agreed phases and verify acceptance. |
| Economize | Use plan-and-orchestrate with minimal reads and output. |
| Handover | Use session-handover. Update the handover from actual changes and checks. |
| End | Use session-end. Save the next action for another device. |

## Language behaviour

The instructions are in English and apply in any language. The agent answers
in your language and keeps each document's existing language. New documents
follow the project's convention, falling back to English. Names, paths, code
identifiers, JSON keys and CLI options are not translated.

| Language | Example invocation |
| --- | --- |
| English | Use session-start. Resume the project and answer in English. |
| Czech | Použij session-start. Pokračuj v projektu a odpovídej česky. |
| Russian | Используй session-start. Продолжи проект и отвечай по-русски. |
| Spanish | Usa session-start. Retoma el proyecto y responde en español. |
| Japanese | session-start を使ってプロジェクトを再開し、日本語で回答してください。 |

Titles, acceptance criteria, reasons, notes, next actions and paths accept
Unicode, and the runtime prints them as readable UTF-8. Session, phase and check
IDs are ASCII.

## Project record

Reuse the project's existing context, plan and handover. New projects use
`PROJECT.md`, `docs/plans/<workstream>.md` and `HANDOVER.md`. Provider
instruction files keep a short pointer to them. A project that another workflow
already runs keeps that workflow and its files.

Runtime state lives in `.agent-state/session-workflow` in the main Git checkout
and is shared by linked worktrees. It carries its own `.gitignore`. To hand off,
transfer it together with its evidence.

## Solo and parallel sessions

- **Solo (default):** one writer per checkout. A new chat supersedes the earlier
  chats in the same checkout and takes over their phase claims and preview
  servers. A chat closed without session-end therefore blocks nothing. A chat that
  is still running a check is detected as alive, and the takeover is refused.
- **Parallel:** tell a chat, in any language, that another agent works in the
  same folder ("work in parallel", «работаем параллельно», «pracujeme
  paralelně», «並行して作業する»), and it begins with `--parallel`. The agent goes
  by the meaning, so a request to run tests in parallel does not count.
  - The folder then stays in parallel mode: sessions already active there become
    parallel too, and a chat opened later without the word joins automatically.
  - Nobody is taken over until every session there has ended or been released.
  - Give the writers disjoint paths or separate worktrees, and keep one
    integrator for shared documents and Git history.
  - If a parallel chat stops without ending, ask the user to confirm, then
    `release` it; the release is recorded.
  - When all of them are gone, solo takeover works again.
- **Other machines:** state is local. Before switching devices, end the
  session, then transfer the branch, uncommitted work and
  `.agent-state/session-workflow`. Sessions from another machine appear as
  `other machine` and can be released after confirmation.

Claims depend on cooperation: they do not stop direct edits that bypass the runtime.

## Deterministic runtime

Skills call their bundled `scripts/session.py`; its source never needs to enter
the prompt. The [quickstart](../packs/session-workflow/shared/quickstart.md) has
every command an ordinary session uses, and a recovery table. The
[runtime reference](../packs/session-workflow/shared/runtime.md) covers the rest.

A read-only first look from this source checkout:

```sh
python3 packs/session-workflow/skills/session-start/scripts/session.py --root /path/to/project snapshot
```

The agent still chooses meaningful checks and judges acceptance. A passing exit
code alone does not establish the intended outcome.
