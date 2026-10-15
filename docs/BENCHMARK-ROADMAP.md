# Measure the intended project workflow

The short website/game/app [harness](../benchmarks/README.md) measures
orchestration overhead and one fresh-chat continuation in three arms (baseline,
lite conventions, workflow) with repetitions. It does not exercise the main
reason to adopt this pack: a long project with independent sessions, changes and
interrupted work. Repeat it after optimizations to catch overhead/quality
regressions; use the following separate protocol to evaluate project value.

## Three larger scenarios

| Scenario | Product scope | Session change or interruption | Independent acceptance |
| --- | --- | --- | --- |
| Workshop site and editor | Public catalogue, filtering/URL state, booking validation, local content editor, English/Czech UI and keyboard/mobile behavior | Add a content schema migration in a later fresh session; public UI and editor writers work in isolated scopes before one integration session | Public/editor round trips, migration of a frozen old dataset, reload/URL consistency, text rendering, language switches, keyboard/mobile checks and regression suite |
| Small browser game | Deterministic seeded levels, input handling, scoring, save/resume, replay and configurable difficulty | Gameplay and save/UI writers work in isolated scopes; terminate one session after a recorded checkpoint, then resume it in a fresh chat with a new level rule | Seed/replay determinism, save migration/corruption recovery, pause/resume, keyboard victory, stable score and regression suite |
| Offline project board | CRUD, filters, schema migration, queued edits, simulated server sync/conflicts, import/export and undo | Data/sync and UI writers progress separately; interrupt one test process, introduce a conflicting change, then integrate from durable records | Queue/retry identity, conflict resolution, atomic import, stable IDs, migration, reload/undo semantics and regression suite |

Fixtures, the simulated sync endpoint and the acceptance tests must be committed
and frozen before execution. No external API, asset generation or live deployment
is needed. Product requirements and tests are identical across arms; do not award
points for creating more documents or for invoking a named skill.

## Fair lifecycle protocol

Run three arms: `baseline` (no skills), `lite` (no skills, plus the frozen
conventions text of `benchmarks/prompts/lite.md`) and `workflow` (this pack).
For each scenario and arm use the same model/effort/tools, starter, time cap and
functional briefs. Use at least three independent seeds/repetitions per cell,
with a recorded, balanced random order. All arms receive the same write scopes,
handoff requirement, interruption schedule and permission boundaries. Baseline
may use its ordinary planning and project files; lite adds only the conventions
text; only workflow gets this pack. Do not force baseline or lite to omit
documentation or otherwise handicap them.

`workflow` versus `lite` is the decisive comparison: does the runtime earn its
cost over conventions alone? Lite keeps the same project documents and evidence
rules but has no claims, checkpoints, runtime state or scripts; its ownership and
recovery rely on documents and Git. Comparing each arm with baseline separates
the value of conventions from the value of the runtime.

Use six logical sessions per project: architecture/start, two concurrent feature
writers in isolated worktrees, resumed interrupted writer, integration and a final
fresh-session requirement change. Give concurrent writers only their own briefs
and shared project files. Keep one integrator for shared documents/Git history.
Include a deliberate request to acquire an already owned scope: evaluate whether
the writer preserves the owner and reconciles before editing, rather than merely
counting conflict errors as failures. The same safety expectation applies to all
arms. Do not auto-evict a writer because a clock expired.

Check cooperative local concurrency separately from independent device copies.
Multi-device evaluation needs actual transferred artifacts/destination checks or
a shared coordination service. A local lock and matching installations do not
prove cross-host coordination. A second provider is a separate controlled block;
do not mix provider/model changes into the arm comparison.

## Measurements and decision rule

- Native total, cached and uncached input/output tokens for every coding session;
  missing telemetry stays unknown. Add the costs of planning, recovery and
  integration to the corresponding project arm.
  Persist supported intermediate usage receipts before a forced interruption.
  If only final-turn usage is available, schedule planned interruptions after a
  completed turn or disclose unknown partial inference costs; never estimate them
  from text length or replace them with zero.
- Elapsed project time and summed active session time, reported separately when
  sessions overlap. Also report time from fresh-session start to the first
  correct product change and time spent redoing completed work.
- Requirement groups passed before/after each change; reproducible defects
  grouped by cause; regressions introduced at integration; unresolved work.
  Keep grader defects and infrastructure failures separate.
- Tool commands and commands containing runtime calls. If counting inner CLI
  invocations or metadata steps, instrument them explicitly and label the unit;
  one batched command is not one metadata operation.
- Lost checkpoints/claims, unauthorized owner overwrite, duplicate side effects,
  stale evidence promoted to DONE, failed recovery and retained foreign jobs.
  A prevented unsafe action is successful protection, not a product bug.

Freeze acceptance and the scoring formula before running. Compare time/tokens
at equal passed requirements, including recovery costs. A lower budget achieved
by omitting checks or leaving more unfinished work is not an improvement. Report
each repetition and distribution, rather than only the best run. Product workflow
value requires observed recovery/integration benefits; the short overhead pilot
alone cannot establish it. The runtime earns its cost only if workflow beats lite
on recovery, ownership safety or integration at equal passed requirements, or
matches lite at lower cost. If lite matches workflow, the conventions rather than
the runtime carry the value.

## Cross-provider relay (follow-up)

The golden path tests in `scripts/test_relay.py` catch regressions in the
relay mechanics; they do not show that cross-provider work pays off. A later
benchmark should compare, on the frozen scenarios above:

- single-provider work with self-review;
- the same work with an agent-relay cross-review by another provider;
- a delegated write phase by another provider.

Measure defects found by independent acceptance tests, review findings that
were confirmed or rejected, extra tokens and wall time, and how often a
writer's claims disagreed with recorded facts. Record provider and model for
each arm, since a result for one pair does not carry over to another.
