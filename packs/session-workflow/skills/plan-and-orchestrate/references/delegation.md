# Parallel work and delegation

Use native subagents or parallel chats only when the host offers them and the
user authorized them. No team size is required; sequential work with disclosed
self-review is always valid. To consult, review with or delegate to an agent of
another provider, use the agent-relay skill: it records each delegation and
checks a writer's claims against the runtime.

- **One integrator** owns the plan, context, handover, integration and Git
  history. Writers never change those shared records.
- **Isolation:** give each writer disjoint `paths` in one checkout, or its own
  linked worktree. Every parallel writer starts with `begin --parallel` and
  claims only its phase. Serialize intertwined changes and shared resources such
  as one dev server, one browser profile or one database.
- **Packet** for a writer: phase ID, workspace, goal and acceptance, allowed
  paths, relevant code anchors, constraints, dependency state, required checks
  and stop conditions. Later packets name the checkpoint and send only changes.
- **Writer returns** changed files, behavior, checks with results, gaps and
  blockers.
- **Reviewers are read-only.** They review an exact revision or diff and return
  findings with location, scenario and impact, the scope they checked, and
  APPROVE or CHANGES_REQUIRED. A verdict does not mean that unexecuted tests
  passed. Reuse the same reviewer for the fix delta when possible.
- **Before session-end**, make sure every writer has ended its session or been
  released after confirming it stopped. Keep the plan resumable without native
  agent IDs.
