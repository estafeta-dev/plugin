# Relay hardening plan (3.1.1)

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
- Base: `agent-relay-3.1.0` @ 5b3fb8a (PR #3, open). Branch
  `relay-hardening-3.1.1`.

## Decisions

| ID | Question and recommendation | Answer or open impact | Date |
| --- | --- | --- | --- |
| H1 | Linux | Closed by PR #3 CI: ubuntu-latest with Python 3.9 and 3.13 passed all four suites. Record it; no extra work. | 2026-10-15 |
| H2 | Windows without a Windows machine | Add a windows-latest job to CI and iterate by pushing to this branch. Mark POSIX-only tests as skipped with their reason. Fix real runtime defects. | 2026-10-15 |
| H3 | Gemini route | Verify Antigravity live through T3 host tasks. `gemini -p` gets an install and failure-mode check only: personal Gemini logins were retired, and the user chose no API key. | 2026-10-15 |
| H4 | CI double runs | Trigger `push` only for main; pull requests cover branches. | 2026-10-15 |

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
- Acceptance: a Codex review of the round 2 fixes and this update returns
  APPROVE, or each finding is fixed with a test and the fix delta is
  re-reviewed.
- Checks: `live-review-3`, plus the suites.

### R5: Release 3.1.1

- Scope: versions, README limits, VALIDATION.md, handover, PR.
- Acceptance: 3.1.1 is consistent everywhere, and the "Not verified" list
  holds only items with a concrete reason.
- Checks: `pack-check`, `unit-workflow`, `unit-session`, `golden-relay`.
