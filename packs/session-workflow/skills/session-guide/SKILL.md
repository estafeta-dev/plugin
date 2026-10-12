---
name: session-guide
description: >-
  Explain Session Workflow to a user in a few lines: what each skill is for,
  what to say and when, which files appear, what the agent never does without
  asking, and where the current project stands. Use for session-guide, "how does
  Session Workflow work", «как работает session workflow» or «объясни
  session-start». Read-only: it starts and changes nothing.
license: Apache-2.0
metadata:
  workflow-pack: session-workflow
  workflow-version: "3.0.0"
---

# Session guide

Explain the workflow so that the user can use it right away.

- Answer in the user's language, in about 20 lines.
- Every line must tell the user something to do or something they need to know.
- No product praise, no generic advice, no explaining what an AI agent is.

1. **Look at this project, read-only.** If `.agent-state/session-workflow`
   exists in the Git root, run `status` with this skill's `scripts/session.py`
   ([quickstart](references/quickstart.md)). Never run `begin` or anything
   else that writes.
2. **Explain with the card below.** Cut it to what matters for this user and
   skip what they already know.
3. **Show where the project stands** in 2-3 lines: phases and their states,
   the saved next action, and other active sessions. If there is no state, say
   the project does not use the workflow yet and that "Use session-start" sets
   it up.
4. **Offer one next step,** usually starting a session. Do not start it
   unasked.

## Card

**What it is.** The project keeps its own memory in files: goal, plan,
progress, verified checks and the next step. A new chat, another agent or
another device continues from those files instead of from chat history.

**What to say.** Any language works; naming the skill is the most reliable.

| When | Say | The agent |
| --- | --- | --- |
| Opening a chat | "Use session-start" | Finds where work stopped, checks what changed since, continues |
| Work longer than one step | "Use plan-and-orchestrate" | Splits it into phases with acceptance criteria, executes them, runs checks |
| At a milestone | "Use session-handover" | Writes what changed and why, what is verified and what is left |
| When stopping | "Use session-end" | Saves the exact next step and stops the servers it started |

**Files.**
- PROJECT.md holds the goal and next step, docs/plans/ the plan, and
  HANDOVER.md what is done and verified. Read and edit them freely.
- `.agent-state/` holds machine state. It is never committed or edited by hand.

**What the agent does by itself.**
- It takes over the previous chat's work in the same folder, even if that chat
  was closed without session-end.
- It marks a phase DONE only after a check passed. Otherwise the phase stays
  VERIFY, with the gap named.

**What it never does without you.** Commit, push, deploy, paid runs or
deleting data. A plan alone does not authorize implementation.

**When you are needed.**
- **Several agents in one folder:** tell one of them they work in parallel.
  The folder then stays in parallel mode until all of them end, and none takes
  over another.
- **The agent asks whether a chat is closed:** answer, and it releases that
  chat's unfinished work.
- **A phase stays VERIFY:** something was not checked, for example the UI.
  Check it, or accept the gap.
- **Switching devices:** run session-end first. Then move the branch, any
  uncommitted files and `.agent-state`, and run session-start there.

A one-off small edit needs none of this.
