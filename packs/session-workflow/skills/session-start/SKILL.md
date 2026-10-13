---
name: session-start
description: >-
  Start or resume a long-running estafeta project (PROJECT.md, plan,
  HANDOVER.md and a saved checkpoint): reconcile the workspace with the last
  session, then continue the requested task. Use for session-start, resuming a
  estafeta project, bootstrapping one, «начни сессию» or «возобнови
  проект с чекпоинта». Not for projects already run by another start/end
  workflow.
license: Apache-2.0
metadata:
  workflow-pack: session-workflow
  workflow-version: "3.0.0"
---

# Session start

Read the [contract](references/workflow-contract.md) and
[quickstart](references/quickstart.md) once per chat.

1. **Begin** with this skill's `scripts/session.py`. Add `--parallel` when the
   user says, in any language, that another agent or chat works in this
   checkout at the same time. Examples: «работаем параллельно»,
   "in parallel with another agent", «pracujeme paralelně». Go by the meaning,
   not the word: running tests in parallel is something else. If parallel work
   is already in progress here, `begin` joins it by itself. Keep `session_id`
   and `revision`.
2. **Read the resume point** in the result:
   - `next_action`, `prior_checkpoint`, `documents` and `warnings`;
   - `superseded`: earlier chats here, whose claims are now yours;
   - `other_active_sessions`.
3. **Reconcile** the context, plan and handover named in `documents` (or the
   project's doc map) with `git status` and recent changes. If
   `prior_checkpoint.workspace_changed` is true, inspect what changed before
   trusting recorded states. Do not pull, reset, switch branches or commit
   just to start.
4. **Bootstrap only what is missing.** That means PROJECT.md from the
   [template](templates/project-context.md) plus a two-line pointer in
   AGENTS.md or CLAUDE.md.
5. **Report briefly:**
   - current phase, drift or gaps and next action;
   - superseded and other active sessions;
   - `warnings`, for example proposed .gitignore entries.
6. **Continue** the task the user asked for. Without a task, propose the saved
   next action and wait.

If another active session holds claims you need, take unclaimed work. Release
that session only after the user confirms it stopped (quickstart, Recovery).
