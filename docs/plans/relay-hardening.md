# Relay hardening and provider policy plan (3.2.0)

- Context: [PROJECT.md](../../PROJECT.md); previous workstream:
  [multi-provider](multi-provider.md).
- Goal and acceptance: close the gaps that 3.1.0 left as "Not verified":
  - live `codex exec` and Gemini transports;
  - the Gemini/Antigravity route;
  - native Linux and Windows;
  - a third review round on the round 2 fixes.

  Each gap ends verified, or as a documented limitation with a concrete
  reason.
- Scope and non-goals: CI, tests, runtime fixes found by the new evidence,
  adapter corrections, validation record and a 3.1.1 release. Not in scope:
  new delegation modes or a benchmark run.
- Execution: authorized by the user on 2026-10-15.
  - Installing `@openai/codex` and `@google/gemini-cli` globally (npm prefix
    `~/.local`).
  - Paid runs: live `codex exec`, live Antigravity through T3, and a third
    Codex review round, with re-review of its fixes if needed.
  - Pushes to a stacked branch with its own PR on top of #3.
- Constraints: same as the 3.1.0 plan. Store no secrets, never use
  sandbox-bypass flags, and keep state schema 2.
- Base: `agent-relay-3.1.0` @ 5b3fb8a (PR #3). Branch
  `relay-hardening-3.1.1`, merged to main through PR #5 on 2026-10-16. The
  remaining phases continue on `main`.

## Decisions

| ID | Question and recommendation | Answer or open impact | Date |
| --- | --- | --- | --- |
| H1 | Linux | Closed by PR #3 CI: ubuntu-latest with Python 3.9 and 3.13 passed all four suites. Record it; no extra work. | 2026-10-15 |
| H2 | Windows without a Windows machine | Add a windows-latest job to CI and iterate by pushing to this branch. Mark POSIX-only tests as skipped with their reason. Fix real runtime defects. | 2026-10-15 |
| H3 | Gemini route | Verify Antigravity live through T3 host tasks. `gemini -p` gets an install and failure-mode check only: personal Gemini logins were retired, and the user chose no API key. | 2026-10-15 |
| H4 | CI double runs | Trigger `push` only for main; pull requests cover branches. | 2026-10-15 |
| H5 | Scope grew (user, 2026-10-15) | One release, 3.2.0, that adds three things: orchestrator hosts beyond T3, a project provider policy with a first-use question, and a guard against taking over a live session. | 2026-10-15 |
| H6 | Provider policy enforcement | The runtime enforces it. PROJECT.md holds a marked "AI providers" table; `delegate start` refuses until it exists, and refuses providers or modes it does not allow. session-start asks the user on first use. | 2026-10-15 |
| H7 | Live session takeover | Observed: a separate T3 thread's solo session-start superseded the live orchestrator and inherited its claims. Solo `begin` now supersedes only sessions that have been idle for 30 minutes (configurable) and hold no open delegations; otherwise it joins in parallel and warns. | 2026-10-15 |

## Phases

### R1: Windows and CI

- Scope: `.github/workflows/ci.yml`, `scripts/test_*.py`, `scripts/golden/`,
  the runtime if Windows exposes defects.
- Acceptance: the windows-latest job passes all suites. Every skipped test
  names its POSIX-only reason. Branch pushes no longer run CI twice.
- Checks: `unit-session`, `unit-workflow`, `golden-relay`, `pack-check`,
  `ci-windows` (recorded GitHub run).

### R2: Live Codex CLI

- Scope: `skills/agent-relay/references/adapters.md`, VALIDATION.md.
- Acceptance: `codex exec` as a supervised `delegate` worker passes
  consult-cli and write-worktree with `--live-verify` in disposable fixtures.
  The adapter commands match `codex exec --help` 0.162.1.
- Checks: `live-codex-cli`.

### R3: Gemini and Antigravity

- Scope: adapters, VALIDATION.md.
- Acceptance:
  - Antigravity (gemini-3.8-flash-high) through T3 passes a consult and a
    delegated write with `--live-verify`.
  - The `gemini -p` adapter matches `gemini --help` 0.64.0.
  - Its unauthenticated failure is recorded by `delegate` as an exited worker
    and a `malformed` result, never as success.
- Checks: `live-antigravity`, `gemini-cli-failure`.

### R4: Review round 3

- Scope: whatever its findings touch.
- Acceptance: a Codex review of the round 2 fixes and this whole update
  (R1-R3, R6-R8) returns APPROVE, or each finding is fixed with a test and the
  fix delta is re-reviewed.
- Checks: `live-review-3`, plus the suites.

### R6: Provider policy and first-use question

- Scope: runtime (policy parser and `delegate start` gate; `delegate
  providers` shows the policy), session-start, agent-relay, session-guide,
  the project-context template, tests, golden scenarios and the live driver.
- Acceptance:
  - On first use in a project, session-start asks which providers, modes and
    models are allowed, offering detected CLIs and host options, and writes
    the marked table in PROJECT.md.
  - Delegation is refused without it, and for anything it does not allow.
- Checks: `unit-session`, `golden-relay`, `pack-check`.

### R7: Takeover guard

- Scope: `begin` in the runtime, the contract, USAGE.md, tests.
- Acceptance: a solo begin joins in parallel, instead of superseding, when an
  earlier session in this checkout was active within the idle threshold or
  has open delegations. Idle sessions are still taken over.
- Checks: `unit-session`, `golden-relay`.

### R8: Orchestrator hosts beyond T3

- Scope: adapters ("Orchestrator hosts"), a live orchestrator driver, and
  VALIDATION.md.
- Acceptance: live runs, each verified with `--live-verify`:
  - Codex (`codex exec` with project-local skills) orchestrates a Claude
    worker;
  - Claude Code (`claude -p`) orchestrates a Codex worker;
  - Claude Code delegates to its own native subagent.

  Sandbox requirements per host are documented.
- Checks: `live-orchestrators`.

### R5: Release 3.2.0

- Scope: versions, README limits, VALIDATION.md, handover, PR.
- Acceptance: 3.2.0 is consistent everywhere, and the "Not verified" list
  holds only items with a concrete reason.
- Checks: `pack-check`, `unit-workflow`, `unit-session`, `golden-relay`.

## Status at pause (2026-10-15)

- **DONE with recorded checks:**
  - R1: Windows CI, green on PR #5 at 29fb17e (closed 2026-10-16);
  - R2: live `codex exec`;
  - R3: Antigravity through T3, Gemini CLI failure mode;
  - R6: provider policy and first-use question;
  - R7: takeover guard;
  - R8: orchestrators in Claude Code and Codex, plus native subagents.
- **R4 is open.** Codex review round 3 (`review-codex-3`, gpt-6.1-sol)
  returned CHANGES_REQUIRED.
  - Round 2 items: R2-1 and R2-5 are closed. R2-2, R2-3 and R2-4 are
    partially open (items 6, 8 and 9 below).
  - Each finding below needs a failing test, then a fix:
    1. **High.** The policy parser reads rows inside code blocks and comments,
       and a duplicate ID overrides an earlier row (a `claude-pricefx` none row
       can become write). Reject duplicates and ignore commented or fenced
       rows.
    2. An empty or missing model cell counts as any model. Require an explicit
       `any`.
    3. **High.** The Windows job is assigned after the child starts. Put the
       supervisor itself in the job before spawning, and fail loudly when
       assignment fails.
    4. **High.** A nested delegation B escapes parent A's stop: B has a separate
       process group and overwrites the inherited stop-file path. Chain the
       stop requests (watch the parent's file too) and stop child supervisors
       transitively.
    5. The stop sequence blocks heartbeats for about 13 s, past the 10 s
       expiry, so cancel reports unknown during a valid stop. Keep beating
       while stopping.
    6. An explicit `type: null` is treated as absent. Require the key to be
       absent for a Gemini `response`.
    7. Duplicate keys in JSON/JSONL envelopes are resolved silently. Parse
       envelopes with `object_pairs`.
    8. **High.** For a host writer recorded late, its early edits are absorbed
       into the baseline. Record the baseline before launching the host task,
       or flag late recording without a baseline.
    9. A removed worker worktree skips freshness and log validation silently.
       Report it as a discrepancy.
    10. A `runtime-prepared:<name>` event is not attributed in
        `last_activity`. Attribute runtime launches to their session.
    11. `live_orchestrator.py` passes even if the orchestrator failed, did not
        end its session or left workers running, and it does not check the
        requested provider, model or transport. Tighten it.
- **Then:** rerun the suites, the affected golden paths and the live paths
  touched (orchestrators, Windows CI). Have Codex re-review the fix delta.
  After that, R5 releases 3.2.0 (PR #5 is already merged).

