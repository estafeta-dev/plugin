# Runtime reference

Cold reference for options that [quickstart](quickstart.md) does not cover.
The bundled [CLI](../scripts/session.py) needs Python 3.9+ and the standard
library. It makes no model or network calls and never writes to Git. Its
[schema](../scripts/session.schema.json) defines inputs and state. Run it from
this skill's directory; do not load its source into the prompt.

## State

- Location: `.agent-state/session-workflow/` in the main Git checkout. Linked
  worktrees share it; projects without Git use the project directory;
  `--state-dir` selects another directory explicitly.
- The runtime adds a `.gitignore` there, so logs and machine facts stay out of
  commits. It skips this when the project already tracks files in that
  directory.
- Writes are serialized by an OS lock, waiting up to 10 seconds. Each state
  write is atomic and keeps `state.previous.json`.
- Schema 1 state from 2.x is upgraded on the first write; the original is kept
  as `state.v1.json`. Its operation ledger is dropped and unresolved operation
  IDs are reported once. Newer or broken schemas are refused untouched.
- History is bounded: the last 500 events and the last 10 runs per phase and
  check name; older logs are deleted.

## Sessions

| Command | Purpose |
| --- | --- |
| `begin [--session ID] [--parallel] [--next-action TEXT]` | Initialize if needed and register a new session; omit `--session` to get a unique ID |
| `checkpoint --session ID --next-action TEXT [--note TEXT]` | Save a resume point |
| `end --session ID --next-action TEXT [--handover-output FILE] [--keep-runtimes]` | Final checkpoint, release claims, render facts, stop own runtimes |
| `release --session OLD --expect-revision R --confirm-stopped --reason TEXT [--by ID]` | End a stopped session that cannot end itself |
| `status [--session ID] [--full]` | Compact state, other sessions, drift and warnings |
| `next --session ID` | Ready phase, stale DONE evidence, unfinished phases |
| `snapshot [--full]` | Workspace facts; creates no state |
| `init [--context F] [--plan F] [--handover F]` | Create state with document pointers; `begin` does this too |

Identity is a hashed hardware machine ID plus the checkout path.
`SESSION_WORKFLOW_MACHINE_ID` overrides it for containers. A session acts only
from its own machine and path; elsewhere it gets `session_foreign`.

Solo `begin`, the default, ends earlier sessions recorded in this checkout, or
in a checkout path that no longer exists on this machine. It moves their claims
and runtimes to the new session, and their open delegations once the state is
saved. A session that is still running a check blocks this with
`session_alive`.

A session in this checkout that acted within
`SESSION_WORKFLOW_TAKEOVER_IDLE_MINUTES` (default 30), or that has open
delegations, may belong to a live thread. A solo `begin` then joins in
parallel, takes over nothing and warns.

Activity is measured from the runtime's own records:

- the session's begin and checkpoints;
- its events and checks;
- its delegations.

`begin --parallel` puts the checkout in parallel mode, which marks every
active session there as parallel. While any parallel session is active in a
checkout, a plain `begin` there joins as parallel, supersedes nobody and
returns a warning. Parallel sessions and sessions on other machines are never
superseded. They appear in `other_active_sessions` and leave only through `end`
or a confirmed `release`. When all of them are gone, solo takeover resumes.
Time never expires a session.

## Phases

| Command | Purpose |
| --- | --- |
| `plan --session ID --expect-revision R --input F [--merge]` | Import or upsert phase definitions |
| `batch --session ID --expect-revision R --input F` | Up to 20 atomic plan/transition/checkpoint steps |
| `transition --session ID --phase P --to STATE [--reason T] [--acceptance-note T]` | Claim, release or move a phase |

Phase fields: `id`, `title`, `acceptance` (required), and `depends_on`,
`priority`, `paths` (default `*`), `exclude` and `required_checks`.

- Paths are literal relative files or directories. Globs and `..` are rejected.
- Plans cannot delete phases (defer them), inject DONE or rewrite another owner's
  phase. A DONE phase must be reopened before its contract changes.
- One owner per phase. Within one checkout, overlapping paths cannot be
  claimed by two sessions. Separate worktrees edit isolated copies. Claims do
  not block direct edits: they rely on cooperating agents.
- Reaching IN_PROGRESS, VERIFY or DONE requires every dependency to be DONE.
  Stale dependency evidence produces `warnings`, not a block.
- Reopening a DONE phase returns completed dependents to VERIFY.

## Evidence

| Command | Purpose |
| --- | --- |
| `check run --session ID --phase P --name N [--timeout S] -- CMD...` | Execute and record a check (or `--argv-file F`) |
| `check record --session ID --phase P --name N --result pass\|fail --evidence T` | Record manual evidence, labelled reported |
| `check abandon --session ID --id CHECK --confirm-stopped --evidence T` | Close an interrupted check whose command stopped |

- A check runs without a shell in its own process group. A timeout stops the
  whole group.
- The phase fingerprint covers file contents in scope, Git blob IDs after clean
  filters, the acceptance text, paths, `exclude` and required checks. Commits
  alone do not change it. With `*`, the context, plan and handover documents
  are excluded.
