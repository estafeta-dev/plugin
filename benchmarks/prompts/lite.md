Project continuity conventions (apply them without extra tools):

- Keep three short project files current. PROJECT.md: goal, constraints,
  documentation map and the next concrete action. docs/plans/<workstream>.md:
  phases with acceptance criteria, dependencies and status. HANDOVER.md: what
  changed and why, checks actually run with their results, known gaps and the
  next action.
- At the start, read these files plus git status and the recent log before
  editing; note any drift between the documents and the workspace.
- Phase status is TODO, IN_PROGRESS, VERIFY, DONE or BLOCKED. Mark DONE only
  after a check you executed passed after the last relevant change; otherwise
  keep VERIFY and name the gap.
- Report evidence by level: code written, automated checks, browser/UI checks,
  device checks. Never present an unexecuted check as passed.
- Update only changed facts; do not copy the brief or full logs into documents.
- At the end of the session, update HANDOVER.md and the next action in
  PROJECT.md, and stop processes you started.
