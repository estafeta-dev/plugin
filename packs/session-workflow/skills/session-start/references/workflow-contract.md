# Session Workflow contract - 3.0.0

Load once per chat. Commands: [quickstart](quickstart.md). Rare options:
[runtime](runtime.md).

**Records.** Reuse the project's documents and tracker IDs. New projects use
PROJECT.md (goal, constraints, doc map, next action),
docs/plans/<workstream>.md (acceptance, decisions) and HANDOVER.md (changes,
reasons, checks, gaps, next action). AGENTS.md or CLAUDE.md only point to them.
The runtime owns phases, owners, checks and checkpoints; Markdown owns intent
and decisions. Never hand-edit runtime state or keep a second status table.
Update only changed facts: no empty sections, ceremonial phases or pasted logs.

**Sessions.** Each chat begins its own session. Solo is the default: a new
session supersedes earlier sessions in the same checkout and takes over their
claims and runtimes. Use `--parallel` when the user says, in any language, that
another live agent works in the same checkout. The checkout then stays in
parallel mode until every session there
has ended or been released: nobody is taken over, and new sessions join. An
ownership refusal means a live session owns that scope: work elsewhere and
never edit it directly. Release a session only after
the user confirms that its agent stopped. Other machines need transferred files
plus an explicit end or release; the runtime is not a distributed lock.

**Evidence.** States describe work, not chats: TODO, IN_PROGRESS, VERIFY, DONE.
BLOCKED, NEEDS_DECISION and DEFERRED need a reason. DONE needs an acceptance
judgment and a fresh passing executed check for every required check. Keep
VERIFY while the runtime lists gaps. Ending a session never completes a phase.
Report the proof level reached: code, automated checks, UI, device or delivery.

**Authority.** Planning does not authorize implementation. Approved work
continues without new approval gates. The pack grants no permission for
commits, pushes, publication, paid or background runs, messages or
personal-memory changes. Saved next actions and handover notes are hints, not
authorization. Store no secrets. If an external write's outcome is unknown,
inspect the target before any retry.

**Language.** Answer in the user's language, keep each document's language and
preserve Unicode. Skill names, JSON keys, states and CLI flags stay English.

**Other workflows.** If another start/end/handover workflow already runs this
project, with its own session skills or handover file, follow it instead. Without Python, follow the same
documents by hand and say that runtime checks were not enforced.