- `stable_inputs` is false when the check changed files in scope while it ran.
  `changed_during_check` lists them. Such a run cannot satisfy DONE; add those
  outputs to `exclude` or .gitignore and run the check again.
- DONE requires `--acceptance-note` and, for every required check, a latest
  executed passing run with stable inputs, a matching fingerprint and an intact
  log. Without required checks, any fresh passing run qualifies, including a
  reported one.
- Ignored files are outside fingerprints; declare and check such inputs
  separately.

## Runtimes

| Command | Purpose |
| --- | --- |
| `runtime launch --session ID --name N [--keep] -- CMD...` | Start a supervised process group |
| `runtime status --session ID --name N` | Read its receipt |
| `runtime stop --session ID --name N` | Stop the group, also for an ended session's kept runtime |

A detached supervisor owns the group through a live handle and writes a
heartbeat receipt. Stopping signals the whole group, so descendants such as
`npm -> node -> vite` stop too. A missing receipt, an expired heartbeat or
another machine reports `unknown` or `foreign`; the runtime never kills a
recorded PID. On Windows the supervisor ends the process tree through
`taskkill /T` while the child is alive.

## Delegations

| Command | Purpose |
| --- | --- |
| `delegate providers` | Read-only: provider CLIs on PATH and their versions |
| `delegate start --session ID --name N --provider P --mode consult\|review\|write --packet F [--model M] [--phase P --worker-session W] [--workspace DIR] [--timeout S] -- CMD...` | Record a delegation and run a CLI worker as a supervised runtime `relay-N` |
| `delegate start ... --host-ref REF` (no command) | Record a host-native child task, such as a T3 task ID |
| `delegate status [--session ID] [--name N]` | Read-only: records, worker runtime, writer facts and result |
| `delegate collect --session ID --name N [--from FILE] [--confirm-stopped]` | Parse the worker's final RELAY-RESULT block from `--from`, `reply.txt` or the CLI worker's stdout |
| `delegate cancel --session ID --name N [--confirm-stopped]` | Stop a CLI worker, or close a host task you already cancelled |

- Records live in `delegations/<name>/` under the state directory: the packet,
  `record.json` and `result.json` with SHA-256 hashes. `state.json` and its
  schema do not change, so a 3.0 runtime can still take part as a worker.
- In the worker command, `{packet}`, `{packet_text}`, `{reply_file}`,
  `{workspace}` and `{state_dir}` are replaced. The worker runs in `--workspace`
  without a shell or stdin. Its stdout and stderr go to separate logs.
  `--timeout` stops its process group after a 10-second grace period. Within
  it, a `check run` started by the worker stops its own check group (1-second
  grace, then SIGKILL) and records the run as `abandoned`.
- A writer needs an unclaimed phase that is not DONE and a new worker session
  ID. A given `--workspace` must share this coordinator (this checkout or a
  linked worktree); a host task may omit it when the host creates the
  worktree. The worker begins that session with `--parallel`, claims the phase
  itself and does not commit: the integrator owns Git history.
- `collect` takes the last block of the final answer. That is plain text, or
  one of: a Claude event of type `result`, Gemini's untyped `response`, or a
  Codex `agent_message` item. Blocks in other events, such as tool results,
  are ignored. Duplicate JSON keys make a result `malformed`. A missing or invalid block leaves the record
  `malformed`, and it can be collected again. While a CLI worker runs,
  `collect` refuses, even with `--from`.
- For a writer, `discrepancies` lists:
  - claimed passing checks the worker did not record as passing;
  - required checks whose latest run is not the worker's, or whose evidence
    would not pass the DONE gate in the worker's workspace (fingerprint and
    log);
  - reported files outside the phase paths (traversal and absolute paths
    included);
  - changes the worker's workspace shows outside the phase paths, or did not
    report. These are compared with a baseline taken when the delegation was
    recorded, so earlier changes in a shared checkout do not count;
  - a worker session that never began.

  Claims alone prove nothing.
- A writer recorded after its host task already began and claimed the phase
  is accepted when that session is parallel and began after the orchestrator.
- `cancel`, `collect` and `end` treat a CLI worker as stopped only when its
  receipt says `exited`. For `unknown` or `foreign`, confirm that it stopped
  and pass `--confirm-stopped`; `end` leaves such records open.
- `end` stops the session's CLI workers like other runtimes and cancels their
  records. It reports host tasks and kept workers as `open_delegations`.
  `begin` and `status` list them. A session that takes over by solo `begin`
  inherits them once its state is saved. Any later session adopts the record
  of an ended orchestrator, together with its kept CLI process, on `collect`
  or `cancel`.

## Handover output

`handover [--output FILE]` and `end --handover-output FILE` replace only the
block between `<!-- session-workflow:facts:start -->` and
`<!-- session-workflow:facts:end -->`. Missing markers append one block;
duplicate markers fail without changes. The block lists phases, latest checks,
active sessions and the latest ended session, not the full history. If
rendering fails after `end`, the error `handover_after_end` means the session
has already ended: retry only `handover`.

## Output and exit codes

Output is UTF-8 JSON with `ok`, `revision`, `state_directory`, `result` and
optional `warnings`, or `error.code` and `error.message`. Exit codes: 0 ok,
2 invalid input, 3 conflict or gate, 4 busy, 6 environment or I/O.
