# Relay packet: <name>

```relay-packet
{
  "version": 1,
  "name": "<delegation name>",
  "mode": "consult | review | write",
  "orchestrator": "<orchestrator session ID>",
  "workspace": "<absolute path the worker works in>",
  "runtime": ["python3", "<absolute path to the orchestrator's scripts/session.py>"],
  "phase": "<write only: phase ID>",
  "worker_session": "<write only: new session ID for the worker>",
  "allowed_paths": ["<write only: phase paths>"],
  "required_checks": {"<check name>": ["<argv>", "..."]},
  "revision": "<review only: commit or range to review>"
}
```

You are a worker for another agent, which orchestrates this project. Delete the
sections that do not apply to this mode before sending.

## Task

<Goal and acceptance in a few lines. For review: the exact revision or diff
and what to look for. For consult: the question and the context files.>

## Context

<Only the anchors needed: files, functions, decisions, constraints. Point to
files instead of pasting them.>

## Rules

- Work only in the workspace above. Do not commit, push, install, publish or
  change PROJECT.md, plans, HANDOVER.md or other shared records.
- consult and review: read only. Change no files.
- write: change only `allowed_paths`. Record your work with the runtime above;
  `--root` is always the workspace:
  1. `begin --parallel --session <worker_session>`
  2. `transition --session <worker_session> --expect-revision R --phase <phase> --to IN_PROGRESS`
  3. make the change
  4. for each required check: `check run --session <worker_session> --expect-revision R --phase <phase> --name <name> --timeout 300 -- <its argv>`
  5. `transition ... --to VERIFY`, then `end --session <worker_session> --expect-revision R --next-action "Orchestrator integrates <phase>"`

  Use the `revision` each call returns. An `ownership` refusal means stop and
  report it as blocked.
- Stop and report `blocked` instead of guessing when access, a decision or a
  dependency is missing.

## Reply

End your final message with exactly one block, valid JSON inside:

```text
<<<RELAY-RESULT
{"outcome": "completed | blocked | failed",
 "summary": "one or two sentences",
 "answer": "consult: the answer",
 "verdict": "review: APPROVE | CHANGES_REQUIRED",
 "findings": [{"location": "file:line", "scenario": "inputs/state", "impact": "what goes wrong"}],
 "worker_session": "write: your session ID",
 "changed_files": ["write: paths"],
 "checks": [{"name": "write: check name", "result": "pass | fail"}],
 "gaps": ["anything not done or not verified"]}
RELAY-RESULT>>>
```

Keep only the fields for your mode. Report checks exactly as recorded: the
orchestrator compares them with the runtime state.
